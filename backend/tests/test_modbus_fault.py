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
