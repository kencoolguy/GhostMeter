"""Tests for ModbusTcpAdapter slave-to-device reverse mapping."""

import uuid

import pytest

from app.protocols.modbus_tcp import ModbusTcpAdapter
from app.protocols.base import RegisterInfo


class TestReverseMapping:
    """Test slave_id to device_id reverse mapping."""

    @pytest.mark.asyncio
    async def test_reverse_mapping_on_add(self):
        adapter = ModbusTcpAdapter(host="127.0.0.1", port=15502)
        await adapter.start()
        try:
            device_id = uuid.uuid4()
            registers = [RegisterInfo(address=0, function_code=3, data_type="float32", byte_order="big_endian")]
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
            registers = [RegisterInfo(address=0, function_code=3, data_type="float32", byte_order="big_endian")]
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
        registers = [RegisterInfo(address=0, function_code=3, data_type="float32", byte_order="big_endian")]
        await adapter.add_device(device_id, 1, registers)
        await adapter.stop()
        assert adapter.get_device_id_for_slave(1) is None
