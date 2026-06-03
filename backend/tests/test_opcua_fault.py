"""Tests for OPC UA comm-layer fault simulation (real asyncua client round-trips)."""

import asyncio  # noqa: F401 — used in Task 3 tests
import socket
import time  # noqa: F401 — used in Task 3 tests
import uuid

import pytest

pytestmark = pytest.mark.asyncio


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestOpcUaFaultCache:
    async def test_cache_seeded_on_add_and_updated(self):
        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        adapter = OpcUaAdapter(host="127.0.0.1", port=_free_port())
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

        adapter = OpcUaAdapter(host="127.0.0.1", port=_free_port())
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
