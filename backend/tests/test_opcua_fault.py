"""Tests for OPC UA comm-layer fault simulation (real asyncua client round-trips)."""

import asyncio
import time
import uuid

import pytest

from tests.netutil import free_tcp_port

pytestmark = pytest.mark.asyncio


class TestOpcUaFaultCache:
    async def test_cache_seeded_on_add_and_updated(self):
        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        adapter = OpcUaAdapter(host="127.0.0.1", port=free_tcp_port())
        await adapter.start()
        dev = uuid.uuid4()
        regs = [RegisterInfo(0, 3, "float32", "big_endian", name="v")]
        try:
            await adapter.add_device(dev, 1, regs)
            # Seeded with 0 on add
            assert adapter._last_values[(dev, 0, 3)][0] == 0
            # Updated by update_register
            await adapter.update_register(dev, 0, 3, 12.5, "float32", "big_endian")
            assert abs(adapter._last_values[(dev, 0, 3)][0] - 12.5) < 0.01
        finally:
            await adapter.stop()

    async def test_cache_cleared_on_remove_and_stop(self):
        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        adapter = OpcUaAdapter(host="127.0.0.1", port=free_tcp_port())
        await adapter.start()
        dev = uuid.uuid4()
        regs = [RegisterInfo(0, 3, "float32", "big_endian", name="v")]
        try:
            await adapter.add_device(dev, 1, regs)
            await adapter.remove_device(dev)
            assert all(k[0] != dev for k in adapter._last_values)
        finally:
            await adapter.stop()
        assert adapter._last_values == {}
        assert adapter._faulted == set()


class _SubHandler:
    def __init__(self) -> None:
        self.values: list = []

    def datachange_notification(self, node, val, data) -> None:  # noqa: ANN001
        self.values.append(val)


async def _make_running_device(port, name="FaultMeter"):
    """Start an adapter with one device + one float32 register at addr 0/fc 3."""
    from app.protocols.base import RegisterInfo
    from app.protocols.opcua_agent import OpcUaAdapter

    adapter = OpcUaAdapter(host="127.0.0.1", port=port)
    await adapter.start()
    dev = uuid.uuid4()
    adapter.set_device_meta(dev, name)
    await adapter.add_device(dev, 1, [RegisterInfo(0, 3, "float32", "big_endian", name="v")])
    await adapter.update_register(dev, 0, 3, 100.0, "float32", "big_endian")
    url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
    return adapter, dev, url


async def _read_status(url, raise_on_bad=False):
    """Connect, read the device's 'v' node DataValue, return (status_name, value)."""
    from asyncua import Client

    async with Client(url=url) as client:
        ns = await client.get_namespace_index("http://ghostmeter.local/opcua/")
        gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
        dev = await gm.get_child([f"{ns}:FaultMeter (#1)"])
        var = await dev.get_child([f"{ns}:v"])
        dv = await var.read_data_value(raise_on_bad_status=raise_on_bad)
        return dv.StatusCode_.name, (dv.Value.Value if dv.Value else None)


