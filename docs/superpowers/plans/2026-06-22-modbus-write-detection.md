# Modbus Write Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect and record client Modbus write attempts (FC05/06/15/16) on the read-only simulator, surface an unread badge + event list in the UI, so EMS developers can verify their system issued the right writes.

**Architecture:** Accept-and-ignore + record. `trace_pdu` records each write attempt into a per-device in-memory ring buffer (`write_tracker`, N=50, no DB). An unread count + latest event ride the existing 1Hz monitor snapshot. A clean REST pair serves the full list (`GET` pure) and resets unread (`POST .../ack`). UI shows an antd badge on the Monitor device card that opens a Drawer.

**Tech Stack:** Python 3.12 / FastAPI / pymodbus 3.12.1 (async) / SQLAlchemy; React 18 / TypeScript (strict) / Ant Design 5 / Zustand. TDD throughout; backend tests via pytest, frontend gate via `tsc`.

**Spec:** `docs/superpowers/specs/2026-06-22-modbus-write-detection-design.md`

**Branch:** `feature/claude-modbus-write-detection-20260612` (worktree, based on 0.4.3 dev)

**Verified facts (from codebase + library introspection):**
- pymodbus 3.12.1 write request PDUs expose: `.function_code`, `.address`, `.dev_id`, `.transaction_id`. Register writes (FC6/16) carry values in `.registers` (list[int]); coil writes (FC5/15) carry them in `.bits` (list[bool]).
- `trace_pdu` runs on the asyncio event loop (server started via `asyncio.create_task(serve_forever())`) — no cross-thread concerns.
- `ModbusTcpAdapter._device_registers: dict[UUID, list[RegisterInfo]]`; `RegisterInfo` has `.address`, `.function_code` (3=holding, 4=input), `.name: str | None`.
- `_slave_to_device: dict[int, UUID]` resolves the device in `trace_pdu`'s incoming branch.
- Simulation singletons live in `app/simulation/__init__.py` (e.g. `fault_simulator = FaultSimulator()`), imported as `from app.simulation import fault_simulator`.
- Monitor snapshot device dict is built in `monitor_service.get_snapshot` (per-device dict around line 142); imports `from app.simulation import anomaly_injector, fault_simulator, simulation_engine` at the top of the method.
- Device sub-resource routes mounted with `prefix="/devices"` in `main.py`; `device_service.get_device_protocol(session, device_id)` 404s on unknown device.
- Frontend types are a named-export barrel in `types/index.ts`; monitor types in `types/monitor.ts`; API clients in `services/*Api.ts` use the shared `api` axios instance.

---

## Task 1: `write_tracker` module + singleton

**Files:**
- Create: `backend/app/simulation/write_tracker.py`
- Modify: `backend/app/simulation/__init__.py`
- Test: `backend/tests/test_write_tracker.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_write_tracker.py`:

```python
"""Unit tests for the in-memory write tracker."""

from uuid import uuid4

from app.simulation.write_tracker import WriteTracker


def test_record_and_get_events_newest_first():
    t = WriteTracker()
    dev = uuid4()
    t.record(dev, function_code=6, address=10, values=[111], register_name="setpoint")
    t.record(dev, function_code=16, address=20, values=[1, 2], register_name=None)

    events = t.get_events(dev)
    assert [e.address for e in events] == [20, 10]  # newest first
    assert events[1].register_name == "setpoint"
    assert events[0].values == [1, 2]
    assert events[0].function_code == 16


def test_unread_increments_and_mark_read_resets():
    t = WriteTracker()
    dev = uuid4()
    assert t.get_unread_count(dev) == 0
    t.record(dev, function_code=6, address=1, values=[1], register_name=None)
    t.record(dev, function_code=6, address=2, values=[2], register_name=None)
    assert t.get_unread_count(dev) == 2
    t.mark_read(dev)
    assert t.get_unread_count(dev) == 0
    # buffer retained after mark_read
    assert len(t.get_events(dev)) == 2


def test_ring_buffer_caps_at_max():
    t = WriteTracker()
    dev = uuid4()
    for i in range(60):
        t.record(dev, function_code=6, address=i, values=[i], register_name=None)
    events = t.get_events(dev)
    assert len(events) == 50  # MAX_EVENTS_PER_DEVICE
    assert events[0].address == 59  # newest kept
    assert events[-1].address == 10  # oldest 10 dropped


def test_latest_returns_most_recent_or_none():
    t = WriteTracker()
    dev = uuid4()
    assert t.latest(dev) is None
    t.record(dev, function_code=6, address=7, values=[7], register_name="x")
    assert t.latest(dev).address == 7


def test_clear_removes_device_state():
    t = WriteTracker()
    dev = uuid4()
    t.record(dev, function_code=6, address=1, values=[1], register_name=None)
    t.clear(dev)
    assert t.get_events(dev) == []
    assert t.get_unread_count(dev) == 0
    assert t.latest(dev) is None


def test_values_are_copied_not_aliased():
    t = WriteTracker()
    dev = uuid4()
    src = [1, 2]
    t.record(dev, function_code=16, address=0, values=src, register_name=None)
    src.append(3)
    assert t.get_events(dev)[0].values == [1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_write_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.simulation.write_tracker'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/simulation/write_tracker.py`:

```python
"""In-memory tracker for client write attempts against the read-only simulator.

Protocol-agnostic so issue #72 can reuse it for OPC UA / BACnet. In-memory
only — no DB persistence; cleared on device stop and server restart.
"""

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

logger = logging.getLogger(__name__)

MAX_EVENTS_PER_DEVICE = 50


@dataclass(frozen=True)
class WriteEvent:
    """A single recorded client write attempt."""

    timestamp: datetime          # UTC
    function_code: int           # 5 / 6 / 15 / 16
    address: int                 # starting address
    values: list[int]            # raw 16-bit words; coils as 0 | 1
    register_name: str | None    # resolved template register name, or None


class WriteTracker:
    """Per-device ring buffer of client write attempts. In-memory only."""

    def __init__(self) -> None:
        self._buffers: dict[UUID, deque[WriteEvent]] = {}
        self._unread: dict[UUID, int] = {}

    def record(
        self,
        device_id: UUID,
        function_code: int,
        address: int,
        values: list[int],
        register_name: str | None = None,
    ) -> None:
        """Append a write event and bump the device's unread count."""
        buf = self._buffers.get(device_id)
        if buf is None:
            buf = deque(maxlen=MAX_EVENTS_PER_DEVICE)
            self._buffers[device_id] = buf
        buf.append(
            WriteEvent(
                timestamp=datetime.now(timezone.utc),
                function_code=function_code,
                address=address,
                values=list(values),
                register_name=register_name,
            )
        )
        self._unread[device_id] = self._unread.get(device_id, 0) + 1

    def get_events(self, device_id: UUID) -> list[WriteEvent]:
        """Return events newest-first."""
        buf = self._buffers.get(device_id)
        if not buf:
            return []
        return list(reversed(buf))

    def get_unread_count(self, device_id: UUID) -> int:
        return self._unread.get(device_id, 0)

    def latest(self, device_id: UUID) -> WriteEvent | None:
        buf = self._buffers.get(device_id)
        if not buf:
            return None
        return buf[-1]

    def mark_read(self, device_id: UUID) -> None:
        """Reset the unread count; the event buffer is retained."""
        self._unread[device_id] = 0

    def clear(self, device_id: UUID) -> None:
        """Drop all state for one device (on device stop/remove)."""
        self._buffers.pop(device_id, None)
        self._unread.pop(device_id, None)

    def clear_all(self) -> None:
        """Drop all state (used in tests / shutdown)."""
        self._buffers.clear()
        self._unread.clear()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_write_tracker.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Register the singleton**

Modify `backend/app/simulation/__init__.py` to add the import, instance, and exports:

```python
from app.simulation.anomaly_injector import AnomalyInjector
from app.simulation.engine import SimulationEngine
from app.simulation.fault_simulator import FaultSimulator
from app.simulation.write_tracker import WriteTracker

simulation_engine = SimulationEngine()
fault_simulator = FaultSimulator()
anomaly_injector = AnomalyInjector()
write_tracker = WriteTracker()

