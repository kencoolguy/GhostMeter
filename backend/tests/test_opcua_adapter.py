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