class TestOpcUaFaultApplication:
    async def test_exception_fault_yields_bad_device_failure(self):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = free_tcp_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("exception", {}))
            await adapter.apply_fault(dev)
            status, _ = await _read_status(url)
            assert status == "BadDeviceFailure", status
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_timeout_fault_yields_bad_timeout(self):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = free_tcp_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("timeout", {}))
            await adapter.apply_fault(dev)
            status, _ = await _read_status(url)
            assert status == "BadTimeout", status
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_delay_fault_slows_reads(self):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = free_tcp_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("delay", {"delay_ms": 400}))
            await adapter.apply_fault(dev)
            t0 = time.monotonic()
            status, value = await _read_status(url, raise_on_bad=True)
            elapsed = time.monotonic() - t0
            assert status == "Good", status
            assert abs(value - 100.0) < 0.01
            assert elapsed >= 0.3, f"expected >=0.3s, got {elapsed:.3f}s"
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_intermittent_rate_1_always_bad(self):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = free_tcp_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("intermittent", {"failure_rate": 1.0}))
            await adapter.apply_fault(dev)
            for _ in range(3):
                status, _ = await _read_status(url)
                assert status == "BadCommunicationError", status
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_intermittent_rate_0_always_good(self):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = free_tcp_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("intermittent", {"failure_rate": 0.0}))
            await adapter.apply_fault(dev)
            status, value = await _read_status(url, raise_on_bad=True)
            assert status == "Good"
            assert abs(value - 100.0) < 0.01
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_update_register_during_fault_does_not_clear_callback(self):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = free_tcp_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("exception", {}))
            await adapter.apply_fault(dev)
            # Simulation engine keeps pushing values during the fault:
            await adapter.update_register(dev, 0, 3, 222.0, "float32", "big_endian")
            status, _ = await _read_status(url)
            assert status == "BadDeviceFailure", status  # callback still active
            # but the cache tracked the latest value
            assert abs(adapter._last_values[(dev, 0, 3)][0] - 222.0) < 0.01
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_clear_fault_restores_value_and_subscription(self):
        from asyncua import Client

        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = free_tcp_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("exception", {}))
            await adapter.apply_fault(dev)
            # clear
            fault_simulator.clear_fault(dev)
            await adapter.remove_fault(dev)

            async with Client(url=url) as client:
                ns = await client.get_namespace_index("http://ghostmeter.local/opcua/")
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                d = await gm.get_child([f"{ns}:FaultMeter (#1)"])
                var = await d.get_child([f"{ns}:v"])
                # value readable again (the cached 100.0)
                assert abs(await var.read_value() - 100.0) < 0.01
                # subscription resumes
                handler = _SubHandler()
                sub = await client.create_subscription(50, handler)
                await sub.subscribe_data_change(var)
                await asyncio.sleep(0.3)
                await adapter.update_register(dev, 0, 3, 175.0, "float32", "big_endian")
                await asyncio.sleep(0.5)
                await sub.delete()
                assert any(abs(v - 175.0) < 0.05 for v in handler.values), handler.values
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_fault_reattaches_on_device_add(self):
        """A fault set before the device is added is re-applied on add (parity with
        Modbus, where the fault survives a device stop/start)."""
        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = free_tcp_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        dev = uuid.uuid4()
        try:
            fault_simulator.set_fault(dev, FaultConfig("exception", {}))
            adapter.set_device_meta(dev, "FaultMeter")
            regs = [RegisterInfo(0, 3, "float32", "big_endian", name="v")]
            await adapter.add_device(dev, 1, regs)
            assert dev in adapter._faulted
            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            status, _ = await _read_status(url)
            assert status == "BadDeviceFailure", status
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_fault_type_switches_live_without_reattach(self):
        """The callback reads fault_simulator live, so changing the fault type
        while attached flips the observed status with no second apply_fault."""
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = free_tcp_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("exception", {}))
            await adapter.apply_fault(dev)
            status, _ = await _read_status(url)
            assert status == "BadDeviceFailure", status

            # Switch type WITHOUT calling apply_fault again — same callback, live read.
            fault_simulator.set_fault(dev, FaultConfig("timeout", {}))
            status, _ = await _read_status(url)
            assert status == "BadTimeout", status
        finally:
            fault_simulator.clear_all()
            await adapter.stop()


class TestOpcUaFaultRestWiring:
    async def test_put_fault_applies_to_opcua_then_delete_clears(self, client):
        from asyncua import Client

        from app.protocols import protocol_manager
        from app.protocols.opcua_agent import OpcUaAdapter
        from app.simulation import fault_simulator

        port = free_tcp_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        protocol_manager.register_adapter("opcua", adapter)
        await protocol_manager.start_all()
        try:
            tpl = await client.post("/api/v1/templates", json={
                "name": "Fault-OPCUA",
                "protocol": "opcua",
                "registers": [
                    {"name": "v", "address": 0, "function_code": 3,
                     "data_type": "float32", "byte_order": "big_endian",
                     "scale_factor": 1.0, "unit": "V", "sort_order": 0},
                ],
            })
            assert tpl.status_code == 201
            template_id = tpl.json()["data"]["id"]

            dev = await client.post("/api/v1/devices", json={
                "name": "RestFaultMeter", "template_id": template_id,
                "slave_id": 1, "port": 4840,
            })
            assert dev.status_code == 201
            device_id = dev.json()["data"]["id"]
            assert (await client.post(f"/api/v1/devices/{device_id}/start")).status_code == 200

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"

            async def read_status():
                async with Client(url=url) as opc:
                    ns = await opc.get_namespace_index("http://ghostmeter.local/opcua/")
                    gm = await opc.nodes.objects.get_child([f"{ns}:GhostMeter"])
                    d = await gm.get_child([f"{ns}:RestFaultMeter (#1)"])
                    var = await d.get_child([f"{ns}:v"])
                    dv = await var.read_data_value(raise_on_bad_status=False)
                    return dv.StatusCode_.name

            # PUT fault → OPC UA reads go Bad
            put = await client.put(
                f"/api/v1/devices/{device_id}/fault",
                json={"fault_type": "exception", "params": {}},
            )
            assert put.status_code == 200
            assert await read_status() == "BadDeviceFailure"

            # DELETE fault → reads recover
            assert (await client.delete(f"/api/v1/devices/{device_id}/fault")).status_code == 200
            assert await read_status() == "Good"
        finally:
            fault_simulator.clear_all()
            await protocol_manager.stop_all()
            protocol_manager._adapters.pop("opcua", None)
