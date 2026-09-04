import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.simulation.engine import SimulationEngine


class TestSimulationEngineLifecycle:
    @pytest.mark.asyncio
    async def test_start_device_no_configs(self):
        engine = SimulationEngine()
        device_id = uuid.uuid4()
        with patch.object(engine, '_load_device_data', new_callable=AsyncMock) as mock_load:
            mock_load.return_value = ([], {}, "modbus_tcp")
            await engine.start_device(device_id)
            assert device_id not in engine._device_states

    @pytest.mark.asyncio
    async def test_stop_nonexistent_device_noop(self):
        engine = SimulationEngine()
        await engine.stop_device(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_shutdown_empty(self):
        engine = SimulationEngine()
        await engine.shutdown()
        assert len(engine._device_states) == 0

    @pytest.mark.asyncio
    async def test_reload_calls_load(self):
        engine = SimulationEngine()
        device_id = uuid.uuid4()
        with patch.object(engine, '_load_device_data', new_callable=AsyncMock) as mock_load:
            mock_load.return_value = ([], {}, "modbus_tcp")
            await engine.reload_device(device_id)
            assert mock_load.call_count == 1


class _FakeAdapter:
    """Records update_register calls; no network."""

    def __init__(self):
        self.updates: list[tuple] = []

    async def update_register(self, *args):
        self.updates.append(args)


def _static_config(device_id, register, value, interval_ms=100):
    from app.models.simulation import SimulationConfig

    return SimulationConfig(
        device_id=device_id, register_name=register, data_mode="static",
        mode_params={"value": value}, is_enabled=True, update_interval_ms=interval_ms,
    )


def _aggregate_config(device_id, register, sources, op="sum", on_missing="last_known"):
    from app.models.simulation import SimulationConfig

    return SimulationConfig(
        device_id=device_id, register_name=register, data_mode="aggregate",
        mode_params={"op": op, "sources": sources, "on_missing": on_missing},
        is_enabled=True, update_interval_ms=100,
    )


@pytest.fixture
def aggregate_world(monkeypatch):
    """Two static sub-meters + one aggregating main meter, all DB/network free.

    ``directory`` maps names → ids like ``load_device_directory`` would; the
    engine's DB loaders are patched to use it.
    """
    from types import SimpleNamespace

    import app.simulation.engine as engine_mod
    from app.simulation.aggregate import DeviceDirectory, resolve_sources
    from app.simulation.engine import RegisterMeta

    ids = {name: uuid.uuid4() for name in ("PM-01", "PM-02", "MVCB")}
    directory = DeviceDirectory()
    for name, dev_id in ids.items():
        directory.by_id[dev_id] = SimpleNamespace(id=dev_id, name=name)
        directory.by_name[name] = [dev_id]

    configs = {
        ids["PM-01"]: [_static_config(ids["PM-01"], "energy", 10.0)],
        ids["PM-02"]: [_static_config(ids["PM-02"], "energy", 20.0)],
        ids["MVCB"]: [_aggregate_config(ids["MVCB"], "energy", ["PM-01", "PM-02"])],
    }
    register_map = {"energy": RegisterMeta(0, 3, "float32", "big_endian", 1.0, 0)}
    adapter = _FakeAdapter()
    engine = SimulationEngine()

    async def fake_load(device_id):
        return (configs[device_id], register_map, "modbus_tcp")

    async def fake_directory(_session):
        return directory

    async def fake_deps(_session, _directory):
        # Mirror what the DB would hold: every aggregate config's sources
        deps = {}
        for dev_id, cfgs in configs.items():
            for c in cfgs:
                if c.data_mode == "aggregate":
                    deps.setdefault(dev_id, set()).update(
                        resolve_sources(directory, c.mode_params["sources"], strict=False)
                    )
        return deps

    class _NullSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(engine, "_load_device_data", fake_load)
    monkeypatch.setattr(engine, "_load_anomaly_schedules", AsyncMock(return_value=[]))
    monkeypatch.setattr(engine_mod, "async_session_factory", lambda: _NullSession())
    monkeypatch.setattr(engine_mod, "load_device_directory", fake_directory)
    monkeypatch.setattr(engine_mod, "load_aggregate_dependencies", fake_deps)
    monkeypatch.setattr(engine_mod.protocol_manager, "get_adapter", lambda _p: adapter)
    return SimpleNamespace(engine=engine, ids=ids, configs=configs, adapter=adapter)


class TestAggregateMode:
    @pytest.mark.asyncio
    async def test_main_meter_sums_running_sources(self, aggregate_world):
        w = aggregate_world
        try:
            for name in ("PM-01", "PM-02", "MVCB"):
                await w.engine.start_device(w.ids[name])
            await asyncio.sleep(0.25)
            assert w.engine.get_current_values(w.ids["MVCB"])["energy"] == 30.0
        finally:
            await w.engine.shutdown()

    @pytest.mark.asyncio
    async def test_stopped_source_keeps_last_known_value(self, aggregate_world):
        w = aggregate_world
        try:
            for name in ("PM-01", "PM-02", "MVCB"):
                await w.engine.start_device(w.ids[name])
            await asyncio.sleep(0.25)
            await w.engine.stop_device(w.ids["PM-02"])
            await asyncio.sleep(0.25)
            # PM-02 is gone from live values but its last value still counts
            assert w.ids["PM-02"] not in w.engine._device_values
            assert w.engine.get_current_values(w.ids["MVCB"])["energy"] == 30.0
        finally:
            await w.engine.shutdown()

    @pytest.mark.asyncio
    async def test_on_missing_zero_drops_stopped_source(self, aggregate_world):
        w = aggregate_world
        w.configs[w.ids["MVCB"]] = [
            _aggregate_config(w.ids["MVCB"], "energy", ["PM-01", "PM-02"], on_missing="zero"),
        ]
        try:
            for name in ("PM-01", "PM-02", "MVCB"):
                await w.engine.start_device(w.ids[name])
            await asyncio.sleep(0.25)
            await w.engine.stop_device(w.ids["PM-02"])
            await asyncio.sleep(0.25)
            assert w.engine.get_current_values(w.ids["MVCB"])["energy"] == 10.0
        finally:
            await w.engine.shutdown()

    @pytest.mark.asyncio
    async def test_unresolvable_source_is_skipped_not_fatal(self, aggregate_world):
        w = aggregate_world
        w.configs[w.ids["MVCB"]] = [
            _aggregate_config(w.ids["MVCB"], "energy", ["PM-01", "deleted-meter"]),
        ]
        try:
            await w.engine.start_device(w.ids["PM-01"])
            await w.engine.start_device(w.ids["MVCB"])
            await asyncio.sleep(0.25)
            assert w.engine.get_current_values(w.ids["MVCB"])["energy"] == 10.0
        finally:
            await w.engine.shutdown()

    @pytest.mark.asyncio
    async def test_cycle_rejected_at_launch(self, aggregate_world):
        from app.simulation.aggregate import AggregateCycleError

        w = aggregate_world
        # PM-01 now aggregates MVCB while MVCB aggregates PM-01
        w.configs[w.ids["PM-01"]] = [_aggregate_config(w.ids["PM-01"], "energy", ["MVCB"])]
        try:
            with pytest.raises(AggregateCycleError, match="MVCB"):
                await w.engine.start_device(w.ids["MVCB"])
            assert not w.engine.is_device_simulating(w.ids["MVCB"])
        finally:
            await w.engine.shutdown()

    @pytest.mark.asyncio
    async def test_aggregate_evaluated_before_same_device_computed(self, aggregate_world):
        from app.models.simulation import SimulationConfig
        from app.simulation.engine import RegisterMeta

        w = aggregate_world
        # 'doubled' sorts *before* 'energy' in the template yet depends on it
        w.configs[w.ids["MVCB"]] = [
            SimulationConfig(
                device_id=w.ids["MVCB"], register_name="doubled", data_mode="computed",
                mode_params={"expression": "{energy} * 2"}, is_enabled=True,
                update_interval_ms=100,
            ),
            _aggregate_config(w.ids["MVCB"], "energy", ["PM-01", "PM-02"]),
        ]
        register_map = {
            "doubled": RegisterMeta(0, 3, "float32", "big_endian", 1.0, 0),
            "energy": RegisterMeta(2, 3, "float32", "big_endian", 1.0, 1),
        }

        async def fake_load(device_id):
            return (w.configs[device_id], register_map, "modbus_tcp")

        w.engine._load_device_data = fake_load
        try:
            for name in ("PM-01", "PM-02", "MVCB"):
                await w.engine.start_device(w.ids[name])
            await asyncio.sleep(0.25)
            values = w.engine.get_current_values(w.ids["MVCB"])
            assert values == {"energy": 30.0, "doubled": 60.0}
        finally:
            await w.engine.shutdown()
