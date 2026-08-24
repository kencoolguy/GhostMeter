"""Integration tests for Modbus client write detection.

Starts a real ModbusTcpAdapter and uses a pymodbus AsyncModbusTcpClient to
issue writes, then asserts they were recorded by write_tracker.
"""

from uuid import uuid4

import pytest
from pymodbus.client import AsyncModbusTcpClient

from app.protocols.base import RegisterInfo
from app.protocols.modbus_tcp import ModbusTcpAdapter
from app.simulation import write_tracker

MODBUS_PORT = 15602
DEVICE_ID = uuid4()
SLAVE_ID = 1
SETPOINT_ADDR = 4


@pytest.fixture
async def adapter():
    adapter = ModbusTcpAdapter(host="127.0.0.1", port=MODBUS_PORT)
    await adapter.start()
    reg = RegisterInfo(
        address=SETPOINT_ADDR,
        function_code=3,
        data_type="uint32",
        byte_order="big_endian",
        name="power_setpoint",
    )
    await adapter.add_device(DEVICE_ID, SLAVE_ID, [reg])
    yield adapter
    write_tracker.clear_all()
    await adapter.stop()


@pytest.fixture
async def client(adapter):
    cli = AsyncModbusTcpClient("127.0.0.1", port=MODBUS_PORT, timeout=5, retries=0)
    await cli.connect()
    yield cli
    cli.close()


async def test_fc6_single_register_write_recorded(client):
    result = await client.write_register(SETPOINT_ADDR, 1234, device_id=SLAVE_ID)
    assert not result.isError()

    events = write_tracker.get_events(DEVICE_ID)
    assert len(events) == 1
    assert events[0].operation == "Write Register"
    assert events[0].address == SETPOINT_ADDR
    assert events[0].values == ["1234"]
    assert events[0].register_name == "power_setpoint"
    assert write_tracker.get_unread_count(DEVICE_ID) == 1


async def test_fc16_multi_register_write_recorded(client):
    result = await client.write_registers(SETPOINT_ADDR, [11, 22], device_id=SLAVE_ID)
    assert not result.isError()

    events = write_tracker.get_events(DEVICE_ID)
    assert len(events) == 1
    assert events[0].operation == "Write Registers"
    assert events[0].address == SETPOINT_ADDR
    assert events[0].values == ["11", "22"]


async def test_coil_write_recorded_even_when_address_illegal(client):
    # No coil datastore exists, so the response is an error — but the attempt
    # is still recorded (trace_pdu sees the incoming request first).
    await client.write_coil(0, True, device_id=SLAVE_ID)

    events = write_tracker.get_events(DEVICE_ID)
    assert len(events) == 1
    assert events[0].operation == "Write Coil"
    assert events[0].values == ["1"]
    assert events[0].register_name is None


async def test_unknown_address_records_with_null_name(client):
    await client.write_register(999, 7, device_id=SLAVE_ID)
    events = write_tracker.get_events(DEVICE_ID)
    assert len(events) == 1
    assert events[0].address == 999
    assert events[0].register_name is None


async def test_read_does_not_record(client):
    await client.read_holding_registers(SETPOINT_ADDR, count=1, device_id=SLAVE_ID)
    assert write_tracker.get_events(DEVICE_ID) == []


async def test_clear_on_remove_device(adapter, client):
    await client.write_register(SETPOINT_ADDR, 1, device_id=SLAVE_ID)
    assert write_tracker.get_unread_count(DEVICE_ID) == 1
    await adapter.remove_device(DEVICE_ID)
    assert write_tracker.get_events(DEVICE_ID) == []


async def test_write_recorded_even_when_timeout_fault_active(adapter, client):
    # The write attempt is recorded before the timeout fault suppresses the
    # slave, so the user still sees that the client issued the write.
    from app.simulation import fault_simulator
    from app.simulation.fault_simulator import FaultConfig

    fault_simulator.set_fault(DEVICE_ID, FaultConfig(fault_type="timeout", params={}))
    try:
        await client.write_register(SETPOINT_ADDR, 55, device_id=SLAVE_ID)
    except Exception:
        pass  # timeout fault suppresses the response — client may raise/time out
    finally:
        fault_simulator.clear_all()

    events = write_tracker.get_events(DEVICE_ID)
    assert len(events) == 1
    assert events[0].values == ["55"]
