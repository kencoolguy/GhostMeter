"""Unit tests for AnomalyInjector."""

import uuid

import pytest

from app.simulation.anomaly_injector import AnomalyInjector, AnomalyState


@pytest.fixture
def injector() -> AnomalyInjector:
    return AnomalyInjector()


@pytest.fixture
def device_id() -> uuid.UUID:
    return uuid.uuid4()


class TestInjectAndApply:
    def test_no_anomaly_returns_original(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        result = injector.apply(device_id, "voltage", 230.0, 10.0)
        assert result == 230.0

    def test_flatline_with_explicit_value(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "flatline", {"value": 200.0})
        result = injector.apply(device_id, "voltage", 230.0, 10.0)
        assert result == 200.0

    def test_flatline_freezes_at_current(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "flatline", {})
        result1 = injector.apply(device_id, "voltage", 230.0, 10.0)
        assert result1 == 230.0
        result2 = injector.apply(device_id, "voltage", 240.0, 11.0)
        assert result2 == 230.0

    def test_out_of_range(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "out_of_range", {"value": 999.0})
        result = injector.apply(device_id, "voltage", 230.0, 10.0)
        assert result == 999.0

    def test_data_loss(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "data_loss", {})
        result = injector.apply(device_id, "voltage", 230.0, 10.0)
        assert result == 0.0

    def test_spike_with_probability_1(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(
            device_id, "voltage", "spike",
            {"multiplier": 3.0, "probability": 1.0},
        )
        result = injector.apply(device_id, "voltage", 100.0, 10.0)
        assert result == 300.0

    def test_spike_with_probability_0(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(
            device_id, "voltage", "spike",
            {"multiplier": 3.0, "probability": 0.0},
        )
        result = injector.apply(device_id, "voltage", 100.0, 10.0)
        assert result == 100.0

    def test_drift_accumulates(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(
            device_id, "voltage", "drift",
            {"drift_per_second": 1.0, "max_drift": 50.0},
        )
        result_at_10 = injector.apply(device_id, "voltage", 230.0, 10.0)
        assert result_at_10 == 230.0
        result_at_15 = injector.apply(device_id, "voltage", 230.0, 15.0)
        assert result_at_15 == 235.0

    def test_drift_capped_at_max(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(
            device_id, "voltage", "drift",
            {"drift_per_second": 10.0, "max_drift": 5.0},
        )
        injector.apply(device_id, "voltage", 230.0, 10.0)
        result = injector.apply(device_id, "voltage", 230.0, 20.0)
        assert result == 235.0


class TestRemoveAndClear:
    def test_remove_specific_register(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "data_loss", {})
        injector.inject(device_id, "current", "data_loss", {})
        injector.remove(device_id, "voltage")
        assert injector.apply(device_id, "voltage", 230.0, 10.0) == 230.0
        assert injector.apply(device_id, "current", 15.0, 10.0) == 0.0

    def test_clear_device(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "data_loss", {})
        injector.inject(device_id, "current", "data_loss", {})
        injector.clear_device(device_id)
        assert injector.apply(device_id, "voltage", 230.0, 10.0) == 230.0
        assert injector.apply(device_id, "current", 15.0, 10.0) == 15.0

    def test_get_active_anomalies(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "spike", {"multiplier": 2.0, "probability": 1.0})
        active = injector.get_active(device_id)
        assert len(active) == 1
        assert "voltage" in active
        assert active["voltage"].anomaly_type == "spike"

    def test_get_active_empty(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        active = injector.get_active(device_id)
        assert active == {}


class TestScheduleChecking:
    def test_schedule_activates_in_window(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.load_schedules(device_id, [
            {
                "register_name": "voltage",
                "anomaly_type": "data_loss",
                "anomaly_params": {},
                "trigger_after_seconds": 100,
                "duration_seconds": 60,
            },
        ])
        result_50 = injector.apply(device_id, "voltage", 230.0, 50.0)
        assert result_50 == 230.0
        result_120 = injector.apply(device_id, "voltage", 230.0, 120.0)
        assert result_120 == 0.0
        result_170 = injector.apply(device_id, "voltage", 230.0, 170.0)
        assert result_170 == 230.0

    def test_realtime_takes_precedence_over_schedule(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.load_schedules(device_id, [
            {
                "register_name": "voltage",
                "anomaly_type": "data_loss",
                "anomaly_params": {},
                "trigger_after_seconds": 0,
                "duration_seconds": 9999,
            },
        ])
        injector.inject(device_id, "voltage", "out_of_range", {"value": 999.0})
        result = injector.apply(device_id, "voltage", 230.0, 50.0)
        assert result == 999.0
