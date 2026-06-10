"""Tests for the BACnet/IP adapter (real bacpypes3 client round-trips on loopback)."""

import socket
import uuid

import pytest

pytestmark = pytest.mark.asyncio


def _free_udp_port() -> int:
    """Return an unused UDP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


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

        adapter = BacnetAdapter(address="127.0.0.1/32", port=_free_udp_port())
        status = adapter.get_status()
        assert status["running"] is False
        assert status["device_count"] == 0
        assert status["object_count"] == 0

    async def test_start_stop(self):
        from app.protocols.bacnet_agent import BacnetAdapter

        adapter = BacnetAdapter(address="127.0.0.1/32", port=_free_udp_port())
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

        port = _free_udp_port()
        adapter = BacnetAdapter(address="127.0.0.1/32", port=port)
        await adapter.start()
        await adapter.stop()
        # Second start must not raise "existing network" ValueError
        await adapter.start()
        try:
            assert adapter.get_status()["running"] is True
        finally:
            await adapter.stop()
