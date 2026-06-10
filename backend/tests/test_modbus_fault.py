"""Tests for ModbusTcpAdapter slave-to-device reverse mapping."""

import uuid

import pytest

from app.protocols.base import RegisterInfo
from app.protocols.modbus_tcp import ModbusTcpAdapter


class TestBaseFaultHooks:
    """The base apply_fault/remove_fault hooks are no-ops; Modbus inherits them
    unchanged (Modbus applies faults via trace_pdu polling, not via these hooks)."""

    @pytest.mark.asyncio
    async def test_modbus_fault_hooks_are_noops(self):
        adapter = ModbusTcpAdapter(host="127.0.0.1", port=15598)
        dev = uuid.uuid4()
        # No start(), no device registered — pure no-ops must not raise.
        await adapter.apply_fault(dev)
        await adapter.remove_fault(dev)


class TestReverseMapping:
    """Test slave_id to device_id reverse mapping."""

    @pytest.mark.asyncio
    async def test_reverse_mapping_on_add(self):
        adapter = ModbusTcpAdapter(host="127.0.0.1", port=15502)
        await adapter.start()
        try:
            device_id = uuid.uuid4()
            registers = [RegisterInfo(
                address=0, function_code=3, data_type="float32", byte_order="big_endian",
            )]
            await adapter.add_device(device_id, 1, registers)

            assert adapter.get_device_id_for_slave(1) == device_id
            assert adapter.get_device_id_for_slave(99) is None
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_reverse_mapping_cleared_on_remove(self):
        adapter = ModbusTcpAdapter(host="127.0.0.1", port=15503)
        await adapter.start()
        try:
            device_id = uuid.uuid4()
            registers = [RegisterInfo(
                address=0, function_code=3, data_type="float32", byte_order="big_endian",
            )]
            await adapter.add_device(device_id, 1, registers)
            await adapter.remove_device(device_id)

            assert adapter.get_device_id_for_slave(1) is None
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_reverse_mapping_cleared_on_stop(self):
        adapter = ModbusTcpAdapter(host="127.0.0.1", port=15504)
        await adapter.start()
        device_id = uuid.uuid4()
        registers = [RegisterInfo(
            address=0, function_code=3, data_type="float32", byte_order="big_endian",
        )]
        await adapter.add_device(device_id, 1, registers)
        await adapter.stop()
        assert adapter.get_device_id_for_slave(1) is None


class _FakePdu:
    """Minimal stand-in for a pymodbus PDU as seen by trace_pdu."""

    def __init__(self, dev_id: int = 1, transaction_id: int = 1, function_code: int = 3):
        self.dev_id = dev_id
        self.transaction_id = transaction_id
        self.function_code = function_code


class TestFaultParamClamping:
    """Modbus must consume the shared clamping helpers: delay capped at 10 s
    (previously unbounded — delay_ms=999999 hung the response ~17 min) and
    failure_rate sanitized (previously a malformed rate crashed trace_pdu)."""

    def _adapter_with_fault(self, fault_type: str, params: dict):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        adapter = ModbusTcpAdapter(host="127.0.0.1", port=15599)
        device_id = uuid.uuid4()
        adapter._slave_to_device[1] = device_id
        fault_simulator.set_fault(device_id, FaultConfig(fault_type=fault_type, params=params))
        return adapter, device_id

    @pytest.mark.asyncio
    async def test_delay_fault_clamped_to_10s_cap(self, monkeypatch):
        from app.simulation import fault_simulator

        adapter, device_id = self._adapter_with_fault("delay", {"delay_ms": 999_999})
        sleeps: list[float] = []
        monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
        try:
            trace_pdu = adapter._create_trace_pdu()
            trace_pdu(True, _FakePdu())  # outgoing response path applies delay
            assert sleeps == [10.0]
        finally:
            fault_simulator.clear_fault(device_id)

    @pytest.mark.asyncio
    async def test_delay_fault_nan_falls_back_to_default(self, monkeypatch):
        from app.simulation import fault_simulator

        adapter, device_id = self._adapter_with_fault("delay", {"delay_ms": float("nan")})
        sleeps: list[float] = []
        monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
        try:
            trace_pdu = adapter._create_trace_pdu()
            trace_pdu(True, _FakePdu())
            assert sleeps == [0.5]
        finally:
            fault_simulator.clear_fault(device_id)

    @pytest.mark.asyncio
    async def test_intermittent_malformed_rate_does_not_crash(self, monkeypatch):
        from app.simulation import fault_simulator

        adapter, device_id = self._adapter_with_fault("intermittent", {"failure_rate": "abc"})
        # Deterministic: 0.9 >= fallback 0.5 → no drop, no _suppress_slave call
        monkeypatch.setattr("random.random", lambda: 0.9)
        try:
            trace_pdu = adapter._create_trace_pdu()
            result = trace_pdu(False, _FakePdu())  # incoming path; must not raise
            assert result is not None
        finally:
            fault_simulator.clear_fault(device_id)
