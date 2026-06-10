"""Tests for BACnet comm-layer fault simulation (real bacpypes3 client round-trips)."""

import asyncio
import contextlib
import socket
import time
import uuid

import pytest
from bacpypes3.settings import settings as bp3_settings

NETWORK = 100

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module", autouse=True)
def _route_aware():
    """Enable route-aware addresses so the client reaches VLAN devices on loopback."""
    previous = bp3_settings.route_aware
    bp3_settings.route_aware = True
    yield
    bp3_settings.route_aware = previous


@pytest.fixture(autouse=True)
def _clean_faults():
    """Fault state is process-global; never leak it between tests."""
    from app.simulation import fault_simulator

    fault_simulator.clear_all()
    yield
    fault_simulator.clear_all()


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.asynccontextmanager
async def _client_app():
    from bacpypes3.app import Application
    from bacpypes3.local.device import DeviceObject
    from bacpypes3.local.networkport import NetworkPortObject

    port = _free_udp_port()
    app = Application.from_object_list([
        DeviceObject(
            objectIdentifier=("device", 4194302),
            objectName="fault-test-client",
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
        port=_free_udp_port(),
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

    return [RegisterInfo(0, 3, "float32", "big_endian", name="voltage", unit="V")]


def _set_fault(device_id, fault_type: str, params: dict | None = None) -> None:
    from app.simulation import fault_simulator
    from app.simulation.fault_simulator import FaultConfig

    fault_simulator.set_fault(device_id, FaultConfig(fault_type=fault_type, params=params or {}))


class TestBacnetReadFaults:
    async def test_exception_fault_returns_bacnet_error(self):
        from bacpypes3.apdu import ErrorRejectAbortNack
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "exception")
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                with pytest.raises(ErrorRejectAbortNack) as exc_info:
                    await client.read_property(
                        addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                    )
                assert "operational-problem" in str(exc_info.value)
            stats = adapter.get_stats(device_id)
            assert stats.error_count >= 1

    async def test_timeout_fault_drops_response(self):
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "timeout")
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        client.read_property(
                            addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                        ),
                        timeout=2,
                    )
            stats = adapter.get_stats(device_id)
            assert stats.request_count >= 1
            assert stats.error_count >= 1
            assert stats.success_count == 0

    async def test_delay_fault_postpones_response(self):
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            await adapter.update_register(device_id, 0, 3, 230.0, "float32", "big_endian")
            _set_fault(device_id, "delay", {"delay_ms": 1000})
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                t0 = time.monotonic()
                value = await client.read_property(
                    addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                )
                elapsed = time.monotonic() - t0
                assert elapsed >= 1.0
                assert abs(float(value) - 230.0) < 0.01

    async def test_intermittent_rate_one_always_drops(self):
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "intermittent", {"failure_rate": 1.0})
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        client.read_property(
                            addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                        ),
                        timeout=2,
                    )

    async def test_intermittent_rate_zero_always_serves(self):
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "intermittent", {"failure_rate": 0.0})
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                value = await client.read_property(
                    addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                )
                assert value is not None

    async def test_clear_fault_recovers(self):
        from bacpypes3.primitivedata import ObjectIdentifier

        from app.simulation import fault_simulator

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "timeout")
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        client.read_property(
                            addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                        ),
                        timeout=2,
                    )
                fault_simulator.clear_fault(device_id)
                value = await client.read_property(
                    addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                )
                assert value is not None

    async def test_rpm_also_gated(self):
        """ReadPropertyMultiple goes through the same gate as ReadProperty."""
        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "timeout")
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        client.read_property_multiple(
                            addr, ["analog-input,0", ["present-value"]]
                        ),
                        timeout=2,
                    )


class TestBacnetWhoIsFault:
    async def test_whois_suppressed_under_timeout(self):
        from bacpypes3.pdu import Address

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "timeout")
            async with _client_app() as client:
                addr = Address(f"{NETWORK}:*@127.0.0.1:{adapter._port}")
                # who_is resolves on first I-Am for low==high, else waits its
                # internal window (~3 s) and returns whatever arrived: nothing.
                i_ams = await client.who_is(100001, 100001, addr)
                assert i_ams == []

    async def test_whois_recovers_after_clear(self):
        from bacpypes3.pdu import Address

        from app.simulation import fault_simulator

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "timeout")
            fault_simulator.clear_fault(device_id)
            async with _client_app() as client:
                addr = Address(f"{NETWORK}:*@127.0.0.1:{adapter._port}")
                i_ams = await client.who_is(100001, 100001, addr)
                assert len(i_ams) == 1
                assert i_ams[0].iAmDeviceIdentifier[1] == 100001

    async def test_whois_unaffected_by_delay_fault(self):
        """Only timeout/intermittent make the device go dark; delay applies to reads."""
        from bacpypes3.pdu import Address

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "delay", {"delay_ms": 5000})
            async with _client_app() as client:
                addr = Address(f"{NETWORK}:*@127.0.0.1:{adapter._port}")
                i_ams = await asyncio.wait_for(client.who_is(100001, 100001, addr), timeout=4)
                assert len(i_ams) == 1


BACNET_TEMPLATE_PAYLOAD = {
    "name": "BACnet Fault E2E Meter",
    "protocol": "bacnet",
    "registers": [
        {
            "name": "voltage",
            "address": 0,
            "function_code": 3,
            "data_type": "float32",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "V",
            "description": "Voltage",
            "sort_order": 0,
        },
    ],
}


class TestBacnetFaultRestE2E:
    async def test_set_and_clear_fault_via_api(self, client):
        from bacpypes3.primitivedata import ObjectIdentifier

        resp = await client.post("/api/v1/templates", json=BACNET_TEMPLATE_PAYLOAD)
        assert resp.status_code == 201
        template_id = resp.json()["data"]["id"]

        resp = await client.post(
            "/api/v1/devices",
            json={"template_id": template_id, "name": "E2E BACnet", "slave_id": 60},
        )
        assert resp.status_code == 201
        device_id = uuid.UUID(resp.json()["data"]["id"])

        async with _running_adapter() as adapter:
            await adapter.add_device(device_id, 60, _regs())
            async with _client_app() as bn_client:
                addr = _device_addr(adapter._port, 60)
                ai0 = ObjectIdentifier(("analog-input", 0))

                # Healthy read first
                assert await bn_client.read_property(addr, ai0, "present-value") is not None

                # Set timeout fault through the REST API
                resp = await client.put(
                    f"/api/v1/devices/{device_id}/fault",
                    json={"fault_type": "timeout", "params": {}},
                )
                assert resp.status_code == 200
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        bn_client.read_property(addr, ai0, "present-value"), timeout=2
                    )

                # Clear through the REST API → recovers
                resp = await client.delete(f"/api/v1/devices/{device_id}/fault")
                assert resp.status_code == 200
                assert await bn_client.read_property(addr, ai0, "present-value") is not None
