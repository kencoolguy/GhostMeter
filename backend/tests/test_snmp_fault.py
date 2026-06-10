"""Tests for SNMP comm-layer fault simulation (real GET/GETNEXT through the agent)."""

import asyncio
import socket
import time
import uuid

import pytest

pytestmark = pytest.mark.asyncio

OID = "1.3.6.1.2.1.33.1.3.3.1.3.1"


@pytest.fixture(autouse=True)
def _clean_faults():
    from app.simulation import fault_simulator

    fault_simulator.clear_all()
    yield
    fault_simulator.clear_all()


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _set_fault(device_id, fault_type: str, params: dict | None = None) -> None:
    from app.simulation import fault_simulator
    from app.simulation.fault_simulator import FaultConfig

    fault_simulator.set_fault(device_id, FaultConfig(fault_type=fault_type, params=params or {}))


async def _running_agent(monkeypatch):
    """Start an SnmpAdapter on a free port serving one register via OID.

    Returns (adapter, device_id, port). Caller must `await adapter.stop()`.
    """
    from app.protocols.base import RegisterInfo
    from app.protocols.snmp_agent import SnmpAdapter
    from app.simulation import simulation_engine

    port = _free_udp_port()
    device_id = uuid.uuid4()
    monkeypatch.setattr(
        simulation_engine,
        "get_current_values",
        lambda did: {"input_voltage": 221.5} if did == device_id else {},
    )
    adapter = SnmpAdapter(port=port)
    await adapter.start()
    regs = [RegisterInfo(0, 4, "float32", "big_endian", oid=OID, name="input_voltage")]
    await adapter.add_device(device_id, 1, regs)
    adapter.set_register_names(device_id, {OID: "input_voltage"})
    return adapter, device_id, port


async def _snmp_get(port: int, timeout: int = 1, retries: int = 0):
    """One real SNMP GET; returns (errorIndication, errorStatus, varBinds)."""
    from pysnmp.hlapi.v3arch.asyncio import (
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        UdpTransportTarget,
        get_cmd,
    )

    eng = SnmpEngine()
    tgt = await UdpTransportTarget.create(("127.0.0.1", port), timeout=timeout, retries=retries)
    ei, es, _ix, vbs = await get_cmd(
        eng, CommunityData("public", mpModel=1), tgt, ContextData(),
        ObjectType(ObjectIdentity(OID)),
    )
    return ei, es, vbs


class TestSnmpExceptionFault:
    async def test_exception_fault_returns_gen_err(self, monkeypatch):
        adapter, device_id, port = await _running_agent(monkeypatch)
        try:
            _set_fault(device_id, "exception")
            ei, es, _vbs = await _snmp_get(port)
            assert ei is None  # a response DID arrive
            assert int(es) == 5  # genErr
        finally:
            await adapter.stop()

    async def test_exception_cleared_recovers(self, monkeypatch):
        from app.simulation import fault_simulator

        adapter, device_id, port = await _running_agent(monkeypatch)
        try:
            _set_fault(device_id, "exception")
            fault_simulator.clear_fault(device_id)
            ei, es, vbs = await _snmp_get(port)
            assert ei is None and int(es) == 0
            assert "221.5" in vbs[0][1].prettyPrint()
        finally:
            await adapter.stop()


class TestSnmpDropAndDelayFaults:
    async def test_timeout_fault_no_response(self, monkeypatch):
        adapter, device_id, port = await _running_agent(monkeypatch)
        try:
            _set_fault(device_id, "timeout")
            ei, _es, _vbs = await _snmp_get(port)
            assert ei is not None  # request timed out, no response
        finally:
            await adapter.stop()

    async def test_getnext_also_dropped(self, monkeypatch):
        """GETNEXT names a predecessor OID — device resolution must still work."""
        from pysnmp.hlapi.v3arch.asyncio import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            next_cmd,
        )

        adapter, device_id, port = await _running_agent(monkeypatch)
        try:
            _set_fault(device_id, "timeout")
            eng = SnmpEngine()
            tgt = await UdpTransportTarget.create(("127.0.0.1", port), timeout=1, retries=0)
            ei, _es, _ix, _vbs = await next_cmd(
                eng, CommunityData("public", mpModel=1), tgt, ContextData(),
                ObjectType(ObjectIdentity("1.3.6.1.2.1.33.1.3.3.1.3.0")),
            )
            assert ei is not None
        finally:
            await adapter.stop()

    async def test_delay_fault_defers_response_without_blocking(self, monkeypatch):
        adapter, device_id, port = await _running_agent(monkeypatch)
        try:
            _set_fault(device_id, "delay", {"delay_ms": 1200})

            ticks = 0

            async def _heartbeat():
                nonlocal ticks
                while True:
                    await asyncio.sleep(0.05)
                    ticks += 1

            hb = asyncio.create_task(_heartbeat())
            t0 = time.monotonic()
            ei, es, vbs = await _snmp_get(port, timeout=5)
            elapsed = time.monotonic() - t0
            hb.cancel()

            assert ei is None and int(es) == 0
            assert "221.5" in vbs[0][1].prettyPrint()
            assert elapsed >= 1.2
            # call_later must not block the loop; the heartbeat kept ticking
            assert ticks >= 10
        finally:
            await adapter.stop()

    async def test_intermittent_rate_one_drops(self, monkeypatch):
        adapter, device_id, port = await _running_agent(monkeypatch)
        try:
            _set_fault(device_id, "intermittent", {"failure_rate": 1.0})
            ei, _es, _vbs = await _snmp_get(port)
            assert ei is not None
        finally:
            await adapter.stop()

    async def test_intermittent_rate_zero_serves(self, monkeypatch):
        adapter, device_id, port = await _running_agent(monkeypatch)
        try:
            _set_fault(device_id, "intermittent", {"failure_rate": 0.0})
            ei, es, vbs = await _snmp_get(port)
            assert ei is None and int(es) == 0
            assert "221.5" in vbs[0][1].prettyPrint()
        finally:
            await adapter.stop()

    async def test_timeout_cleared_recovers(self, monkeypatch):
        from app.simulation import fault_simulator

        adapter, device_id, port = await _running_agent(monkeypatch)
        try:
            _set_fault(device_id, "timeout")
            ei, _es, _vbs = await _snmp_get(port)
            assert ei is not None
            fault_simulator.clear_fault(device_id)
            ei, es, vbs = await _snmp_get(port)
            assert ei is None and int(es) == 0
        finally:
            await adapter.stop()
