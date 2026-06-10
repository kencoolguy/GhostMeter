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
