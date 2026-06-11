# BACnet / SNMP / MQTT Comm-layer Fault Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend comm-layer fault simulation (delay / timeout / exception / intermittent) to the BACnet, SNMP, and MQTT adapters so all five protocols support it through the existing REST API.

**Architecture:** Pull-based everywhere (the Modbus model): each adapter consults the in-memory `fault_simulator` singleton on its serving path. BACnet intercepts in `_DeviceApplication` async handlers; SNMP intercepts in subclassed pysnmp command responders (drop/delay) plus the MIB controller (exception → genErr); MQTT checks inside `_publish_loop`. No `apply_fault`/`remove_fault` overrides, no DB changes, one REST validation rule added (MQTT + exception → 422).

**Tech Stack:** Python 3.12, bacpypes3 0.0.106, pysnmp 7.1.27, aiomqtt, FastAPI, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-06-11-fault-sim-snmp-mqtt-bacnet-design.md` (approved).

**Branch:** `feature/claude-fault-sim-snmp-mqtt-bacnet-20260611` (already created; spec committed).

---

## Environment notes (read first)

- Run tests from `backend/` with the Python 3.12 venv and host DB override:
  ```bash
  cd backend && DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter" ./.venv/bin/python -m pytest <args>
  ```
  Postgres must be up: `docker compose up -d postgres`. Below, `PYTEST` means exactly this invocation.
- `fault_simulator` is a module-level **instance** created in `backend/app/simulation/__init__.py` (`fault_simulator = FaultSimulator()`). Adapters import it lazily inside functions (existing pattern, avoids circular imports): `from app.simulation import fault_simulator`.
- The new param helpers are **module-level functions** in `app/simulation/fault_simulator.py` (not methods): import them with `from app.simulation.fault_simulator import get_delay_seconds, get_failure_rate`.
- Fault state is process-global. Every new fault test file needs the autouse cleanup fixture (shown in each test task) so faults never leak between tests.

---

### Task 1: Shared fault-param helpers

**Files:**
- Modify: `backend/app/simulation/fault_simulator.py`
- Test: `backend/tests/test_fault_simulator.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_fault_simulator.py`:

```python
class TestFaultParamHelpers:
    """Clamping helpers shared by the BACnet/SNMP/MQTT fault gates."""

    def test_delay_default_is_500ms(self):
        from app.simulation.fault_simulator import get_delay_seconds

        assert get_delay_seconds({}) == 0.5

    def test_delay_clamps_to_10s_cap(self):
        from app.simulation.fault_simulator import get_delay_seconds

        assert get_delay_seconds({"delay_ms": 99_999}) == 10.0

    def test_delay_negative_clamps_to_zero(self):
        from app.simulation.fault_simulator import get_delay_seconds

        assert get_delay_seconds({"delay_ms": -5}) == 0.0

    def test_delay_malformed_falls_back_to_default(self):
        from app.simulation.fault_simulator import get_delay_seconds

        assert get_delay_seconds({"delay_ms": "abc"}) == 0.5
        assert get_delay_seconds({"delay_ms": None}) == 0.5

    def test_rate_default_is_half(self):
        from app.simulation.fault_simulator import get_failure_rate

        assert get_failure_rate({}) == 0.5

    def test_rate_clamped_to_unit_interval(self):
        from app.simulation.fault_simulator import get_failure_rate

        assert get_failure_rate({"failure_rate": 1.7}) == 1.0
        assert get_failure_rate({"failure_rate": -0.2}) == 0.0

    def test_rate_malformed_falls_back_to_default(self):
        from app.simulation.fault_simulator import get_failure_rate

        assert get_failure_rate({"failure_rate": "x"}) == 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTEST tests/test_fault_simulator.py::TestFaultParamHelpers -v`
Expected: FAIL — `ImportError: cannot import name 'get_delay_seconds'`

- [ ] **Step 3: Implement the helpers**

Append to `backend/app/simulation/fault_simulator.py` (after the `FaultSimulator` class):

```python
MAX_DELAY_MS = 10_000  # matches the OPC UA server-side delay cap


def get_delay_seconds(params: dict) -> float:
    """Return a delay fault's duration in seconds, clamped to [0, MAX_DELAY_MS].

    Malformed values fall back to the 500 ms default rather than crashing the
    serving path.
    """
    try:
        delay_ms = float(params.get("delay_ms", 500))
    except (TypeError, ValueError):
        delay_ms = 500.0
    return min(max(delay_ms, 0.0), float(MAX_DELAY_MS)) / 1000.0


