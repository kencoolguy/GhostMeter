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


async def test_internal_updates_are_not_recorded():
    """Simulation-engine writes (update_register → node.write_value, is_external
    False) must NOT be recorded as client writes."""
    from app.simulation import write_tracker

    write_tracker.clear_all()
    port = free_tcp_port()
    adapter, dev, _url = await _make_running_device(port)  # does one update_register
    try:
        # Several more internal updates — none should be recorded.
        for v in (1.0, 2.0, 3.0):
            await adapter.update_register(dev, 0, 3, v, "float32", "big_endian")
        assert write_tracker.get_events(dev) == []
        assert write_tracker.get_unread_count(dev) == 0
    finally:
        await adapter.stop()


async def test_recorded_value_is_client_original_not_coerced():
    """The audit trail records exactly what the client sent, even when the value
    is coerced to the node's type for the actual (read-back) write."""
    import uuid as _uuid

    from asyncua import Client

    from app.protocols.base import RegisterInfo
    from app.protocols.opcua_agent import OpcUaAdapter
    from app.simulation import write_tracker

    write_tracker.clear_all()
    port = free_tcp_port()
    adapter = OpcUaAdapter(host="127.0.0.1", port=port)
    await adapter.start()
    dev = _uuid.uuid4()
    adapter.set_device_meta(dev, "IntMeter")
    # int16 register → a Double written by a loose client gets coerced on apply.
    await adapter.add_device(dev, 1, [RegisterInfo(0, 3, "int16", "big_endian", name="sp")])
    url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
    try:
        async with Client(url=url) as client:
            ns = await client.get_namespace_index("http://ghostmeter.local/opcua/")
            gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
            d = await gm.get_child([f"{ns}:IntMeter (#1)"])
            var = await d.get_child([f"{ns}:sp"])
            await var.write_value(55.9)  # Double → coerced to int16 on apply
            assert await var.read_value() == 55  # applied value is the coerced int

        events = write_tracker.get_events(dev)
        assert len(events) == 1
        assert events[0].values == ["55.9"]  # recorded value is the client original
        assert events[0].register_name == "sp"
    finally:
        await adapter.stop()