__all__ = [
    "simulation_engine",
    "fault_simulator",
    "anomaly_injector",
    "write_tracker",
    "SimulationEngine",
    "FaultSimulator",
    "AnomalyInjector",
    "WriteTracker",
]
```

- [ ] **Step 6: Verify the singleton imports**

Run: `cd backend && python -c "from app.simulation import write_tracker; print(type(write_tracker).__name__)"`
Expected: prints `WriteTracker`

- [ ] **Step 7: Commit**

```bash
git add backend/app/simulation/write_tracker.py backend/app/simulation/__init__.py backend/tests/test_write_tracker.py
git commit -m "feat: in-memory write_tracker ring buffer (#71)"
```

---

## Task 2: Record writes in `trace_pdu`

**Files:**
- Modify: `backend/app/protocols/modbus_tcp.py` (trace_pdu incoming branch + two helpers + clear hooks)
- Test: `backend/tests/test_modbus_write_detection.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/test_modbus_write_detection.py`:

```python
"""Integration tests for Modbus client write detection.

Starts a real ModbusTcpAdapter and uses a pymodbus AsyncModbusTcpClient to
issue writes, then asserts they were recorded by write_tracker.
"""

from uuid import uuid4

import pytest
from pymodbus.client import AsyncModbusTcpClient

from app.protocols.base import RegisterInfo
from app.protocols.modbus_tcp import ModbusTcpAdapter
from app.simulation import write_tracker

MODBUS_PORT = 15602
DEVICE_ID = uuid4()
SLAVE_ID = 1
SETPOINT_ADDR = 4


@pytest.fixture
async def adapter():
    adapter = ModbusTcpAdapter(host="127.0.0.1", port=MODBUS_PORT)
    await adapter.start()
    reg = RegisterInfo(
        address=SETPOINT_ADDR,
        function_code=3,
        data_type="uint16",
        byte_order="big_endian",
        name="power_setpoint",
    )
    await adapter.add_device(DEVICE_ID, SLAVE_ID, [reg])
    yield adapter
    write_tracker.clear_all()
    await adapter.stop()


@pytest.fixture
async def client(adapter):
    cli = AsyncModbusTcpClient("127.0.0.1", port=MODBUS_PORT, timeout=5)
    await cli.connect()
    yield cli
    cli.close()


async def test_fc6_single_register_write_recorded(client):
    result = await client.write_register(SETPOINT_ADDR, 1234, device_id=SLAVE_ID)
    assert not result.isError()

    events = write_tracker.get_events(DEVICE_ID)
    assert len(events) == 1
    assert events[0].function_code == 6
    assert events[0].address == SETPOINT_ADDR
    assert events[0].values == [1234]
    assert events[0].register_name == "power_setpoint"
    assert write_tracker.get_unread_count(DEVICE_ID) == 1


async def test_fc16_multi_register_write_recorded(client):
    result = await client.write_registers(SETPOINT_ADDR, [11, 22], device_id=SLAVE_ID)
    assert not result.isError()

    events = write_tracker.get_events(DEVICE_ID)
    assert len(events) == 1
    assert events[0].function_code == 16
    assert events[0].address == SETPOINT_ADDR
    assert events[0].values == [11, 22]


async def test_coil_write_recorded_even_when_address_illegal(client):
    # No coil datastore exists, so the response is an error — but the attempt
    # is still recorded (trace_pdu sees the incoming request first).
    await client.write_coil(0, True, device_id=SLAVE_ID)

    events = write_tracker.get_events(DEVICE_ID)
    assert len(events) == 1
    assert events[0].function_code == 5
    assert events[0].values == [1]
    assert events[0].register_name is None


async def test_unknown_address_records_with_null_name(client):
    await client.write_register(999, 7, device_id=SLAVE_ID)
    events = write_tracker.get_events(DEVICE_ID)
    assert len(events) == 1
    assert events[0].address == 999
    assert events[0].register_name is None


async def test_read_does_not_record(client):
    await client.read_holding_registers(SETPOINT_ADDR, count=1, device_id=SLAVE_ID)
    assert write_tracker.get_events(DEVICE_ID) == []


async def test_clear_on_remove_device(adapter, client):
    await client.write_register(SETPOINT_ADDR, 1, device_id=SLAVE_ID)
    assert write_tracker.get_unread_count(DEVICE_ID) == 1
    await adapter.remove_device(DEVICE_ID)
    assert write_tracker.get_events(DEVICE_ID) == []