def get_failure_rate(params: dict) -> float:
    """Return an intermittent fault's failure rate, clamped to [0.0, 1.0]."""
    try:
        rate = float(params.get("failure_rate", 0.5))
    except (TypeError, ValueError):
        rate = 0.5
    return min(max(rate, 0.0), 1.0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests/test_fault_simulator.py -v`
Expected: ALL PASS (new helpers + pre-existing FaultSimulator tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/simulation/fault_simulator.py backend/tests/test_fault_simulator.py
git commit -m "feat: add shared fault-param clamping helpers (delay cap, failure rate)"
```

---

### Task 2: BACnet read-path fault gate

**Files:**
- Modify: `backend/app/protocols/bacnet_agent.py` (imports + `_DeviceApplication`)
- Create: `backend/tests/test_bacnet_fault.py`

- [ ] **Step 1: Create the test file with helpers and read-fault tests**

Create `backend/tests/test_bacnet_fault.py`. Helpers are duplicated from `tests/test_bacnet_adapter.py` (existing convention: `test_opcua_fault.py` duplicates `_free_port` too):

```python
"""Tests for BACnet comm-layer fault simulation (real bacpypes3 client round-trips)."""

import asyncio
import contextlib
import socket
import time
import uuid

import pytest
from bacpypes3.settings import settings as bp3_settings

NETWORK = 100

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module", autouse=True)
def _route_aware():
    """Enable route-aware addresses so the client reaches VLAN devices on loopback."""
    previous = bp3_settings.route_aware
    bp3_settings.route_aware = True
    yield
    bp3_settings.route_aware = previous


@pytest.fixture(autouse=True)
def _clean_faults():
    """Fault state is process-global; never leak it between tests."""
    from app.simulation import fault_simulator

    fault_simulator.clear_all()
    yield
    fault_simulator.clear_all()


def _free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.asynccontextmanager
async def _client_app():
    from bacpypes3.app import Application
    from bacpypes3.local.device import DeviceObject
    from bacpypes3.local.networkport import NetworkPortObject

    port = _free_udp_port()
    app = Application.from_object_list([
        DeviceObject(
            objectIdentifier=("device", 4194302),
            objectName="fault-test-client",
            vendorIdentifier=999,
        ),
        NetworkPortObject(
            f"127.0.0.1/32:{port}",
            objectIdentifier=("network-port", 1),
            objectName="client-port",
        ),
    ])
    try:
        yield app
    finally:
        app.close()


def _device_addr(router_port: int, slave_id: int):
    from bacpypes3.pdu import Address

    return Address(f"{NETWORK}:{slave_id}@127.0.0.1:{router_port}")


@contextlib.asynccontextmanager
async def _running_adapter():
    from app.protocols.bacnet_agent import BacnetAdapter

    adapter = BacnetAdapter(
        address="127.0.0.1/32",
        port=_free_udp_port(),
        device_instance_base=100000,
        network=NETWORK,
    )
    await adapter.start()
    assert adapter.get_status()["running"] is True
    try:
        yield adapter
    finally:
        await adapter.stop()


def _regs():
    from app.protocols.base import RegisterInfo

    return [RegisterInfo(0, 3, "float32", "big_endian", name="voltage", unit="V")]


def _set_fault(device_id, fault_type: str, params: dict | None = None) -> None:
    from app.simulation import fault_simulator
    from app.simulation.fault_simulator import FaultConfig

    fault_simulator.set_fault(device_id, FaultConfig(fault_type=fault_type, params=params or {}))


class TestBacnetReadFaults:
    async def test_exception_fault_returns_bacnet_error(self):
        from bacpypes3.apdu import ErrorRejectAbortNack
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "exception")
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                with pytest.raises(ErrorRejectAbortNack) as exc_info:
                    await client.read_property(
                        addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                    )
                assert "operational-problem" in str(exc_info.value)
            stats = adapter.get_stats(device_id)
            assert stats.error_count >= 1

    async def test_timeout_fault_drops_response(self):
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "timeout")
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        client.read_property(
                            addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                        ),
                        timeout=2,
                    )
            stats = adapter.get_stats(device_id)
            assert stats.request_count >= 1
            assert stats.error_count >= 1
            assert stats.success_count == 0

    async def test_delay_fault_postpones_response(self):
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            await adapter.update_register(device_id, 0, 3, 230.0, "float32", "big_endian")
            _set_fault(device_id, "delay", {"delay_ms": 1000})
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                t0 = time.monotonic()
                value = await client.read_property(
                    addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                )
                elapsed = time.monotonic() - t0
                assert elapsed >= 1.0
                assert abs(float(value) - 230.0) < 0.01

    async def test_intermittent_rate_one_always_drops(self):
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "intermittent", {"failure_rate": 1.0})
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        client.read_property(
                            addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                        ),
                        timeout=2,
                    )

    async def test_intermittent_rate_zero_always_serves(self):
        from bacpypes3.primitivedata import ObjectIdentifier

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "intermittent", {"failure_rate": 0.0})
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                value = await client.read_property(
                    addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                )
                assert value is not None

    async def test_clear_fault_recovers(self):
        from bacpypes3.primitivedata import ObjectIdentifier

        from app.simulation import fault_simulator

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "timeout")
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        client.read_property(
                            addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                        ),
                        timeout=2,
                    )
                fault_simulator.clear_fault(device_id)
                value = await client.read_property(
                    addr, ObjectIdentifier(("analog-input", 0)), "present-value"
                )
                assert value is not None

    async def test_rpm_also_gated(self):
        """ReadPropertyMultiple goes through the same gate as ReadProperty."""
        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "timeout")
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        client.read_property_multiple(
                            addr, ["analog-input,0", ["present-value"]]
                        ),
                        timeout=2,
                    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTEST tests/test_bacnet_fault.py::TestBacnetReadFaults -v`
Expected: FAIL — exception test gets a value instead of `ErrorRejectAbortNack`; timeout test gets a response instead of `asyncio.TimeoutError`. (`test_intermittent_rate_zero_always_serves`, `test_delay…` may pass trivially — fine.)

- [ ] **Step 3: Implement the fault gate in `_DeviceApplication`**

In `backend/app/protocols/bacnet_agent.py`:

(a) Add to the stdlib imports at the top (after `import ipaddress`):

```python
import asyncio
```

and (after `import math`):

```python
import random
```

(b) Add `_drop_for_fault` to `_DeviceApplication` (below `_count`):

```python
    async def _drop_for_fault(self) -> bool:
        """Pull-based comm-fault gate for confirmed read requests.

        Returns True when the request must be dropped (timeout / intermittent
        — the client sees a timeout). Sleeps for delay faults and raises
        ExecutionError for exception faults (bacpypes3 converts it to a BACnet
        Error APDU, same path as the WriteProperty rejection).
        """
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import get_delay_seconds, get_failure_rate

        fault = fault_simulator.get_fault(self._ghost_device_id)
        if fault is None:
            return False
        if fault.fault_type == "timeout":
            return True
        if fault.fault_type == "intermittent":
            return random.random() < get_failure_rate(fault.params)
        if fault.fault_type == "delay":
            await asyncio.sleep(get_delay_seconds(fault.params))
            return False
        if fault.fault_type == "exception":
            raise ExecutionError(errorClass="device", errorCode="operationalProblem")
        return False
```

(c) Replace the two read handlers so the gate runs inside the stats try-block:

```python
    async def do_ReadPropertyRequest(self, apdu) -> None:
        t0 = time.monotonic()
        try:
            if await self._drop_for_fault():
                self._count(t0, success=False)
                return
            await super().do_ReadPropertyRequest(apdu)
        except Exception:
            self._count(t0, success=False)
            raise
        self._count(t0, success=True)

    async def do_ReadPropertyMultipleRequest(self, apdu) -> None:
        t0 = time.monotonic()
        try:
            if await self._drop_for_fault():
                self._count(t0, success=False)
                return
            await super().do_ReadPropertyMultipleRequest(apdu)
        except Exception:
            self._count(t0, success=False)
            raise
        self._count(t0, success=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests/test_bacnet_fault.py::TestBacnetReadFaults -v`
Expected: 7 PASS

- [ ] **Step 5: Run the existing BACnet suite for regressions**

Run: `PYTEST tests/test_bacnet_adapter.py -v`
Expected: 17 PASS (no behavior change without an active fault)

- [ ] **Step 6: Commit**

```bash
git add backend/app/protocols/bacnet_agent.py backend/tests/test_bacnet_fault.py
git commit -m "feat: BACnet comm-layer fault simulation on the read path"
```

---

### Task 3: BACnet Who-Is suppression

**Files:**
- Modify: `backend/app/protocols/bacnet_agent.py` (`_DeviceApplication`)
- Test: `backend/tests/test_bacnet_fault.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_bacnet_fault.py`:

```python
class TestBacnetWhoIsFault:
    async def test_whois_suppressed_under_timeout(self):
        from bacpypes3.pdu import Address

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "timeout")
            async with _client_app() as client:
                addr = Address(f"{NETWORK}:*@127.0.0.1:{adapter._port}")
                # who_is resolves on first I-Am for low==high, else waits its
                # internal window (~3 s) and returns whatever arrived: nothing.
                i_ams = await client.who_is(100001, 100001, addr)
                assert i_ams == []

    async def test_whois_recovers_after_clear(self):
        from bacpypes3.pdu import Address

        from app.simulation import fault_simulator

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "timeout")
            fault_simulator.clear_fault(device_id)
            async with _client_app() as client:
                addr = Address(f"{NETWORK}:*@127.0.0.1:{adapter._port}")
                i_ams = await client.who_is(100001, 100001, addr)
                assert len(i_ams) == 1
                assert i_ams[0].iAmDeviceIdentifier[1] == 100001

    async def test_whois_unaffected_by_delay_fault(self):
        """Only timeout/intermittent make the device go dark; delay applies to reads."""
        from bacpypes3.pdu import Address

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            _set_fault(device_id, "delay", {"delay_ms": 5000})
            async with _client_app() as client:
                addr = Address(f"{NETWORK}:*@127.0.0.1:{adapter._port}")
                i_ams = await asyncio.wait_for(client.who_is(100001, 100001, addr), timeout=4)
                assert len(i_ams) == 1
```

- [ ] **Step 2: Run tests to verify the suppression test fails**

Run: `PYTEST tests/test_bacnet_fault.py::TestBacnetWhoIsFault -v`
Expected: `test_whois_suppressed_under_timeout` FAILS (I-Am still answered); the other two pass.

- [ ] **Step 3: Implement `do_WhoIsRequest` override**

Add to `_DeviceApplication` in `backend/app/protocols/bacnet_agent.py` (after `do_WritePropertyRequest`):

```python
    async def do_WhoIsRequest(self, apdu) -> None:
        """A device under timeout/intermittent fault goes fully dark (no I-Am),
        like a real dead device. delay/exception only affect reads."""
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import get_failure_rate

        fault = fault_simulator.get_fault(self._ghost_device_id)
        if fault is not None:
            if fault.fault_type == "timeout":
                return
            if fault.fault_type == "intermittent" and random.random() < get_failure_rate(
                fault.params
            ):
                return
        await super().do_WhoIsRequest(apdu)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests/test_bacnet_fault.py -v`
Expected: ALL PASS (read faults + Who-Is)

- [ ] **Step 5: Commit**

```bash
git add backend/app/protocols/bacnet_agent.py backend/tests/test_bacnet_fault.py
git commit -m "feat: BACnet Who-Is suppression under timeout/intermittent faults"
```

---

### Task 4: BACnet REST e2e (API set/clear fault → real client observes it)

**Files:**
- Test: `backend/tests/test_bacnet_fault.py` (append)

This works because `fault_simulator` is a process-global singleton: the API route writes it and a manually started adapter in the same test process reads it. The httpx ASGI client doesn't run the app lifespan, so the adapter is started by the test, and the device created via REST is registered on it by the test using the API-returned device id.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_bacnet_fault.py`:

```python
BACNET_TEMPLATE_PAYLOAD = {
    "name": "BACnet Fault E2E Meter",
    "protocol": "bacnet",
    "registers": [
        {
            "name": "voltage",
            "address": 0,
            "function_code": 3,
            "data_type": "float32",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "V",
            "description": "Voltage",
            "sort_order": 0,
        },
    ],
}


class TestBacnetFaultRestE2E:
    async def test_set_and_clear_fault_via_api(self, client):
        from bacpypes3.primitivedata import ObjectIdentifier

        resp = await client.post("/api/v1/templates", json=BACNET_TEMPLATE_PAYLOAD)
        assert resp.status_code == 201
        template_id = resp.json()["data"]["id"]

        resp = await client.post(
            "/api/v1/devices",
            json={"template_id": template_id, "name": "E2E BACnet", "slave_id": 60},
        )
        assert resp.status_code == 201
        device_id = uuid.UUID(resp.json()["data"]["id"])

        async with _running_adapter() as adapter:
            await adapter.add_device(device_id, 60, _regs())
            async with _client_app() as bn_client:
                addr = _device_addr(adapter._port, 60)
                ai0 = ObjectIdentifier(("analog-input", 0))

                # Healthy read first
                assert await bn_client.read_property(addr, ai0, "present-value") is not None

                # Set timeout fault through the REST API
                resp = await client.put(
                    f"/api/v1/devices/{device_id}/fault",
                    json={"fault_type": "timeout", "params": {}},
                )
                assert resp.status_code == 200
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        bn_client.read_property(addr, ai0, "present-value"), timeout=2
                    )

                # Clear through the REST API → recovers
                resp = await client.delete(f"/api/v1/devices/{device_id}/fault")
                assert resp.status_code == 200
                assert await bn_client.read_property(addr, ai0, "present-value") is not None
```

- [ ] **Step 2: Run the test**

Run: `PYTEST tests/test_bacnet_fault.py::TestBacnetFaultRestE2E -v`
Expected: PASS already (Tasks 2–3 implemented the behavior; this verifies the REST seam). If it fails, the seam is broken — fix before continuing.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_bacnet_fault.py
git commit -m "test: BACnet fault REST e2e (API set/clear observed by real client)"
```

---

### Task 5: SNMP exception fault → genErr

**Files:**
- Modify: `backend/app/protocols/snmp_agent.py` (`_DynamicMibController`)
- Create: `backend/tests/test_snmp_fault.py`

- [ ] **Step 1: Create the test file with the exception test**

Create `backend/tests/test_snmp_fault.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify the genErr test fails**

Run: `PYTEST tests/test_snmp_fault.py::TestSnmpExceptionFault -v`
Expected: `test_exception_fault_returns_gen_err` FAILS (errorStatus 0, value served); recovery test passes trivially.

- [ ] **Step 3: Implement the exception hook in `_DynamicMibController`**

In `backend/app/protocols/snmp_agent.py`:

(a) Add to the third-party imports (after the existing `pysnmp` imports):

```python
from pysnmp.smi import error as smi_error
```

(b) Add a helper method to `_DynamicMibController` (after `__init__`):

```python
    def _raise_for_exception_fault(self, oid: str) -> None:
        """Raise GenError when the OID's device has an active `exception` fault.

        process_pdu's SmiError handler maps GenError to a genErr response
        (pysnmp SMI_ERROR_MAP), so the client receives a protocol-level error
        instead of a value.
        """
        from app.simulation import fault_simulator

        entry = self._adapter._oid_map.get(oid)
        if entry is None:
            return
        fault = fault_simulator.get_fault(entry[0])
        if fault is not None and fault.fault_type == "exception":
            raise smi_error.GenError()
```

(c) In `read_variables`, call it right after computing `oid`:

```python
        for name, _ in var_binds:
            oid = ".".join(str(x) for x in name)
            self._raise_for_exception_fault(oid)
            value, data_type = self._adapter.resolve_oid(oid)
```

(d) In `read_next_variables`, call it on the resolved next OID, inside the `while` loop right before `resolve_oid`:

```python
            while nxt is not None:
                self._raise_for_exception_fault(nxt)
                value, data_type = self._adapter.resolve_oid(nxt)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests/test_snmp_fault.py -v`
Expected: 2 PASS

- [ ] **Step 5: Run existing SNMP suite for regressions**

Run: `PYTEST tests/test_snmp.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/protocols/snmp_agent.py backend/tests/test_snmp_fault.py
git commit -m "feat: SNMP exception fault returns genErr"
```

---

### Task 6: SNMP drop/delay via fault-aware command responders

**Files:**
- Modify: `backend/app/protocols/snmp_agent.py`
- Test: `backend/tests/test_snmp_fault.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_snmp_fault.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTEST tests/test_snmp_fault.py::TestSnmpDropAndDelayFaults -v`
Expected: timeout/getnext/intermittent-1.0 FAIL (response still arrives); delay FAILS on `elapsed >= 1.2`; rate-zero and recovery pass trivially.

- [ ] **Step 3: Implement the fault-aware responders**

In `backend/app/protocols/snmp_agent.py`:

(a) Add stdlib imports at the top (before `import bisect`):

```python
import asyncio
import random
```

(b) Add the mixin and subclasses after `_DynamicMibController` (before `class SnmpAdapter`):

```python
class _FaultAwareResponderMixin:
    """process_pdu override that consults fault_simulator before responding.

    timeout / intermittent → drop the request (no response datagram; the
    client times out). delay → defer the entire synchronous response pipeline
    with call_later (process_pdu and everything below it is sync and ends in
    a sendto, so deferring the whole call never blocks the event loop).
    exception → falls through; _DynamicMibController raises GenError → genErr.
    """

    _ghost_adapter: "SnmpAdapter | None" = None

    def process_pdu(
        self,
        snmpEngine,
        messageProcessingModel,
        securityModel,
        securityName,
        securityLevel,
        contextEngineId,
        contextName,
        pduVersion,
        PDU,
        maxSizeResponseScopedPDU,
        stateReference,
    ):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import get_delay_seconds, get_failure_rate

        adapter = self._ghost_adapter
        device_id = adapter.resolve_pdu_device(PDU) if adapter is not None else None
        fault = fault_simulator.get_fault(device_id)
        parent_process_pdu = super().process_pdu
        args = (
            snmpEngine, messageProcessingModel, securityModel, securityName,
            securityLevel, contextEngineId, contextName, pduVersion, PDU,
            maxSizeResponseScopedPDU, stateReference,
        )
        if fault is not None:
            if fault.fault_type == "timeout":
                logger.debug("SNMP timeout fault: dropping request for device %s", device_id)
                return
            if fault.fault_type == "intermittent" and random.random() < get_failure_rate(
                fault.params
            ):
                logger.debug("SNMP intermittent fault: dropping request for device %s", device_id)
                return
            if fault.fault_type == "delay":

                def _deferred() -> None:
                    try:
                        parent_process_pdu(*args)
                    except Exception:
                        logger.exception(
                            "Deferred SNMP response failed for device %s", device_id
                        )

                asyncio.get_running_loop().call_later(
                    get_delay_seconds(fault.params), _deferred
                )
                return
        parent_process_pdu(*args)


class _FaultAwareGetCommandResponder(_FaultAwareResponderMixin, cmdrsp.GetCommandResponder):
    pass


class _FaultAwareNextCommandResponder(_FaultAwareResponderMixin, cmdrsp.NextCommandResponder):
    pass


class _FaultAwareBulkCommandResponder(_FaultAwareResponderMixin, cmdrsp.BulkCommandResponder):
    pass
```

(c) In `SnmpAdapter.start()`, replace the three responder registrations:

```python
            cmdrsp.GetCommandResponder(self._snmp_engine, snmp_context)
            cmdrsp.NextCommandResponder(self._snmp_engine, snmp_context)
            cmdrsp.BulkCommandResponder(self._snmp_engine, snmp_context)
```

with:

```python
            responders = (
                _FaultAwareGetCommandResponder(self._snmp_engine, snmp_context),
                _FaultAwareNextCommandResponder(self._snmp_engine, snmp_context),
                _FaultAwareBulkCommandResponder(self._snmp_engine, snmp_context),
            )
            for responder in responders:
                responder._ghost_adapter = self
```

(d) Add `resolve_pdu_device` to `SnmpAdapter` (in the "SNMP-specific methods" section, after `set_register_names`):

```python
    def resolve_pdu_device(self, pdu) -> UUID | None:
        """Map a request PDU to a device via its first resolvable varbind OID.

        GETNEXT/GETBULK requests name a predecessor OID, so fall back to the
        next registered OID. Drop/delay faults act on the whole datagram, so
        the first resolvable device wins (documented limitation for PDUs that
        mix OIDs of multiple devices).
        """
        from pysnmp.proto.api import v2c

        try:
            var_binds = v2c.apiPDU.get_varbinds(pdu)
        except Exception:
            return None
        for name, _value in var_binds:
            oid = ".".join(str(x) for x in name)
            entry = self._oid_map.get(oid)
            if entry is None:
                nxt = self.get_next_oid(oid)
                entry = self._oid_map.get(nxt) if nxt else None
            if entry is not None:
                return entry[0]
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests/test_snmp_fault.py -v`
Expected: 8 PASS (Task 5 + Task 6 tests)

- [ ] **Step 5: Run existing SNMP suite for regressions**

Run: `PYTEST tests/test_snmp.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/protocols/snmp_agent.py backend/tests/test_snmp_fault.py
git commit -m "feat: SNMP timeout/intermittent/delay faults via fault-aware responders"
```

---

### Task 7: MQTT publish-loop faults

**Files:**
- Modify: `backend/app/protocols/mqtt_adapter.py`
- Create: `backend/tests/test_mqtt_fault.py`

- [ ] **Step 1: Create the test file**

Create `backend/tests/test_mqtt_fault.py`:

```python
"""Tests for MQTT comm-layer fault simulation (publish loop with a fake client)."""

import asyncio
import time
import uuid
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean_faults():
    from app.simulation import fault_simulator

    fault_simulator.clear_all()
    yield
    fault_simulator.clear_all()


class _FakeMqttClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, float]] = []

    async def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, time.monotonic()))


def _publish_config(interval: float = 0.05):
    return SimpleNamespace(
        topic_template="ghost/{device_name}",
        payload_mode="batch",
        publish_interval_seconds=interval,
        qos=0,
        retain=False,
    )


def _set_fault(device_id, fault_type: str, params: dict | None = None) -> None:
    from app.simulation import fault_simulator
    from app.simulation.fault_simulator import FaultConfig

    fault_simulator.set_fault(device_id, FaultConfig(fault_type=fault_type, params=params or {}))


async def _publishing_adapter(monkeypatch, device_id):
    """An MqttAdapter publishing every 50 ms to a fake in-memory client."""
    from app.protocols.base import RegisterInfo
    from app.protocols.mqtt_adapter import MqttAdapter
    from app.simulation import simulation_engine

    monkeypatch.setattr(
        simulation_engine,
        "get_current_values",
        lambda did: {"voltage": 220.0} if did == device_id else {},
    )
    adapter = MqttAdapter()
    adapter._connected = True
    adapter._available = True
    adapter._client = _FakeMqttClient()
    await adapter.add_device(
        device_id, 1, [RegisterInfo(0, 3, "float32", "big_endian", name="voltage")]
    )
    adapter.set_device_meta(device_id, "FaultMeter", 1, "TestTemplate")
    await adapter.start_publishing(device_id, _publish_config())
    return adapter


class TestMqttPublishFaults:
    async def test_baseline_publishes_flow(self, monkeypatch):
        device_id = uuid.uuid4()
        adapter = await _publishing_adapter(monkeypatch, device_id)
        try:
            await asyncio.sleep(0.4)
            assert len(adapter._client.published) >= 3
        finally:
            await adapter.stop_publishing(device_id)

    async def test_timeout_fault_stops_publishing(self, monkeypatch):
        device_id = uuid.uuid4()
        adapter = await _publishing_adapter(monkeypatch, device_id)
        try:
            _set_fault(device_id, "timeout")
            await asyncio.sleep(0.2)  # let any in-flight iteration drain
            count_after_settle = len(adapter._client.published)
            errors_before = adapter.get_stats(device_id).error_count
            await asyncio.sleep(0.4)
            assert len(adapter._client.published) == count_after_settle
            assert adapter.get_stats(device_id).error_count > errors_before
        finally:
            await adapter.stop_publishing(device_id)

    async def test_intermittent_rate_one_stops_rate_zero_flows(self, monkeypatch):
        device_id = uuid.uuid4()
        adapter = await _publishing_adapter(monkeypatch, device_id)
        try:
            _set_fault(device_id, "intermittent", {"failure_rate": 1.0})
            await asyncio.sleep(0.2)
            count = len(adapter._client.published)
            await asyncio.sleep(0.4)
            assert len(adapter._client.published) == count

            _set_fault(device_id, "intermittent", {"failure_rate": 0.0})
            await asyncio.sleep(0.4)
            assert len(adapter._client.published) > count
        finally:
            await adapter.stop_publishing(device_id)

    async def test_delay_fault_spaces_out_publishes(self, monkeypatch):
        device_id = uuid.uuid4()
        adapter = await _publishing_adapter(monkeypatch, device_id)
        try:
            _set_fault(device_id, "delay", {"delay_ms": 300})
            await asyncio.sleep(1.0)
            stamps = [t for _, _, t in adapter._client.published]
            # Find at least two publishes emitted while the fault was active
            # and check their spacing reflects interval (0.05) + delay (0.3).
            faulted_gaps = [
                b - a for a, b in zip(stamps, stamps[1:]) if (b - a) >= 0.3
            ]
            assert faulted_gaps, "expected at least one delayed publish gap >= 0.3s"
        finally:
            await adapter.stop_publishing(device_id)

    async def test_clear_fault_resumes_publishing(self, monkeypatch):
        from app.simulation import fault_simulator

        device_id = uuid.uuid4()
        adapter = await _publishing_adapter(monkeypatch, device_id)
        try:
            _set_fault(device_id, "timeout")
            await asyncio.sleep(0.2)
            count = len(adapter._client.published)
            fault_simulator.clear_fault(device_id)
            await asyncio.sleep(0.4)
            assert len(adapter._client.published) > count
        finally:
            await adapter.stop_publishing(device_id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTEST tests/test_mqtt_fault.py -v`
Expected: baseline PASSES; timeout / intermittent-1.0 / delay / recovery FAIL (publishes keep flowing unfaulted).

- [ ] **Step 3: Implement the fault check in `_publish_loop`**

In `backend/app/protocols/mqtt_adapter.py`:

(a) Add to the stdlib imports at the top (after `import json`):

```python
import random
```

(b) In `_publish_loop`, extend the lazy import at the top of the method:

```python
        from app.simulation import fault_simulator, simulation_engine
        from app.simulation.fault_simulator import get_delay_seconds, get_failure_rate
```

(c) Insert the fault gate right after `await asyncio.sleep(interval)` (before the broker-connected check):

```python
                fault = fault_simulator.get_fault(device_id)
                if fault is not None:
                    if fault.fault_type == "timeout" or (
                        fault.fault_type == "intermittent"
                        and random.random() < get_failure_rate(fault.params)
                    ):
                        stats = self._device_stats.get(device_id)
                        if stats:
                            stats.request_count += 1
                            stats.error_count += 1
                        continue
                    if fault.fault_type == "delay":
                        await asyncio.sleep(get_delay_seconds(fault.params))
                    # "exception" is rejected at the REST layer for MQTT devices
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests/test_mqtt_fault.py -v`
Expected: 5 PASS

- [ ] **Step 5: Run existing MQTT suites for regressions**

Run: `PYTEST tests/test_mqtt.py tests/test_mqtt_export_import.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/protocols/mqtt_adapter.py backend/tests/test_mqtt_fault.py
git commit -m "feat: MQTT publish-loop fault simulation (timeout/intermittent/delay)"
```

---

### Task 8: REST validation — MQTT + exception → 422

**Files:**
- Modify: `backend/app/api/routes/simulation.py`
- Test: `backend/tests/test_simulation_api.py` (append to `TestFaultControl`)

- [ ] **Step 1: Write the failing test**

Append to `class TestFaultControl` in `backend/tests/test_simulation_api.py`:

```python
    async def test_put_exception_fault_on_mqtt_device_rejected(self, client: AsyncClient) -> None:
        """MQTT is publish-only — no request/response channel for an error, so
        the exception fault type is rejected with 422 and no state is left behind."""
        mqtt_template = {**TEMPLATE_PAYLOAD, "name": "MQTT Fault Template", "protocol": "mqtt"}
        resp = await client.post("/api/v1/templates", json=mqtt_template)
        assert resp.status_code == 201
        template_id = resp.json()["data"]["id"]

        resp = await client.post(
            "/api/v1/devices",
            json={"template_id": template_id, "name": "MQTT Fault Device", "slave_id": 11},
        )
        assert resp.status_code == 201
        device_id = resp.json()["data"]["id"]

        resp = await client.put(
            f"/api/v1/devices/{device_id}/fault",
            json={"fault_type": "exception", "params": {}},
        )
        assert resp.status_code == 422
        assert resp.json()["error_code"] == "VALIDATION_ERROR"

        # No orphan fault state was created
        resp = await client.get(f"/api/v1/devices/{device_id}/fault")
        assert resp.json()["data"] is None

        # The other fault types remain accepted for MQTT devices
        resp = await client.put(
            f"/api/v1/devices/{device_id}/fault",
            json={"fault_type": "timeout", "params": {}},
        )
        assert resp.status_code == 200
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTEST tests/test_simulation_api.py::TestFaultControl::test_put_exception_fault_on_mqtt_device_rejected -v`
Expected: FAIL — PUT returns 200, not 422

- [ ] **Step 3: Implement the validation**

In `backend/app/api/routes/simulation.py`:

(a) Add the import (after `from app.database import get_session`):

```python
from app.exceptions import ValidationException
```

(b) In `set_fault`, right after `protocol = await device_service.get_device_protocol(session, device_id)`:

```python
    if protocol == "mqtt" and data.fault_type == "exception":
        raise ValidationException(
            detail="Fault type 'exception' is not supported for MQTT devices: "
            "MQTT is publish-only, so there is no request/response channel to "
            "return a protocol error on. Use delay, timeout, or intermittent.",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests/test_simulation_api.py -v`
Expected: ALL PASS (new test + existing fault-control tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/simulation.py backend/tests/test_simulation_api.py
git commit -m "feat: reject exception fault type for MQTT devices (422)"
```

---

### Task 9: Full verification + docs

**Files:**
- Modify: `CHANGELOG.md`, `docs/development-log.md`, `docs/development-phases.md`, `docs/api-reference.md`

- [ ] **Step 1: Run lint + the full backend suite**

```bash
cd backend && ./.venv/bin/python -m ruff check app tests
PYTEST tests/ -x -q
```

Expected: ruff clean; full suite PASS (~229 pre-existing + ~23 new). Fix anything that breaks before touching docs.

- [ ] **Step 2: Update CHANGELOG.md**

Add to the top of the `## [Unreleased]` → `### Added` section:

```markdown
- Comm-layer fault simulation for BACnet, SNMP, and MQTT — all five protocols now support `delay` / `timeout` / `intermittent` faults through `PUT /devices/{id}/fault` (pull-based, same model as Modbus). BACnet: faulted devices also stop answering Who-Is (fully dark, like a real dead device); `exception` maps to BACnet Error `device/operationalProblem`. SNMP: `exception` maps to `genErr`; delayed responses are deferred without blocking the event loop. MQTT: `timeout` stops publishing, `intermittent` randomly skips publishes, `delay` publishes late; `exception` is rejected with 422 (publish-only protocols have no request/response channel to return an error on).
```

- [ ] **Step 3: Update docs/development-phases.md**

Add after Milestone 8.11:

```markdown
### Milestone 8.12：SNMP / MQTT / BACnet 故障模擬 ✅ Complete (2026-06-11)
- [x] Shared fault-param helpers in `fault_simulator.py` (`get_delay_seconds` cap 10 s, `get_failure_rate` clamp 0–1)
- [x] BACnet: pull-based fault gate in `_DeviceApplication` (ReadProperty / RPM); `exception` → Error `device/operationalProblem`; timeout/intermittent also suppress Who-Is (device goes fully dark)
- [x] SNMP: fault-aware command responders (timeout/intermittent drop, delay deferred via `loop.call_later` — non-blocking); `exception` → `genErr` via `_DynamicMibController`
- [x] MQTT: `_publish_loop` gate — timeout stops publishing, intermittent skips probabilistically, delay publishes late; `exception` rejected at REST (422)
- [x] REST: `PUT /devices/{id}/fault` validates MQTT + exception → 422; API otherwise unchanged
- [x] Tests: `test_bacnet_fault.py` (real bacpypes3 client incl. REST e2e), `test_snmp_fault.py` (real GET/GETNEXT incl. loop-responsiveness check), `test_mqtt_fault.py` (fake-client publish loop), `test_simulation_api.py` 422 case
- **Result:** comm-layer fault simulation now at parity across all 5 protocols (Modbus / OPC UA / SNMP / MQTT / BACnet)
```

Also update Milestone 8.11's deferred line: remove "comm-layer fault simulation" from the BACnet deferred list (now done).

- [ ] **Step 4: Update docs/api-reference.md**

In the fault endpoint section (`PUT /devices/{id}/fault`), add a note:

```markdown
> **Protocol support:** all fault types apply to Modbus TCP, OPC UA, SNMP, and BACnet.
> MQTT supports `delay` / `timeout` / `intermittent` only — `exception` returns
> `422 VALIDATION_ERROR` because MQTT is publish-only (no request/response channel
> to return a protocol error on). For BACnet, `timeout` / `intermittent` also
> suppress Who-Is replies (the device disappears from discovery while faulted).
```

- [ ] **Step 5: Update docs/development-log.md**

Add a dated entry (2026-06-11) summarizing: what was built (fault sim for 3 protocols, pull-based), key decisions (Approach A rationale, MQTT exception rejection, Who-Is suppression), and notable implementation details (pysnmp sync responder path + `call_later` deferral trick; bacpypes3 async handlers allowing plain `await asyncio.sleep`; GenError → genErr mapping verified in pysnmp 7.1.27).

- [ ] **Step 6: Commit docs**

```bash
git add CHANGELOG.md docs/development-log.md docs/development-phases.md docs/api-reference.md
git commit -m "docs: changelog, dev log, phases, API notes for 3-protocol fault simulation"
```

- [ ] **Step 7: Final check before handoff**

```bash
git log --oneline dev..HEAD
```

Expected: ~8 commits (spec + 6 feature/test commits + docs). Branch ready for push + PR after human review. **Do not merge — wait for review per CLAUDE.md workflow.**

---

## Self-review notes

- Spec coverage: Task 1 (helpers/clamps = spec "Error handling"), Tasks 2–4 (BACnet incl. Who-Is + REST e2e), Tasks 5–6 (SNMP exception + drop/delay + GETNEXT resolution), Task 7 (MQTT), Task 8 (422 validation), Task 9 (docs). Stats convention covered in Tasks 2 (BACnet `_count`) and 7 (MQTT counters); SNMP stats explicitly out of scope per spec.
- Timing-sensitive tests use generous margins (1.0–1.2 s delays vs. 50 ms intervals, lower-bound-only assertions) to avoid flakes.
- bacpypes3 fact to verify at Task 2 runtime: an early `return` from `do_ReadPropertyRequest` without calling `response()` must produce no reply (client timeout). The timeout test asserts exactly this; if bacpypes3 auto-replies on return, the test fails loudly and the drop needs to move to a different layer (e.g. raising and suppressing in `indication`). Treat that as a design checkpoint, not a silent workaround.
```
