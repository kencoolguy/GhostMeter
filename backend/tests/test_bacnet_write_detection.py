"""Integration tests for BACnet client write detection (real bacpypes3 round-trips)."""

import contextlib
import uuid

import pytest
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.settings import settings as bp3_settings

from tests.netutil import free_udp_port

NETWORK = 100

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module", autouse=True)
def _route_aware():
    previous = bp3_settings.route_aware
    bp3_settings.route_aware = True
    yield
    bp3_settings.route_aware = previous


def _regs():
    from app.protocols.base import RegisterInfo

    return [RegisterInfo(0, 3, "float32", "big_endian", name="voltage", unit="V")]


@contextlib.asynccontextmanager
async def _client_app():
    from bacpypes3.app import Application
    from bacpypes3.local.device import DeviceObject
    from bacpypes3.local.networkport import NetworkPortObject

    port = free_udp_port()
    app = Application.from_object_list([
        DeviceObject(
            objectIdentifier=("device", 4194302),
            objectName="write-test-client",
            vendorIdentifier=999,
        ),
        NetworkPortObject(
            f"127.0.0.1/32:{port}",
            objectIdentifier=("network-port", 1),
            objectName="client-port",
        ),
    ])
    try:
        yield app
    finally:
        app.close()


def _device_addr(router_port: int, slave_id: int):
    from bacpypes3.pdu import Address

    return Address(f"{NETWORK}:{slave_id}@127.0.0.1:{router_port}")


@contextlib.asynccontextmanager
async def _running_adapter():
    from app.protocols.bacnet_agent import BacnetAdapter

    adapter = BacnetAdapter(
        address="127.0.0.1/32",
        port=free_udp_port(),
        device_instance_base=100000,
        network=NETWORK,
    )
    await adapter.start()
    try:
        yield adapter
    finally:
        await adapter.stop()


async def test_write_property_is_recorded_and_acked():
    from app.simulation import write_tracker

    write_tracker.clear_all()
    device_id = uuid.uuid4()
    async with _running_adapter() as adapter:
        await adapter.add_device(device_id, 1, _regs())
        async with _client_app() as client:
            addr = _device_addr(adapter._port, 1)
            # Should succeed (accept-and-ignore), NOT raise writeAccessDenied:
            await client.write_property(
                addr, ObjectIdentifier(("analog-input", 0)), "present-value", 42.5
            )

        events = write_tracker.get_events(device_id)
        assert len(events) == 1
        assert events[0].operation == "WriteProperty"
        assert events[0].address == 0  # object instance == register address
        assert float(events[0].values[0]) == 42.5
        assert events[0].register_name == "voltage"
        assert write_tracker.get_unread_count(device_id) == 1


async def test_clear_on_remove_device():
    from app.simulation import write_tracker

    write_tracker.clear_all()
    device_id = uuid.uuid4()
    async with _running_adapter() as adapter:
        await adapter.add_device(device_id, 1, _regs())
        async with _client_app() as client:
            addr = _device_addr(adapter._port, 1)
            await client.write_property(
                addr, ObjectIdentifier(("analog-input", 0)), "present-value", 7.0
            )
        assert write_tracker.get_unread_count(device_id) == 1
        await adapter.remove_device(device_id)
        assert write_tracker.get_events(device_id) == []
