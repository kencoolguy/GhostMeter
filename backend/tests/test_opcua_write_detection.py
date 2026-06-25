"""Integration tests for OPC UA client write detection (real asyncua round-trips)."""

import uuid

import pytest

from tests.netutil import free_tcp_port

pytestmark = pytest.mark.asyncio


async def _make_running_device(port, name="WriteMeter"):
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


async def test_client_write_is_recorded_and_applied():
    from asyncua import Client

    from app.simulation import write_tracker

    write_tracker.clear_all()
    port = free_tcp_port()
    adapter, dev, url = await _make_running_device(port)
    try:
        async with Client(url=url) as client:
            ns = await client.get_namespace_index("http://ghostmeter.local/opcua/")
            gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
            d = await gm.get_child([f"{ns}:WriteMeter (#1)"])
            var = await d.get_child([f"{ns}:v"])
            await var.write_value(55.5)  # succeeds — node is writable now
            assert abs(await var.read_value() - 55.5) < 0.01  # applied (read-back friendly)

        events = write_tracker.get_events(dev)
        assert len(events) == 1
        assert events[0].operation == "Write"
        assert events[0].address == 0
        assert float(events[0].values[0]) == pytest.approx(55.5, abs=0.01)
        assert events[0].register_name == "v"
        assert write_tracker.get_unread_count(dev) == 1
    finally:
        await adapter.stop()


async def test_clear_on_remove_device():
    from asyncua import Client

    from app.simulation import write_tracker

    write_tracker.clear_all()
    port = free_tcp_port()
    adapter, dev, url = await _make_running_device(port)
    try:
        async with Client(url=url) as client:
            ns = await client.get_namespace_index("http://ghostmeter.local/opcua/")
            gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
            d = await gm.get_child([f"{ns}:WriteMeter (#1)"])
            var = await d.get_child([f"{ns}:v"])
            await var.write_value(7.0)
        assert write_tracker.get_unread_count(dev) == 1
        await adapter.remove_device(dev)
        assert write_tracker.get_events(dev) == []
    finally:
        await adapter.stop()
