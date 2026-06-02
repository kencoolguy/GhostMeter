"""Tests for the OPC UA server adapter (real asyncua client round-trips)."""

import asyncio
import socket
import uuid

import pytest

pytestmark = pytest.mark.asyncio


def _free_port() -> int:
    """Return an unused TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _SubHandler:
    """Collects datachange notifications from an asyncua subscription."""

    def __init__(self) -> None:
        self.values: list = []

    def datachange_notification(self, node, val, data) -> None:  # noqa: ANN001
        self.values.append(val)


class TestRegisterInfoExtension:
    async def test_registerinfo_accepts_name_and_unit(self):
        from app.protocols.base import RegisterInfo

        reg = RegisterInfo(0, 3, "float32", "big_endian", name="voltage_l1", unit="V")
        assert reg.name == "voltage_l1"
        assert reg.unit == "V"

    async def test_registerinfo_name_unit_default_none(self):
        """Existing callers that omit name/unit still work (backward compat)."""
        from app.protocols.base import RegisterInfo

        reg = RegisterInfo(0, 3, "float32", "big_endian")
        assert reg.name is None
        assert reg.unit is None


class TestOpcUaSettings:
    async def test_opcua_settings_defaults(self):
        from app.config import get_settings

        s = get_settings()
        assert s.OPCUA_PORT == 4840
        assert s.OPCUA_HOST == "0.0.0.0"
        assert s.OPCUA_NAMESPACE_URI == "http://ghostmeter.local/opcua/"
        assert s.OPCUA_ENDPOINT_PATH == "/ghostmeter/server/"


class TestOpcUaLifecycle:
    async def test_initial_status(self):
        from app.protocols.opcua_agent import OpcUaAdapter

        adapter = OpcUaAdapter(host="127.0.0.1", port=_free_port())
        status = adapter.get_status()
        assert status["running"] is False
        assert status["device_count"] == 0
        assert status["node_count"] == 0

    async def test_start_then_client_can_connect(self):
        from asyncua import Client

        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        try:
            assert adapter.get_status()["running"] is True
            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                assert ns >= 0
                # GhostMeter folder exists under Objects
                folder = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                assert folder is not None
        finally:
            await adapter.stop()
        assert adapter.get_status()["running"] is False


class TestOpcUaAddDevice:
    async def test_add_device_creates_named_nodes(self):
        from asyncua import Client

        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        device_id = uuid.uuid4()
        regs = [
            RegisterInfo(0, 3, "float32", "big_endian", name="voltage_l1", unit="V"),
            RegisterInfo(1, 3, "uint32", "big_endian", name="active_power", unit="W"),
        ]
        try:
            adapter.set_device_meta(device_id, "Test Meter")
            await adapter.add_device(device_id, 1, regs)

            status = adapter.get_status()
            assert status["device_count"] == 1
            assert status["node_count"] == 2

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                dev = await gm.get_child([f"{ns}:Test Meter (#1)"])
                var = await dev.get_child([f"{ns}:voltage_l1"])
                assert await var.read_value() == 0.0
        finally:
            await adapter.stop()

    async def test_add_device_falls_back_to_slave_name(self):
        """When set_device_meta is not called, object is named Device_<slave_id>."""
        from asyncua import Client

        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        device_id = uuid.uuid4()
        regs = [RegisterInfo(0, 3, "float32", "big_endian", name="frequency")]
        try:
            await adapter.add_device(device_id, 7, regs)
            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                dev = await gm.get_child([f"{ns}:Device_7"])
                assert dev is not None
        finally:
            await adapter.stop()


    async def test_duplicate_names_are_independently_addressable(self):
        """Two devices sharing a name must both be reachable by browse (issue #2)."""
        from asyncua import Client

        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        dev_a = uuid.uuid4()
        dev_b = uuid.uuid4()
        regs = [RegisterInfo(0, 3, "float32", "big_endian", name="v")]
        try:
            adapter.set_device_meta(dev_a, "Meter")
            adapter.set_device_meta(dev_b, "Meter")
            await adapter.add_device(dev_a, 1, regs)
            await adapter.add_device(dev_b, 2, regs)
            await adapter.update_register(dev_a, 0, 3, 10.0, "float32", "big_endian")
            await adapter.update_register(dev_b, 0, 3, 20.0, "float32", "big_endian")

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index("http://ghostmeter.local/opcua/")
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                a = await (await gm.get_child([f"{ns}:Meter (#1)"])).get_child([f"{ns}:v"])
                b = await (await gm.get_child([f"{ns}:Meter (#2)"])).get_child([f"{ns}:v"])
                assert abs(await a.read_value() - 10.0) < 0.01
                assert abs(await b.read_value() - 20.0) < 0.01
        finally:
            await adapter.stop()


class TestOpcUaUpdateRegister:
    @pytest.mark.parametrize(
        "data_type,written,expected",
        [
            ("float32", 220.5, 220.5),
            ("float64", 49.985, 49.985),
            ("int16", -123.0, -123),
            ("uint16", 1000.0, 1000),
            ("int32", -70000.0, -70000),
            ("uint32", 250000.0, 250000),
        ],
    )
    async def test_update_register_round_trips(self, data_type, written, expected):
        from asyncua import Client

        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        device_id = uuid.uuid4()
        regs = [RegisterInfo(0, 3, data_type, "big_endian", name="value")]
        try:
            adapter.set_device_meta(device_id, "DT")
            await adapter.add_device(device_id, 1, regs)
            await adapter.update_register(device_id, 0, 3, written, data_type, "big_endian")

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                dev = await gm.get_child([f"{ns}:DT (#1)"])
                var = await dev.get_child([f"{ns}:value"])
                read = await var.read_value()
                assert abs(read - expected) < 0.01
        finally:
            await adapter.stop()

    async def test_update_unknown_register_is_noop(self):
        """Writing to a non-existent (device, addr, fc) does not raise."""
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        try:
            await adapter.update_register(
                uuid.uuid4(), 99, 3, 1.0, "float32", "big_endian"
            )
        finally:
            await adapter.stop()


class TestOpcUaSubscription:
    async def test_subscription_fires_on_value_change(self):
        """A subscribed client receives a notification when update_register runs.

        This is the core OPC UA value-add: the push model makes Subscribe work.
        """
        from asyncua import Client

        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        device_id = uuid.uuid4()
        regs = [RegisterInfo(0, 3, "float32", "big_endian", name="voltage")]
        try:
            adapter.set_device_meta(device_id, "SubMeter")
            await adapter.add_device(device_id, 1, regs)

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                dev = await gm.get_child([f"{ns}:SubMeter (#1)"])
                var = await dev.get_child([f"{ns}:voltage"])

                handler = _SubHandler()
                sub = await client.create_subscription(50, handler)
                await sub.subscribe_data_change(var)
                # initial notification arrives with value 0
                await asyncio.sleep(0.3)

                await adapter.update_register(
                    device_id, 0, 3, 231.4, "float32", "big_endian"
                )
                await asyncio.sleep(0.5)
                await sub.delete()

                assert any(abs(v - 231.4) < 0.05 for v in handler.values), (
                    f"expected 231.4 in notifications, got {handler.values}"
                )
        finally:
            await adapter.stop()


class TestOpcUaRemoveDevice:
    async def test_remove_device_clears_nodes(self):
        from asyncua import Client
        from asyncua.ua.uaerrors import BadNoMatch

        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        device_id = uuid.uuid4()
        regs = [
            RegisterInfo(0, 3, "float32", "big_endian", name="voltage_l1"),
            RegisterInfo(1, 3, "float32", "big_endian", name="voltage_l2"),
        ]
        try:
            adapter.set_device_meta(device_id, "Gone")
            await adapter.add_device(device_id, 1, regs)
            assert adapter.get_status()["node_count"] == 2

            await adapter.remove_device(device_id)
            status = adapter.get_status()
            assert status["device_count"] == 0
            assert status["node_count"] == 0

            # _device_meta must be cleaned up (no leak)
            assert device_id not in adapter._device_meta

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                with pytest.raises(BadNoMatch):
                    await gm.get_child([f"{ns}:Gone (#1)"])
        finally:
            await adapter.stop()


class TestOpcUaOutOfRangeClamping:
    @pytest.mark.parametrize(
        "data_type,written,expected",
        [
            ("int16", 99999.0, 32767),
            ("int16", -99999.0, -32768),
            ("uint16", -5.0, 0),
            ("uint16", 99999.0, 65535),
            ("int32", 9e12, 2147483647),
            ("uint32", -1.0, 0),
            ("float32", 1e40, 3.4028234663852886e38),
            ("float32", -1e40, -3.4028234663852886e38),
        ],
    )
    async def test_out_of_range_value_stays_client_readable(self, data_type, written, expected):
        """An out-of-range value (as anomaly injection produces) must be clamped
        so the node remains readable by clients (pre-fix this raised BadInternalError)."""
        from asyncua import Client

        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        device_id = uuid.uuid4()
        regs = [RegisterInfo(0, 3, data_type, "big_endian", name="value")]
        try:
            adapter.set_device_meta(device_id, "Clamp")
            await adapter.add_device(device_id, 1, regs)
            await adapter.update_register(device_id, 0, 3, written, data_type, "big_endian")

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index("http://ghostmeter.local/opcua/")
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                dev = await gm.get_child([f"{ns}:Clamp (#1)"])
                var = await dev.get_child([f"{ns}:value"])
                read = await var.read_value()   # pre-fix: raises BadInternalError
                assert abs(float(read) - float(expected)) <= abs(expected) * 1e-6 + 1e-6
        finally:
            await adapter.stop()


class TestOpcUaDeviceWiring:
    async def test_started_device_appears_as_named_nodes(self, client):
        """Creating + starting an opcua device registers named nodes via device_service.

        Proves the glue: device_service builds RegisterInfo with name/unit and
        calls set_device_meta before add_device.
        """
        from asyncua import Client

        from app.protocols import protocol_manager
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        protocol_manager.register_adapter("opcua", adapter)
        await protocol_manager.start_all()  # only opcua is registered in test process
        try:
            # Create an OPC UA template via the API
            tpl_resp = await client.post("/api/v1/templates", json={
                "name": "Wire-OPCUA",
                "protocol": "opcua",
                "registers": [
                    {"name": "voltage_l1", "address": 0, "function_code": 3,
                     "data_type": "float32", "byte_order": "big_endian",
                     "scale_factor": 1.0, "unit": "V", "sort_order": 0},
                    {"name": "active_power_total", "address": 1, "function_code": 3,
                     "data_type": "float32", "byte_order": "big_endian",
                     "scale_factor": 1.0, "unit": "W", "sort_order": 1},
                ],
            })
            assert tpl_resp.status_code == 201
            template_id = tpl_resp.json()["data"]["id"]

            dev_resp = await client.post("/api/v1/devices", json={
                "name": "MyOpcMeter",
                "template_id": template_id,
                "slave_id": 1,
                "port": 4840,
            })
            assert dev_resp.status_code == 201
            device_id = dev_resp.json()["data"]["id"]

            start_resp = await client.post(f"/api/v1/devices/{device_id}/start")
            assert start_resp.status_code == 200

            assert adapter.get_status()["device_count"] == 1

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as opc:
                ns = await opc.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                gm = await opc.nodes.objects.get_child([f"{ns}:GhostMeter"])
                dev = await gm.get_child([f"{ns}:MyOpcMeter (#1)"])     # proves set_device_meta
                var = await dev.get_child([f"{ns}:voltage_l1"])    # proves RegisterInfo.name
                val = await var.read_value()
                assert isinstance(val, (int, float))
        finally:
            await protocol_manager.stop_all()
            protocol_manager._adapters.pop("opcua", None)