async def test_write_recorded_even_when_timeout_fault_active(adapter, client):
    # The write attempt is recorded before the timeout fault suppresses the
    # slave, so the user still sees that the client issued the write.
    from app.simulation import fault_simulator
    from app.simulation.fault_simulator import FaultConfig

    fault_simulator.set_fault(DEVICE_ID, FaultConfig(fault_type="timeout", params={}))
    try:
        await client.write_register(SETPOINT_ADDR, 55, device_id=SLAVE_ID)
    except Exception:
        pass  # timeout fault suppresses the response — client may raise/time out
    finally:
        fault_simulator.clear_all()

    events = write_tracker.get_events(DEVICE_ID)
    assert len(events) == 1
    assert events[0].values == [55]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_modbus_write_detection.py -v`
Expected: FAIL — writes are not recorded (`len(events) == 0`).

- [ ] **Step 3: Add the recording helpers**

In `backend/app/protocols/modbus_tcp.py`, add two methods to `ModbusTcpAdapter` (place them right after `_create_trace_pdu`, before `_suppress_slave`):

```python
    def _lookup_register_name(
        self, device_id: UUID, function_code: int, address: int
    ) -> str | None:
        """Resolve a write target to a template register name, or None.

        Write FC 6/16 target holding registers (RegisterInfo.function_code == 3);
        FC 5/15 target coils, which builtin templates don't define.
        """
        if function_code not in (6, 16):
            return None
        for reg in self._device_registers.get(device_id, []):
            if reg.function_code == 3 and reg.address == address:
                return reg.name
        return None

    def _record_write(self, device_id: UUID, pdu) -> None:
        """Record a client write attempt. Must never raise into the serving path."""
        try:
            from app.simulation import write_tracker

            fc = pdu.function_code
            if fc in (6, 16):
                values = list(pdu.registers)
            else:  # 5, 15 — coils
                values = [1 if b else 0 for b in pdu.bits]
            register_name = self._lookup_register_name(device_id, fc, pdu.address)
            write_tracker.record(device_id, fc, pdu.address, values, register_name)
        except Exception:  # pragma: no cover — defensive; must not break the response
            logger.warning("Failed to record write event for %s", device_id, exc_info=True)
```

- [ ] **Step 4: Call the recorder from the incoming branch**

In `_create_trace_pdu`'s `trace_pdu`, inside the incoming `if dev_id is not None:` block (after the stats increment, alongside the fault checks), add:

```python
                    # Record client write attempts (read-only sim: accept + record)
                    if pdu.function_code in (5, 6, 15, 16):
                        self._record_write(dev_id, pdu)
```

The block now reads (for orientation — the new two lines sit after `stats.request_count += 1`):

```python
                if dev_id is not None:
                    self._request_start_times[pdu.transaction_id] = time.monotonic()
                    stats = self._device_stats.get(dev_id)
                    if stats:
                        stats.request_count += 1

                    # Record client write attempts (read-only sim: accept + record)
                    if pdu.function_code in (5, 6, 15, 16):
                        self._record_write(dev_id, pdu)

                    from app.simulation import fault_simulator
                    ...
```

- [ ] **Step 5: Clear tracker state on device removal and stop**

In `_do_remove_device`, after `self._device_registers.pop(device_id, None)`:

```python
        from app.simulation import write_tracker
        write_tracker.clear(device_id)
```

In `stop()`, before the existing `self._device_to_slave.clear()` line:

```python
        from app.simulation import write_tracker
        for device_id in list(self._device_to_slave.values()):
            write_tracker.clear(device_id)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/test_modbus_write_detection.py -v`
Expected: PASS (6 passed)

- [ ] **Step 7: Run the modbus regression tests**

Run: `cd backend && pytest tests/test_modbus.py tests/test_modbus_integration.py tests/test_modbus_fault.py -v`
Expected: PASS (no regressions — write recording is additive)

- [ ] **Step 8: Commit**

```bash
git add backend/app/protocols/modbus_tcp.py backend/tests/test_modbus_write_detection.py
git commit -m "feat: record client write attempts in modbus trace_pdu (#71)"
```

---

## Task 3: Surface write events on the monitor snapshot

**Files:**
- Modify: `backend/app/services/monitor_service.py` (get_snapshot)
- Test: `backend/tests/test_monitor_write_events.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_monitor_write_events.py`:

```python
"""The monitor snapshot must carry per-device write-event summaries."""

from uuid import uuid4

from app.services.monitor_service import MonitorService
from app.simulation import write_tracker


