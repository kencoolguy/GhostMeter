"""Tests for the BACnet/IP adapter (real bacpypes3 client round-trips on loopback)."""

import asyncio
import contextlib
import socket
import uuid

import pytest
from bacpypes3.settings import settings as bp3_settings

from tests.netutil import free_udp_port

NETWORK = 100

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module", autouse=True)
def _route_aware():
    """Enable route-aware addresses for this module; restore on teardown.

    Route-aware addresses ("net:mac@router-ip:port") let the test client reach
    VLAN devices through the router on loopback without any broadcasts.
    """
    previous = bp3_settings.route_aware
    bp3_settings.route_aware = True
    yield
    bp3_settings.route_aware = previous


@contextlib.asynccontextmanager
async def _client_app():
    """A standalone bacpypes3 client application bound to loopback."""
    from bacpypes3.app import Application
    from bacpypes3.local.device import DeviceObject
    from bacpypes3.local.networkport import NetworkPortObject

    port = free_udp_port()
    app = Application.from_object_list([
        DeviceObject(
            objectIdentifier=("device", 4194302),
            objectName="test-client",
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
    """A started BacnetAdapter bound to loopback on a free port."""
    from app.protocols.bacnet_agent import BacnetAdapter

    adapter = BacnetAdapter(
        address="127.0.0.1/32",
        port=free_udp_port(),
        device_instance_base=100000,
        network=NETWORK,
    )
    await adapter.start()
    assert adapter.get_status()["running"] is True
    try:
        yield adapter
    finally:
        await adapter.stop()


def _regs():
    from app.protocols.base import RegisterInfo

    return [
        RegisterInfo(0, 3, "float32", "big_endian", name="voltage_l1", unit="V"),
        RegisterInfo(1, 3, "float32", "big_endian", name="active_power", unit="kW"),
        RegisterInfo(2, 3, "int16", "big_endian", name="status", unit=None),
    ]


class TestBacnetSettings:
    async def test_bacnet_settings_defaults(self):
        from app.config import get_settings

        s = get_settings()
        assert s.BACNET_ADDRESS == "0.0.0.0/0"
        assert s.BACNET_PORT == 47808
        assert s.BACNET_DEVICE_INSTANCE_BASE == 100000
        assert s.BACNET_NETWORK == 100


class TestBacnetLifecycle:
    async def test_initial_status(self):
        from app.protocols.bacnet_agent import BacnetAdapter

        adapter = BacnetAdapter(address="127.0.0.1/32", port=free_udp_port())
        status = adapter.get_status()
        assert status["running"] is False
        assert status["device_count"] == 0
        assert status["object_count"] == 0

    async def test_start_stop(self):
        from app.protocols.bacnet_agent import BacnetAdapter

        adapter = BacnetAdapter(address="127.0.0.1/32", port=free_udp_port())
        await adapter.start()
        try:
            status = adapter.get_status()
            assert status["running"] is True
            assert status["port"] == adapter._port
        finally:
            await adapter.stop()
        assert adapter.get_status()["running"] is False

    async def test_restart_after_stop(self):
        """VLAN name must be released on stop (VirtualNetwork._networks is global)."""
        from app.protocols.bacnet_agent import BacnetAdapter

        port = free_udp_port()
        adapter = BacnetAdapter(address="127.0.0.1/32", port=port)
        await adapter.start()
        await adapter.stop()
        # Second start must not raise "existing network" ValueError
        await adapter.start()
        try:
            assert adapter.get_status()["running"] is True
        finally:
            await adapter.stop()

    async def test_start_fails_when_port_occupied(self):
        """bacpypes3 binds asynchronously with infinite retry — without a
        pre-bind probe, start() would report running=True with a dead socket."""
        from app.protocols.bacnet_agent import BacnetAdapter

        port = free_udp_port()
        blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        blocker.bind(("127.0.0.1", port))
        try:
            adapter = BacnetAdapter(address="127.0.0.1/32", port=port)
            await adapter.start()
            assert adapter.get_status()["running"] is False
        finally:
            blocker.close()
            await adapter.stop()

    async def test_wildcard_bind_serves_unicast(self):
        """0.0.0.0/0 (production default) must answer unicast reads — bacpypes3's
        un-bindable 255.255.255.255 broadcast endpoint would otherwise block
        every reply on macOS (indication() gathers _transport_tasks).

        Note: regression guard for macOS dev hosts; Linux allows binding
        255.255.255.255, so this would pass there even without the fix.
        """
        from bacpypes3.app import Application
        from bacpypes3.local.device import DeviceObject
        from bacpypes3.local.networkport import NetworkPortObject
        from bacpypes3.pdu import Address
        from bacpypes3.primitivedata import ObjectIdentifier

        from app.protocols.bacnet_agent import BacnetAdapter

        port = free_udp_port()
        adapter = BacnetAdapter(address="0.0.0.0/0", port=port)
        await adapter.start()
        client = None
        try:
            assert adapter.get_status()["running"] is True
            client = Application.from_object_list([
                DeviceObject(
                    objectIdentifier=("device", 4194301),
                    objectName="wildcard-probe",
                    vendorIdentifier=999,
                ),
                NetworkPortObject(
                    f"127.0.0.1/32:{free_udp_port()}",
                    objectIdentifier=("network-port", 1),
                    objectName="probe-port",
                ),
            ])
            name = await asyncio.wait_for(
                client.read_property(
                    Address(f"127.0.0.1:{port}"),
                    ObjectIdentifier(("device", 100000)),
                    "object-name",
                ),
                timeout=5,
            )
            assert str(name) == "GhostMeter BACnet Router"
        finally:
            if client is not None:
                client.close()
            await adapter.stop()


class TestBacnetAddRemoveDevice:
    async def test_add_device_creates_objects(self):
        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            status = adapter.get_status()
            assert status["device_count"] == 1
            assert status["object_count"] == 3

    async def test_client_reads_object_name_and_units(self):
        from bacpypes3.basetypes import EngineeringUnits
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            adapter.set_device_meta(device_id, "Test Meter")
            await adapter.add_device(device_id, 1, _regs())

            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                # read_property requires ObjectIdentifier instances (bare
                # tuples raise TypeError in bacpypes3 0.0.106)
                ai0 = ObjectIdentifier(("analog-input", 0))
                name = await client.read_property(addr, ai0, "object-name")
                assert str(name) == "voltage_l1"
                units = await client.read_property(addr, ai0, "units")
                assert units == EngineeringUnits("volts")
                dev_name = await client.read_property(
                    addr, ObjectIdentifier(("device", 100001)), "object-name"
                )
                assert str(dev_name) == "Test Meter"

    async def test_device_instance_conflict_raises(self):
        from app.exceptions import ConflictException

        async with _running_adapter() as adapter:
            await adapter.add_device(uuid.uuid4(), 1, _regs())
            with pytest.raises(ConflictException):
                await adapter.add_device(uuid.uuid4(), 1, _regs())

    async def test_remove_device_clears_objects(self):
        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            await adapter.remove_device(device_id)
            status = adapter.get_status()
            assert status["device_count"] == 0
            assert status["object_count"] == 0
            # The device's VirtualNode must be detached from the VLAN —
            # app.close() alone leaves a zombie node still answering on MAC 1.
            # Only the router's own VLAN node may remain.
            assert len(adapter._vlan.nodes) == 1
            # Same slave_id can be re-added after removal
            await adapter.add_device(uuid.uuid4(), 1, _regs())
            assert len(adapter._vlan.nodes) == 2

    async def test_failed_add_does_not_leak_vlan_node(self):
        """A register name colliding with an internal object name aborts the
        add — the half-built app's VLAN node must be detached so the same
        slave_id can be re-added cleanly."""
        from app.protocols.base import RegisterInfo

        async with _running_adapter() as adapter:
            bad_regs = _regs() + [
                RegisterInfo(5, 3, "float32", "big_endian", name="NetworkPort-VLAN"),
            ]
            failed_device_id = uuid.uuid4()
            with pytest.raises(Exception):
                await adapter.add_device(failed_device_id, 1, bad_regs)
            # Only the router node remains on the VLAN
            assert len(adapter._vlan.nodes) == 1
            assert adapter.get_status()["device_count"] == 0
            assert adapter.get_status()["object_count"] == 0
            # The stats entry created by the base template method must be
            # rolled back on failure
            assert adapter.get_stats(failed_device_id) is None
            # Same slave_id can be added cleanly afterwards
            await adapter.add_device(uuid.uuid4(), 1, _regs())
            assert len(adapter._vlan.nodes) == 2


class TestBacnetUpdateRegister:
    async def test_update_then_client_reads_new_value(self):
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            await adapter.update_register(
                device_id, 0, 3, 231.5, "float32", "big_endian"
            )
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                value = await client.read_property(
                    addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                )
                assert abs(float(value) - 231.5) < 0.01

    async def test_update_unknown_register_is_noop(self):
        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            # Unknown address: must not raise
            await adapter.update_register(
                device_id, 99, 3, 1.0, "float32", "big_endian"
            )

    async def test_write_property_rejected(self):
        """Read-only contract: WriteProperty must return writeAccessDenied and
        the simulated value must remain unchanged."""
        from bacpypes3.apdu import ErrorRejectAbortNack
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            await adapter.update_register(device_id, 0, 3, 220.0, "float32", "big_endian")
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                with pytest.raises(ErrorRejectAbortNack) as exc_info:
                    await client.write_property(
                        addr, ObjectIdentifier(("analog-input", 0)), "present-value", 999.0
                    )
                assert "write-access-denied" in str(exc_info.value)
                value = await client.read_property(
                    addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                )
                assert abs(float(value) - 220.0) < 0.01

    async def test_out_of_range_value_clamped_to_float32(self):
        """Anomaly injection can produce values beyond float32 range; they
        must be clamped so client reads keep succeeding (BACnet Real is
        float32 on the wire — unclamped 1e40 raises OverflowError during
        response encoding)."""
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            await adapter.update_register(
                device_id, 0, 3, 1e40, "float32", "big_endian"
            )
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                value = await client.read_property(
                    addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                )
                assert float(value) == pytest.approx(3.4028234663852886e38)


class TestBacnetStats:
    async def test_read_property_counts_stats(self):
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                await client.read_property(
                    addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                )
                await client.read_property(
                    addr, ObjectIdentifier(("analog-input", 1)), "present-value"
                )

            # client reads completed → responses already sent → stats recorded
            stats = adapter.get_stats(device_id)
            assert stats is not None
            assert stats.request_count == 2
            assert stats.success_count == 2
            assert stats.error_count == 0
            assert stats.avg_response_ms >= 0.0

    async def test_reset_stats(self):
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                await client.read_property(
                    addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                )
            adapter.reset_stats(device_id)
            assert adapter.get_stats(device_id).request_count == 0


class TestBacnetDiscoveryAndRpm:
    async def test_directed_whois_returns_i_am(self):
        from bacpypes3.pdu import Address

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            async with _client_app() as client:
                # Remote-broadcast Who-Is on the VLAN, routed via the router.
                # who_is() drops the source-address filter for broadcast
                # destinations and low==high makes it resolve on the first
                # matching I-Am, so this returns immediately (no 3 s timeout).
                addr = Address(f"{NETWORK}:*@127.0.0.1:{adapter._port}")
                i_ams = await client.who_is(100001, 100001, addr)
                assert len(i_ams) == 1
                assert i_ams[0].iAmDeviceIdentifier[1] == 100001

    async def test_read_property_multiple(self):
        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            await adapter.update_register(
                device_id, 0, 3, 220.0, "float32", "big_endian"
            )
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                results = await client.read_property_multiple(
                    addr,
                    [
                        "analog-input,0", ["present-value", "object-name"],
                        "analog-input,2", ["present-value"],
                    ],
                )
                values = {
                    (str(objid), str(propid)): value
                    for objid, propid, _aidx, value in results
                }
                assert abs(float(values[("analog-input,0", "present-value")]) - 220.0) < 0.01
                assert str(values[("analog-input,0", "object-name")]) == "voltage_l1"
                assert float(values[("analog-input,2", "present-value")]) == 0.0
