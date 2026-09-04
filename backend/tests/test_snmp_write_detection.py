"""SNMP SET handling (issue #97): recorded as a client write, refused with notWritable.

Real SET requests over UDP through the agent, like test_snmp_fault.py.
"""

import uuid

import pytest

from tests.netutil import free_udp_port

pytestmark = pytest.mark.asyncio

OID = "1.3.6.1.2.1.33.1.3.3.1.3.1"
UNKNOWN_OID = "1.3.6.1.2.1.33.1.9.9.9.9"
NOT_WRITABLE = 17
GEN_ERR = 5


async def _running_agent(monkeypatch):
    from app.protocols.base import RegisterInfo
    from app.protocols.snmp_agent import SnmpAdapter
    from app.simulation import simulation_engine, write_tracker

    write_tracker.clear_all()
    port = free_udp_port()
    device_id = uuid.uuid4()
    monkeypatch.setattr(
        simulation_engine, "get_current_values",
        lambda did: {"input_voltage": 221.5} if did == device_id else {},
    )
    adapter = SnmpAdapter(port=port)
    await adapter.start()
    regs = [RegisterInfo(7, 4, "float32", "big_endian", oid=OID, name="input_voltage")]
    await adapter.add_device(device_id, 1, regs)
    return adapter, device_id, port


async def _snmp_set(port: int, oid: str, value, timeout: int = 1):
    from pysnmp.hlapi.v3arch.asyncio import (
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        UdpTransportTarget,
        set_cmd,
    )

    eng = SnmpEngine()
    tgt = await UdpTransportTarget.create(("127.0.0.1", port), timeout=timeout, retries=0)
    ei, es, _ix, vbs = await set_cmd(
        eng, CommunityData("public", mpModel=1), tgt, ContextData(),
        ObjectType(ObjectIdentity(oid), value),
    )
    return ei, es, vbs


async def test_set_is_refused_with_not_writable_and_recorded(monkeypatch):
    from pysnmp.proto.rfc1902 import Gauge32

    from app.simulation import write_tracker

    adapter, device_id, port = await _running_agent(monkeypatch)
    try:
        ei, es, _ = await _snmp_set(port, OID, Gauge32(230))
        assert ei is None, f"no response: {ei}"   # a reply DID arrive (no silent drop)
        assert int(es) == NOT_WRITABLE

        events = write_tracker.get_events(device_id)
        assert len(events) == 1
        ev = events[0]
        assert ev.operation == "Set"
        assert ev.address == 7
        assert ev.values == ["230"]
        assert ev.register_name == "input_voltage"
        assert write_tracker.get_unread_count(device_id) == 1
    finally:
        await adapter.stop()


async def test_set_string_value_is_recorded_as_text(monkeypatch):
    from pysnmp.proto.rfc1902 import OctetString

    from app.simulation import write_tracker

    adapter, device_id, port = await _running_agent(monkeypatch)
    try:
        ei, es, _ = await _snmp_set(port, OID, OctetString("hello"))
        assert ei is None and int(es) == NOT_WRITABLE
        assert write_tracker.get_events(device_id)[0].values == ["hello"]
    finally:
        await adapter.stop()


async def test_set_unknown_oid_not_writable_and_not_recorded(monkeypatch):
    from pysnmp.proto.rfc1902 import Gauge32

    from app.simulation import write_tracker

    adapter, device_id, port = await _running_agent(monkeypatch)
    try:
        ei, es, _ = await _snmp_set(port, UNKNOWN_OID, Gauge32(1))
        assert ei is None and int(es) == NOT_WRITABLE
        assert write_tracker.get_events(device_id) == []
    finally:
        await adapter.stop()


async def test_set_does_not_change_served_value(monkeypatch):
    from pysnmp.hlapi.v3arch.asyncio import (
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        UdpTransportTarget,
        get_cmd,
    )
    from pysnmp.proto.rfc1902 import Gauge32

    adapter, device_id, port = await _running_agent(monkeypatch)
    try:
        await _snmp_set(port, OID, Gauge32(999))
        tgt = await UdpTransportTarget.create(("127.0.0.1", port), timeout=1, retries=0)
        ei, es, _ix, vbs = await get_cmd(
            SnmpEngine(), CommunityData("public", mpModel=1), tgt, ContextData(),
            ObjectType(ObjectIdentity(OID)),
        )
        assert ei is None and int(es) == 0
        assert vbs[0][1].prettyPrint() == "221.5"  # engine still owns the value
    finally:
        await adapter.stop()


async def test_set_under_timeout_fault_is_dropped_but_recorded(monkeypatch):
    from pysnmp.proto.rfc1902 import Gauge32

    from app.simulation import fault_simulator, write_tracker
    from app.simulation.fault_simulator import FaultConfig

    adapter, device_id, port = await _running_agent(monkeypatch)
    try:
        fault_simulator.set_fault(device_id, FaultConfig(fault_type="timeout", params={}))
        ei, _es, _ = await _snmp_set(port, OID, Gauge32(1))
        assert ei is not None  # client timed out — device is "dark"
        # The drop happens before the PDU reaches the MIB controller, so
        # nothing is recorded — consistent with the GET path going fully dark.
        assert write_tracker.get_events(device_id) == []
    finally:
        fault_simulator.clear_fault(device_id)
        await adapter.stop()


async def test_set_under_exception_fault_returns_gen_err_and_records(monkeypatch):
    from pysnmp.proto.rfc1902 import Gauge32

    from app.simulation import fault_simulator, write_tracker
    from app.simulation.fault_simulator import FaultConfig

    adapter, device_id, port = await _running_agent(monkeypatch)
    try:
        fault_simulator.set_fault(device_id, FaultConfig(fault_type="exception", params={}))
        ei, es, _ = await _snmp_set(port, OID, Gauge32(1))
        assert ei is None and int(es) == GEN_ERR
        assert len(write_tracker.get_events(device_id)) == 1
    finally:
        fault_simulator.clear_fault(device_id)
        await adapter.stop()


async def test_remove_device_clears_write_events(monkeypatch):
    from pysnmp.proto.rfc1902 import Gauge32

    from app.simulation import write_tracker

    adapter, device_id, port = await _running_agent(monkeypatch)
    try:
        await _snmp_set(port, OID, Gauge32(1))
        assert write_tracker.get_events(device_id)
        await adapter.remove_device(device_id)
        assert write_tracker.get_events(device_id) == []
    finally:
        await adapter.stop()