def test_build_write_events_payload_with_events():
    svc = MonitorService()
    dev = uuid4()
    write_tracker.clear_all()
    write_tracker.record(dev, function_code=6, address=4, values=[1234], register_name="sp")

    payload = svc.build_write_events_payload(dev)

    assert payload["unread"] == 1
    assert payload["latest"]["function_code"] == 6
    assert payload["latest"]["address"] == 4
    assert payload["latest"]["values"] == [1234]
    assert payload["latest"]["register_name"] == "sp"
    assert isinstance(payload["latest"]["timestamp"], str)


def test_build_write_events_payload_empty():
    svc = MonitorService()
    dev = uuid4()
    write_tracker.clear_all()
    payload = svc.build_write_events_payload(dev)
    assert payload == {"unread": 0, "latest": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_monitor_write_events.py -v`
Expected: FAIL — `AttributeError: 'MonitorService' object has no attribute 'build_write_events_payload'`

- [ ] **Step 3: Add the payload helper and wire it into the snapshot**

In `backend/app/services/monitor_service.py`, add this method to `MonitorService` (place it just above `get_snapshot`):

```python
    def build_write_events_payload(self, device_id: UUID) -> dict[str, Any]:
        """Per-device write-event summary for the monitor snapshot."""
        from app.simulation import write_tracker

        latest = write_tracker.latest(device_id)
        latest_data = None
        if latest is not None:
            latest_data = {
                "timestamp": latest.timestamp.isoformat(),
                "function_code": latest.function_code,
                "address": latest.address,
                "values": latest.values,
                "register_name": latest.register_name,
            }
        return {
            "unread": write_tracker.get_unread_count(device_id),
            "latest": latest_data,
        }
```

Confirm `UUID` is imported at the top of the file; if not, add `from uuid import UUID`.

Then in `get_snapshot`, in the per-device `devices_data.append({...})` dict, add a new key after `"mqtt_stats": mqtt_stats_data,`:

```python
                "write_events": self.build_write_events_payload(device_id),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_monitor_write_events.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/monitor_service.py backend/tests/test_monitor_write_events.py
git commit -m "feat: add write-event summary to monitor snapshot (#71)"
```

---

## Task 4: REST endpoints (list + ack)

**Files:**
- Create: `backend/app/schemas/write_event.py`
- Create: `backend/app/api/routes/write_events.py`
- Modify: `backend/app/main.py` (import + mount router)
- Test: `backend/tests/test_write_events_api.py`

- [ ] **Step 1: Write the failing API test**

Create `backend/tests/test_write_events_api.py`:

```python
"""API tests for the write-events endpoints."""

import uuid

from httpx import AsyncClient

from app.simulation import write_tracker

TEMPLATE_PAYLOAD = {
    "name": "Write Test Meter",
    "protocol": "modbus_tcp",
    "registers": [
        {
            "name": "power_setpoint",
            "address": 4,
            "function_code": 3,
            "data_type": "uint16",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "W",
            "description": "Setpoint",
            "sort_order": 0,
        },
    ],
}


async def _create_device(client: AsyncClient) -> str:
    """Create a template + device, return the device id (string UUID)."""
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    template_id = resp.json()["data"]["id"]
    resp = await client.post(
        "/api/v1/devices",
        json={"template_id": template_id, "name": "Write Device", "slave_id": 11},
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


async def test_list_returns_events_newest_first_without_resetting_unread(
    client: AsyncClient,
):
    device_id = await _create_device(client)
    dev = uuid.UUID(device_id)  # write_tracker keys on UUID, as the endpoint does
    write_tracker.clear_all()
    write_tracker.record(dev, function_code=6, address=1, values=[10], register_name="a")
    write_tracker.record(dev, function_code=16, address=2, values=[20, 30], register_name=None)

    resp = await client.get(f"/api/v1/devices/{device_id}/write-events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert [e["address"] for e in data] == [2, 1]  # newest first
    assert data[0]["values"] == [20, 30]
    # GET is pure: unread unchanged
    assert write_tracker.get_unread_count(dev) == 2


async def test_ack_resets_unread(client: AsyncClient):
    device_id = await _create_device(client)
    dev = uuid.UUID(device_id)
    write_tracker.clear_all()
    write_tracker.record(dev, function_code=6, address=1, values=[10], register_name=None)
    assert write_tracker.get_unread_count(dev) == 1

    resp = await client.post(f"/api/v1/devices/{device_id}/write-events/ack")
    assert resp.status_code == 200
    assert resp.json()["data"]["unread"] == 0
    assert write_tracker.get_unread_count(dev) == 0


async def test_list_unknown_device_404(client: AsyncClient):
    resp = await client.get(f"/api/v1/devices/{uuid.uuid4()}/write-events")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_write_events_api.py -v`
Expected: FAIL — 404 on the new routes (not mounted) / fixture errors.

- [ ] **Step 3: Create the response schemas**

Create `backend/app/schemas/write_event.py`:

```python
"""Pydantic schemas for the write-events API."""

from datetime import datetime

from pydantic import BaseModel


class WriteEventResponse(BaseModel):
    """A single recorded client write attempt."""

    timestamp: datetime
    function_code: int
    address: int
    values: list[int]
    register_name: str | None = None


class WriteEventsAckResponse(BaseModel):
    """Result of acknowledging (resetting) a device's unread writes."""

    unread: int
```

- [ ] **Step 4: Create the route module**

Create `backend/app/api/routes/write_events.py`:

```python
"""API routes for Modbus client write-event detection."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiResponse
from app.schemas.write_event import WriteEventResponse, WriteEventsAckResponse
from app.services import device_service
from app.simulation import write_tracker

router = APIRouter()


@router.get(
    "/{device_id}/write-events",
    response_model=ApiResponse[list[WriteEventResponse]],
)
async def list_write_events(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[WriteEventResponse]]:
    """List recorded client write attempts (newest first). Pure read — no reset."""
    await device_service.get_device_protocol(session, device_id)  # 404s on unknown
    events = write_tracker.get_events(device_id)
    return ApiResponse(
        data=[
            WriteEventResponse(
                timestamp=e.timestamp,
                function_code=e.function_code,
                address=e.address,
                values=e.values,
                register_name=e.register_name,
            )
            for e in events
        ]
    )


@router.post(
    "/{device_id}/write-events/ack",
    response_model=ApiResponse[WriteEventsAckResponse],
)
async def ack_write_events(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[WriteEventsAckResponse]:
    """Reset the device's unread write count. The event buffer is retained."""
    await device_service.get_device_protocol(session, device_id)  # 404s on unknown
    write_tracker.mark_read(device_id)
    return ApiResponse(data=WriteEventsAckResponse(unread=0))
```

- [ ] **Step 5: Mount the router**

In `backend/app/main.py`, add the import next to the other route imports:

```python
from app.api.routes.write_events import router as write_events_router
```

and mount it under `/devices` next to the other device sub-resource routers:

```python
api_v1_router.include_router(write_events_router, prefix="/devices", tags=["write-events"])
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/test_write_events_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Run the full backend suite**

Run: `cd backend && pytest -q`
Expected: PASS (all existing tests + the new ones). Note: `test_health` asserts version `0.1.0` only under CI's `APP_VERSION` env override — if it fails locally, that is the pre-existing stale-pin behavior, unrelated to this change.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/write_event.py backend/app/api/routes/write_events.py backend/app/main.py backend/tests/test_write_events_api.py
git commit -m "feat: write-events REST endpoints — list (pure) + ack (#71)"
```

---

## Task 5: Frontend types + API client

**Files:**
- Modify: `frontend/src/types/monitor.ts`
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/services/writeEventApi.ts`

- [ ] **Step 1: Add the types**

In `frontend/src/types/monitor.ts`, add two interfaces and a field on `DeviceMonitorData`:

```typescript
export interface WriteEventSummary {
  timestamp: string;
  function_code: number;
  address: number;
  values: number[];
  register_name: string | null;
}

export interface DeviceWriteEvents {
  unread: number;
  latest: WriteEventSummary | null;
}
```

and add to `DeviceMonitorData` (after `mqtt_stats`):

```typescript
  write_events: DeviceWriteEvents;
```

- [ ] **Step 2: Export the new types through the barrel**

In `frontend/src/types/index.ts`, add `DeviceWriteEvents` and `WriteEventSummary` to the `from "./monitor"` export block:

```typescript
export type {
  CommunicationStats,
  DeviceMonitorData,
  DeviceWriteEvents,
  FaultInfo,
  MonitorEvent,
  MonitorUpdate,
  MqttStats,
  RegisterData,
  RegisterHistoryPoint,
  WriteEventSummary,
} from "./monitor";
```

- [ ] **Step 3: Create the API client**

Create `frontend/src/services/writeEventApi.ts`:

```typescript
import { api } from "./api";
import type { ApiResponse, WriteEventSummary } from "../types";

export const writeEventApi = {
  list: (deviceId: string) =>
    api
      .get<ApiResponse<WriteEventSummary[]>>(`/devices/${deviceId}/write-events`)
      .then((r) => r.data),

  ack: (deviceId: string) =>
    api
      .post<ApiResponse<{ unread: number }>>(
        `/devices/${deviceId}/write-events/ack`,
      )
      .then((r) => r.data),
};
```

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS. If errors point to code constructing `DeviceMonitorData` without `write_events`, update those call sites to include `write_events: { unread: 0, latest: null }`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/monitor.ts frontend/src/types/index.ts frontend/src/services/writeEventApi.ts
git commit -m "feat: frontend types + API client for write events (#71)"
```

---

## Task 6: UI — badge on the device card + write-events drawer

**Files:**
- Create: `frontend/src/pages/Monitor/WriteEventsDrawer.tsx`
- Modify: `frontend/src/pages/Monitor/DeviceCard.tsx`

- [ ] **Step 1: Create the drawer component**

Create `frontend/src/pages/Monitor/WriteEventsDrawer.tsx`:

```typescript
import { Drawer, Empty, List, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { writeEventApi } from "../../services/writeEventApi";
import type { WriteEventSummary } from "../../types";

const { Text } = Typography;

const FC_LABELS: Record<number, string> = {
  5: "Write Coil",
  6: "Write Register",
  15: "Write Coils",
  16: "Write Registers",
};

interface WriteEventsDrawerProps {
  deviceId: string;
  deviceName: string;
  open: boolean;
  onClose: () => void;
}

export function WriteEventsDrawer({
  deviceId,
  deviceName,
  open,
  onClose,
}: WriteEventsDrawerProps) {
  const [events, setEvents] = useState<WriteEventSummary[]>([]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      const res = await writeEventApi.list(deviceId);
      if (cancelled) return;
      setEvents(res.data ?? []);
      // Mark read once the list has been viewed (resets the unread badge).
      await writeEventApi.ack(deviceId);
    })();
    return () => {
      cancelled = true;
    };
  }, [open, deviceId]);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      placement="right"
      width={360}
      title={`Write Events — ${deviceName}`}
    >
      {events.length === 0 ? (
        <Empty description="No writes received yet" />
      ) : (
        <List
          size="small"
          dataSource={events}
          renderItem={(e) => {
            const time = new Date(e.timestamp).toLocaleTimeString();
            return (
              <List.Item style={{ padding: "6px 0", display: "block" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {time}
                  </Text>
                  <Tag color="geekblue" style={{ fontSize: 10 }}>
                    {FC_LABELS[e.function_code] ?? `FC${e.function_code}`}
                  </Tag>
                </div>
                <Text style={{ fontSize: 12 }}>
                  {e.register_name ?? `@${e.address}`} = [{e.values.join(", ")}]
                </Text>
              </List.Item>
            );
          }}
        />
      )}
    </Drawer>
  );
}
```

- [ ] **Step 2: Add the badge + drawer wiring to the device card**

In `frontend/src/pages/Monitor/DeviceCard.tsx`:

Add imports at the top:

```typescript
import { useState } from "react";
import { WriteEventsDrawer } from "./WriteEventsDrawer";
```

Inside the component body (after `const { primary, secondary } = ...`), add local drawer state and a click handler:

```typescript
  const [writeDrawerOpen, setWriteDrawerOpen] = useState(false);
  const { unread, latest } = device.write_events;
  const hasWrites = unread > 0 || latest !== null;

  const onWriteTagClick = (e: React.MouseEvent) => {
    e.stopPropagation(); // don't navigate to device detail
    setWriteDrawerOpen(true);
  };
```

In the tag row (the `<div style={{ display: "flex", gap: 5, marginTop: 10, ... }}>` block), add a write tag as the first child:

```typescript
        {hasWrites && (
          <Tag
            color={unread > 0 ? "gold" : "default"}
            style={{ fontSize: 10, cursor: "pointer" }}
            onClick={onWriteTagClick}
          >
            {unread > 0 ? `✎ ${unread} write${unread > 1 ? "s" : ""}` : "✎ writes"}
          </Tag>
        )}
```

Render the drawer just before the component's closing `</div>` (the outer card div). Because the drawer renders in an antd portal, stop click propagation so interacting with it doesn't trigger the card navigation:

```typescript
      <div onClick={(e) => e.stopPropagation()}>
        <WriteEventsDrawer
          deviceId={device.device_id}
          deviceName={device.name}
          open={writeDrawerOpen}
          onClose={() => setWriteDrawerOpen(false)}
        />
      </div>
```

- [ ] **Step 3: Type-check and build**

Run: `cd frontend && npx tsc --noEmit && npm run lint && npm run build`
Expected: PASS — 0 type errors, 0 lint errors, build succeeds.

- [ ] **Step 4: Manual smoke (optional but recommended)**

With the dev stack running (`docker compose up -d`), write to a device via any Modbus client (e.g. `python -c "from pymodbus.client import ModbusTcpClient; c=ModbusTcpClient('localhost',port=502); c.connect(); c.write_register(4, 1234, device_id=1)"`), confirm the gold `✎ 1 write` tag appears on the device card within ~1s, click it, see the event, and confirm the badge clears after the drawer opens.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Monitor/WriteEventsDrawer.tsx frontend/src/pages/Monitor/DeviceCard.tsx
git commit -m "feat: write-events badge + drawer on monitor device card (#71)"
```

---

## Task 7: Documentation (required before push)

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/api-reference.md`
- Modify: `docs/development-log.md`
- Modify: `docs/development-phases.md`

- [ ] **Step 1: CHANGELOG**

Under `## [Unreleased]`, add an `### Added` entry (create the section if absent):

```markdown
### Added
- **Modbus client write detection** (issue #71): the read-only simulator now records client write attempts (FC05/06/15/16) into a per-device in-memory ring buffer (50 events) without persisting the written values (accept-and-ignore — the simulation engine still overwrites on the next tick). Surfaced as an unread badge on the Monitor device card (rides the 1Hz snapshot) plus a write-events drawer; backed by `GET /api/v1/devices/{id}/write-events` (pure list) and `POST /api/v1/devices/{id}/write-events/ack` (reset unread). Lets EMS developers verify their system issued the expected writes. Other protocols tracked in #72.
```

- [ ] **Step 2: API reference**

In `docs/api-reference.md`, add the two endpoints in the devices section, matching the file's existing format:

```markdown
### GET /api/v1/devices/{id}/write-events
List recorded client write attempts for a device, newest first. Pure read (does not reset the unread count). 404 if the device does not exist.

Response `data`: array of `{ timestamp, function_code, address, values: number[], register_name: string | null }`.

### POST /api/v1/devices/{id}/write-events/ack
Reset the device's unread write count to 0 (the event buffer is retained). 404 if the device does not exist.

Response `data`: `{ unread: 0 }`.
```

- [ ] **Step 3: Development log**

Prepend a dated entry to `docs/development-log.md` summarizing: the accept-and-ignore decision, the `trace_pdu` recording approach (pymodbus `.registers` vs `.bits`), the snapshot-piggyback delivery, the clean-REST list/ack split, and that values are not persisted.

- [ ] **Step 4: Development phases**

In `docs/development-phases.md`, add a checked item under the current milestone noting Modbus write detection (#71) landed, and a follow-up `- [ ]` for #72 (other protocols).

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md docs/api-reference.md docs/development-log.md docs/development-phases.md
git commit -m "docs: write detection — changelog, API reference, dev log, phases (#71)"
```

---

## Final verification (before opening the PR)

- [ ] `cd backend && pytest -q` — full backend suite green (modulo the known `test_health` env-pin caveat).
- [ ] `cd frontend && npx tsc --noEmit && npm run lint && npm run build` — clean.
- [ ] Manual smoke from Task 6 Step 4 performed and described in the PR body.
- [ ] Open a PR `feature/claude-modbus-write-detection-20260612 → dev` titled `feat: Modbus client write detection (#71)`, body summarizing scope, the accept-and-ignore decision, endpoints, and verification evidence. Do not merge — wait for human review.
```
