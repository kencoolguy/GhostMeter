"""Tests for MQTT comm-layer fault simulation (publish loop with a fake client)."""

import asyncio
import time
import uuid
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean_faults():
    from app.simulation import fault_simulator

    fault_simulator.clear_all()
    yield
    fault_simulator.clear_all()


class _FakeMqttClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, float]] = []

    async def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, time.monotonic()))


def _publish_config(interval: float = 0.05):
    return SimpleNamespace(
        topic_template="ghost/{device_name}",
        payload_mode="batch",
        publish_interval_seconds=interval,
        qos=0,
        retain=False,
    )


def _set_fault(device_id, fault_type: str, params: dict | None = None) -> None:
    from app.simulation import fault_simulator
    from app.simulation.fault_simulator import FaultConfig

    fault_simulator.set_fault(device_id, FaultConfig(fault_type=fault_type, params=params or {}))


async def _publishing_adapter(monkeypatch, device_id):
    """An MqttAdapter publishing every 50 ms to a fake in-memory client."""
    from app.protocols.base import RegisterInfo
    from app.protocols.mqtt_adapter import MqttAdapter
    from app.simulation import simulation_engine

    monkeypatch.setattr(
        simulation_engine,
        "get_current_values",
        lambda did: {"voltage": 220.0} if did == device_id else {},
    )
    adapter = MqttAdapter()
    adapter._connected = True
    adapter._available = True
    adapter._client = _FakeMqttClient()
    await adapter.add_device(
        device_id, 1, [RegisterInfo(0, 3, "float32", "big_endian", name="voltage")]
    )
    adapter.set_device_meta(device_id, "FaultMeter", 1, "TestTemplate")
    await adapter.start_publishing(device_id, _publish_config())
    return adapter


class TestMqttPublishFaults:
    async def test_baseline_publishes_flow(self, monkeypatch):
        device_id = uuid.uuid4()
        adapter = await _publishing_adapter(monkeypatch, device_id)
        try:
            await asyncio.sleep(0.4)
            assert len(adapter._client.published) >= 3
        finally:
            await adapter.stop_publishing(device_id)

    async def test_timeout_fault_stops_publishing(self, monkeypatch):
        device_id = uuid.uuid4()
        adapter = await _publishing_adapter(monkeypatch, device_id)
        try:
            _set_fault(device_id, "timeout")
            await asyncio.sleep(0.2)  # let any in-flight iteration drain
            count_after_settle = len(adapter._client.published)
            errors_before = adapter.get_stats(device_id).error_count
            await asyncio.sleep(0.4)
            assert len(adapter._client.published) == count_after_settle
            assert adapter.get_stats(device_id).error_count > errors_before
        finally:
            await adapter.stop_publishing(device_id)

    async def test_intermittent_rate_one_stops_rate_zero_flows(self, monkeypatch):
        device_id = uuid.uuid4()
        adapter = await _publishing_adapter(monkeypatch, device_id)
        try:
            _set_fault(device_id, "intermittent", {"failure_rate": 1.0})
            await asyncio.sleep(0.2)
            count = len(adapter._client.published)
            await asyncio.sleep(0.4)
            assert len(adapter._client.published) == count

            _set_fault(device_id, "intermittent", {"failure_rate": 0.0})
            await asyncio.sleep(0.4)
            assert len(adapter._client.published) > count
        finally:
            await adapter.stop_publishing(device_id)

    async def test_delay_fault_spaces_out_publishes(self, monkeypatch):
        device_id = uuid.uuid4()
        adapter = await _publishing_adapter(monkeypatch, device_id)
        try:
            _set_fault(device_id, "delay", {"delay_ms": 300})
            await asyncio.sleep(1.0)
            stamps = [t for _, _, t in adapter._client.published]
            # Find at least two publishes emitted while the fault was active
            # and check their spacing reflects interval (0.05) + delay (0.3).
            faulted_gaps = [
                b - a for a, b in zip(stamps, stamps[1:]) if (b - a) >= 0.3
            ]
            assert faulted_gaps, "expected at least one delayed publish gap >= 0.3s"
        finally:
            await adapter.stop_publishing(device_id)

    async def test_clear_fault_resumes_publishing(self, monkeypatch):
        from app.simulation import fault_simulator

        device_id = uuid.uuid4()
        adapter = await _publishing_adapter(monkeypatch, device_id)
        try:
            _set_fault(device_id, "timeout")
            await asyncio.sleep(0.2)
            count = len(adapter._client.published)
            fault_simulator.clear_fault(device_id)
            await asyncio.sleep(0.4)
            assert len(adapter._client.published) > count
        finally:
            await adapter.stop_publishing(device_id)
