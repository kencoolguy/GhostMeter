import uuid

import pytest

from app.simulation.fault_simulator import FaultConfig, FaultSimulator


@pytest.fixture
def simulator():
    return FaultSimulator()


@pytest.fixture
def device_id():
    return uuid.uuid4()


class TestFaultSimulator:
    def test_no_fault_by_default(self, simulator, device_id):
        assert simulator.get_fault(device_id) is None

    def test_set_and_get_fault(self, simulator, device_id):
        config = FaultConfig(fault_type="delay", params={"delay_ms": 500})
        simulator.set_fault(device_id, config)
        result = simulator.get_fault(device_id)
        assert result is not None
        assert result.fault_type == "delay"
        assert result.params["delay_ms"] == 500

    def test_set_fault_replaces_existing(self, simulator, device_id):
        simulator.set_fault(device_id, FaultConfig(fault_type="delay", params={"delay_ms": 100}))
        simulator.set_fault(device_id, FaultConfig(fault_type="timeout", params={}))
        result = simulator.get_fault(device_id)
        assert result is not None
        assert result.fault_type == "timeout"

    def test_clear_fault(self, simulator, device_id):
        simulator.set_fault(device_id, FaultConfig(fault_type="delay", params={"delay_ms": 500}))
        simulator.clear_fault(device_id)
        assert simulator.get_fault(device_id) is None

    def test_clear_nonexistent_fault_noop(self, simulator, device_id):
        simulator.clear_fault(device_id)

    def test_get_fault_with_none_device_id(self, simulator):
        assert simulator.get_fault(None) is None

    def test_multiple_devices_independent(self, simulator):
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        simulator.set_fault(id1, FaultConfig(fault_type="delay", params={"delay_ms": 100}))
        simulator.set_fault(id2, FaultConfig(fault_type="timeout", params={}))
        assert simulator.get_fault(id1).fault_type == "delay"
        assert simulator.get_fault(id2).fault_type == "timeout"

    def test_clear_all(self, simulator):
        id1, id2 = uuid.uuid4(), uuid.uuid4()
        simulator.set_fault(id1, FaultConfig(fault_type="delay", params={"delay_ms": 100}))
        simulator.set_fault(id2, FaultConfig(fault_type="timeout", params={}))
        simulator.clear_all()
        assert simulator.get_fault(id1) is None
        assert simulator.get_fault(id2) is None


class TestFaultConfig:
    def test_valid_fault_types(self):
        for ft in ("delay", "timeout", "exception", "intermittent"):
            config = FaultConfig(fault_type=ft, params={})
            assert config.fault_type == ft


class TestFaultParamHelpers:
    """Clamping helpers shared by the BACnet/SNMP/MQTT fault gates."""

    def test_delay_default_is_500ms(self):
        from app.simulation.fault_simulator import get_delay_seconds

        assert get_delay_seconds({}) == 0.5

    def test_delay_clamps_to_10s_cap(self):
        from app.simulation.fault_simulator import get_delay_seconds

        assert get_delay_seconds({"delay_ms": 99_999}) == 10.0

    def test_delay_negative_clamps_to_zero(self):
        from app.simulation.fault_simulator import get_delay_seconds

        assert get_delay_seconds({"delay_ms": -5}) == 0.0

    def test_delay_malformed_falls_back_to_default(self):
        from app.simulation.fault_simulator import get_delay_seconds

        assert get_delay_seconds({"delay_ms": "abc"}) == 0.5
        assert get_delay_seconds({"delay_ms": None}) == 0.5

    def test_rate_default_is_half(self):
        from app.simulation.fault_simulator import get_failure_rate

        assert get_failure_rate({}) == 0.5

    def test_rate_clamped_to_unit_interval(self):
        from app.simulation.fault_simulator import get_failure_rate

        assert get_failure_rate({"failure_rate": 1.7}) == 1.0
        assert get_failure_rate({"failure_rate": -0.2}) == 0.0

    def test_rate_malformed_falls_back_to_default(self):
        from app.simulation.fault_simulator import get_failure_rate

        assert get_failure_rate({"failure_rate": "x"}) == 0.5
