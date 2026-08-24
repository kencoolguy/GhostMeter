# BACnet Write Detection + Model Generalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend client write detection (issue #71, Modbus-only) to BACnet/IP, and generalize the write-event model so it fits any protocol.

**Architecture:** Generalize `WriteEvent` (`function_code: int` → `operation: str`; `values: list[int]` → `values: list[str]`), updating the Modbus adapter, monitor snapshot, REST schema, frontend, and the #71 tests. Then record BACnet `WriteProperty` requests (accept-and-ignore: record + ack success without persisting) reusing the shared `write_tracker` / API / UI.

**Tech Stack:** Python 3.12 / FastAPI / pymodbus 3.12.1 / bacpypes3 0.0.106; React 18 / TS strict / antd 5. TDD; backend pytest, frontend tsc/lint/build.

**Spec:** `docs/superpowers/specs/2026-06-25-bacnet-write-detection-design.md`

**Branch:** `feature/claude-bacnet-write-detection-20260625` (worktree, off dev incl. #76).

**Backend test command (EXACT, from `backend/`):**
```
cd "/Users/kenchen/Claude Project/enol-next-modbus-write-detection/backend" && DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter" ./.venv/bin/python -m pytest <args>
```

**Verified facts:**
- `WriteEvent`/`WriteTracker.record` today: `record(device_id, function_code: int, address, values: list[int], register_name=None)`.
- Modbus `_record_write` (`modbus_tcp.py`) extracts FC6/16 from `pdu.registers`, FC5/15 from `pdu.bits`.
- Monitor `build_write_events_payload` (`monitor_service.py`) emits a `latest` dict with `function_code`.
- REST: `schemas/write_event.py::WriteEventResponse` has `function_code`; `routes/write_events.py` builds it.
- Frontend `WriteEventSummary` (`types/monitor.ts`) has `function_code: number`, `values: number[]`; `WriteEventsDrawer.tsx` maps it via `FC_LABELS`.
- bacpypes3 0.0.106: base `do_WritePropertyRequest` (`service/object.py:344`) does `obj = self.get_object_id(apdu.objectIdentifier)`, `property_type = obj.get_property_type(apdu.propertyIdentifier)`, `value = apdu.propertyValue.cast_out(property_type, null=(apdu.priority is not None))`. `apdu.objectIdentifier[1]` is the instance (== register address by this adapter's convention). `obj.objectName` is the register name.
- BACnet client write: `await client.write_property(addr, ObjectIdentifier(("analog-input", N)), "present-value", value)`.
- BACnet `_DeviceApplication.do_WritePropertyRequest` (`bacnet_agent.py:127`) currently raises `writeAccessDenied`. `_ghost_device_id` is on the app. Cleanup: `_do_remove_device` (`:463`) and `stop()` (`:248`, bulk-clears at `:259-278`); `_device_apps` is keyed by `device_id`.
- BACnet integration tests live in `test_bacnet_fault.py` (helpers `_client_app`, `_running_adapter`, `_device_addr`, `_regs`, module fixture `_route_aware`).

---

## Task 1: Generalize the write-event model (backend)

This task changes the model end-to-end on the backend in one green commit: the dataclass, all three consumers, and the four #71 test files.

**Files:**
- Modify: `backend/app/simulation/write_tracker.py`
- Modify: `backend/app/protocols/modbus_tcp.py`
- Modify: `backend/app/services/monitor_service.py`
- Modify: `backend/app/schemas/write_event.py`
- Modify: `backend/app/api/routes/write_events.py`
- Tests: `backend/tests/test_write_tracker.py`, `test_modbus_write_detection.py`, `test_monitor_write_events.py`, `test_write_events_api.py`

- [ ] **Step 1: Update the model and all consumers**

In `backend/app/simulation/write_tracker.py`, change the `WriteEvent` dataclass field `function_code: int` to `operation: str` and `values: list[int]` to `values: list[str]`:

```python
@dataclass(frozen=True)
class WriteEvent:
    """A single recorded client write attempt."""

    timestamp: datetime          # UTC
    operation: str               # human label, e.g. "Write Register" / "WriteProperty"
    address: int                 # Modbus address / BACnet object instance
    values: list[str]            # stringified written values
    register_name: str | None    # resolved register/object name, or None
```

and change `record` to match (rename param, keep `list(values)` copy):

```python
    def record(
        self,
        device_id: UUID,
        operation: str,
        address: int,
        values: list[str],
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
                operation=operation,
                address=address,
                values=list(values),
                register_name=register_name,
            )
        )
        self._unread[device_id] = self._unread.get(device_id, 0) + 1
```

In `backend/app/protocols/modbus_tcp.py`, add a module-level label map near the top (after imports):

```python
_MODBUS_WRITE_OPS = {5: "Write Coil", 6: "Write Register", 15: "Write Coils", 16: "Write Registers"}
```

and replace the body of `_record_write` so it computes the operation label and stringifies values:

```python
    def _record_write(self, device_id: UUID, pdu) -> None:
        """Record a client write attempt. Must never raise into the serving path."""
        try:
            from app.simulation import write_tracker

            fc = pdu.function_code
            if fc in (6, 16):
                values = [str(v) for v in pdu.registers]
            else:  # 5, 15 — coils
                values = [str(1 if b else 0) for b in pdu.bits]
            operation = _MODBUS_WRITE_OPS.get(fc, f"FC{fc}")
            register_name = self._lookup_register_name(device_id, fc, pdu.address)
            write_tracker.record(device_id, operation, pdu.address, values, register_name)
        except Exception:  # pragma: no cover — defensive; must not break the response
            logger.warning("Failed to record write event for %s", device_id, exc_info=True)
```

In `backend/app/services/monitor_service.py`, in `build_write_events_payload`, change the `latest_data` dict key `function_code` to `operation`:

```python
            latest_data = {
                "timestamp": latest.timestamp.isoformat(),
                "operation": latest.operation,
                "address": latest.address,
                "values": latest.values,
                "register_name": latest.register_name,
            }
```

In `backend/app/schemas/write_event.py`, change `WriteEventResponse`:

```python
class WriteEventResponse(BaseModel):
    """A single recorded client write attempt."""

    timestamp: datetime
    operation: str
    address: int
    values: list[str]
    register_name: str | None = None
```

In `backend/app/api/routes/write_events.py`, change the `WriteEventResponse(...)` construction in `list_write_events` from `function_code=e.function_code,` to `operation=e.operation,`.

- [ ] **Step 2: Update the four #71 test files**

In `backend/tests/test_write_tracker.py`, replace every `function_code=<int>` keyword in `record(...)` calls with an `operation=<str>` keyword, and make all `values=[...]` lists hold strings. Update assertions:
- `test_record_and_get_events_newest_first`: call `t.record(dev, operation="Write Register", address=10, values=["111"], register_name="setpoint")` and `t.record(dev, operation="Write Registers", address=20, values=["1", "2"], register_name=None)`; assert `events[0].values == ["1", "2"]` and `events[0].operation == "Write Registers"`.
- The other tests: change `function_code=6` → `operation="Write Register"`, and `values=[i]` → `values=[str(i)]`; in `test_ring_buffer_caps_at_max` use `values=[str(i)]`; in `test_values_are_copied_not_aliased` use `src = ["1", "2"]` and assert `== ["1", "2"]`.

In `backend/tests/test_modbus_write_detection.py`, update assertions to the new model:
- `test_fc6_single_register_write_recorded`: `assert events[0].operation == "Write Register"` (was `function_code == 6`); `assert events[0].values == ["1234"]`.
- `test_fc16_multi_register_write_recorded`: `assert events[0].operation == "Write Registers"`; `assert events[0].values == ["11", "22"]`.
- `test_coil_write_recorded_even_when_address_illegal`: `assert events[0].operation == "Write Coil"`; `assert events[0].values == ["1"]`.
- `test_write_recorded_even_when_timeout_fault_active`: `assert events[0].values == ["55"]`.

In `backend/tests/test_monitor_write_events.py`:
- `test_build_write_events_payload_with_events`: call `write_tracker.record(dev, operation="Write Register", address=4, values=["1234"], register_name="sp")`; assert `payload["latest"]["operation"] == "Write Register"` and `payload["latest"]["values"] == ["1234"]`.

In `backend/tests/test_write_events_api.py`:
- In both tests, change the `write_tracker.record(...)` calls to use `operation="Write Register"` / `operation="Write Registers"` and string values (`values=["10"]`, `values=["20", "30"]`).
- In `test_list_returns_events_newest_first_without_resetting_unread`: assert `data[0]["values"] == ["20", "30"]` and (optionally) `data[0]["operation"] == "Write Registers"`.

- [ ] **Step 3: Run the affected tests — confirm PASS**

Run: `... pytest tests/test_write_tracker.py tests/test_modbus_write_detection.py tests/test_monitor_write_events.py tests/test_write_events_api.py -v`
Expected: all pass (the same counts as before: 6 + 7 + 2 + 3).

- [ ] **Step 4: Ruff + commit**

```
cd "/Users/kenchen/Claude Project/enol-next-modbus-write-detection/backend" && ./.venv/bin/python -m ruff check app tests
cd "/Users/kenchen/Claude Project/enol-next-modbus-write-detection"
git add backend/app/simulation/write_tracker.py backend/app/protocols/modbus_tcp.py backend/app/services/monitor_service.py backend/app/schemas/write_event.py backend/app/api/routes/write_events.py backend/tests/test_write_tracker.py backend/tests/test_modbus_write_detection.py backend/tests/test_monitor_write_events.py backend/tests/test_write_events_api.py
git commit -m "refactor: generalize write-event model (operation label + string values) (#72)"
```

---

## Task 2: Generalize the frontend write-event types + drawer

**Files:**
- Modify: `frontend/src/types/monitor.ts`
- Modify: `frontend/src/pages/Monitor/WriteEventsDrawer.tsx`

- [ ] **Step 1: Update the type**

In `frontend/src/types/monitor.ts`, change `WriteEventSummary`:

```typescript
export interface WriteEventSummary {
  timestamp: string;
  operation: string;
  address: number;
  values: string[];
  register_name: string | null;
}
```

- [ ] **Step 2: Update the drawer**

In `frontend/src/pages/Monitor/WriteEventsDrawer.tsx`, delete the `FC_LABELS` constant and render `operation` directly. The `renderItem` becomes:

```typescript
          renderItem={(e) => {
            const time = new Date(e.timestamp).toLocaleTimeString();
            return (
              <List.Item style={{ padding: "6px 0", display: "block" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {time}
                  </Text>
                  <Tag color="geekblue" style={{ fontSize: 10 }}>
                    {e.operation}
                  </Tag>
                </div>
                <Text style={{ fontSize: 12 }}>
                  {e.register_name ?? `@${e.address}`} = [{e.values.join(", ")}]
                </Text>
              </List.Item>
            );
          }}
```

(`e.values` is now `string[]`, so `.join(", ")` works directly.)

- [ ] **Step 3: Gates**

Run: `cd "/Users/kenchen/Claude Project/enol-next-modbus-write-detection/frontend" && npx tsc --noEmit && npm run lint && npm run build`
Expected: 0 type errors, 0 lint errors, build OK.

- [ ] **Step 4: Commit**

```
cd "/Users/kenchen/Claude Project/enol-next-modbus-write-detection"
git add frontend/src/types/monitor.ts frontend/src/pages/Monitor/WriteEventsDrawer.tsx
git commit -m "refactor: frontend write-event drawer shows generic operation label (#72)"
```

---

## Task 3: Record BACnet WriteProperty requests

**Files:**
- Modify: `backend/app/protocols/bacnet_agent.py`
- Test: `backend/tests/test_bacnet_write_detection.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/test_bacnet_write_detection.py`:

```python
"""Integration tests for BACnet client write detection (real bacpypes3 round-trips)."""

import contextlib
import uuid

import pytest
from bacpypes3.primitivedata import ObjectIdentifier
from bacpypes3.settings import settings as bp3_settings

from tests.netutil import free_udp_port

NETWORK = 100

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module", autouse=True)
def _route_aware():
    previous = bp3_settings.route_aware
    bp3_settings.route_aware = True
    yield
    bp3_settings.route_aware = previous


def _regs():
    from app.protocols.base import RegisterInfo

    return [RegisterInfo(0, 3, "float32", "big_endian", name="voltage", unit="V")]


@contextlib.asynccontextmanager
async def _client_app():
    from bacpypes3.app import Application
    from bacpypes3.local.device import DeviceObject
    from bacpypes3.local.networkport import NetworkPortObject

    port = free_udp_port()
    app = Application.from_object_list([
        DeviceObject(
            objectIdentifier=("device", 4194302),
            objectName="write-test-client",
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
        port=free_udp_port(),
        device_instance_base=100000,
        network=NETWORK,
    )
    await adapter.start()
    try:
        yield adapter
    finally:
        await adapter.stop()


async def test_write_property_is_recorded_and_acked():
    from app.simulation import write_tracker

    write_tracker.clear_all()
    device_id = uuid.uuid4()
    async with _running_adapter() as adapter:
        await adapter.add_device(device_id, 1, _regs())
        async with _client_app() as client:
            addr = _device_addr(adapter._port, 1)
            # Should succeed (accept-and-ignore), NOT raise writeAccessDenied:
            await client.write_property(
                addr, ObjectIdentifier(("analog-input", 0)), "present-value", 42.5
            )

        events = write_tracker.get_events(device_id)
        assert len(events) == 1
        assert events[0].operation == "WriteProperty"
        assert events[0].address == 0  # object instance == register address
        assert float(events[0].values[0]) == 42.5
        assert events[0].register_name == "voltage"
        assert write_tracker.get_unread_count(device_id) == 1


async def test_clear_on_remove_device():
    from app.simulation import write_tracker

    write_tracker.clear_all()
    device_id = uuid.uuid4()
    async with _running_adapter() as adapter:
        await adapter.add_device(device_id, 1, _regs())
        async with _client_app() as client:
            addr = _device_addr(adapter._port, 1)
            await client.write_property(
                addr, ObjectIdentifier(("analog-input", 0)), "present-value", 7.0
            )
        assert write_tracker.get_unread_count(device_id) == 1
        await adapter.remove_device(device_id)
        assert write_tracker.get_events(device_id) == []
```

- [ ] **Step 2: Run — confirm FAILS**

Run: `... pytest tests/test_bacnet_write_detection.py -v`
Expected: FAIL — the write currently raises `writeAccessDenied` (no ack, no record).

- [ ] **Step 3: Implement recording + accept-and-ignore**

In `backend/app/protocols/bacnet_agent.py`, replace the `_DeviceApplication.do_WritePropertyRequest` body and add a `_record_write` helper on `_DeviceApplication`:

```python
    async def do_WritePropertyRequest(self, apdu) -> None:
        """Read-only sim: record the client write attempt, then ack success
        without persisting (the simulation engine owns the value)."""
        obj = self.get_object_id(apdu.objectIdentifier)
        if obj is None:
            raise ExecutionError(errorClass="object", errorCode="unknownObject")
        self._record_write(apdu, obj)
        await self.response(SimpleAckPDU(context=apdu))

    def _record_write(self, apdu, obj) -> None:
        """Record a client write attempt. Must never raise into the response path."""
        try:
            from app.simulation import write_tracker

            property_type = obj.get_property_type(apdu.propertyIdentifier)
            value = apdu.propertyValue.cast_out(
                property_type, null=(apdu.priority is not None)
            )
            instance = apdu.objectIdentifier[1]  # (objectType, instance); == register address
            write_tracker.record(
                self._ghost_device_id,
                "WriteProperty",
                instance,
                [str(value)],
                obj.objectName,
            )
        except Exception:  # pragma: no cover — defensive; must not break the ack
            logger.warning(
                "Failed to record BACnet write for %s", self._ghost_device_id, exc_info=True
            )
```

Add the `SimpleAckPDU` import. The file already imports `from bacpypes3.errors import ExecutionError` (line 28); add this line next to the other `bacpypes3` imports (verified to exist in bacpypes3 0.0.106):

```python
from bacpypes3.apdu import SimpleAckPDU
```

- [ ] **Step 4: Add tracker cleanup on remove + stop**

In `_do_remove_device` (around `bacnet_agent.py:463`), after the `_device_apps.pop(device_id, ...)` / `_objects` filtering, add:

```python
        from app.simulation import write_tracker
        write_tracker.clear(device_id)
```

In `stop()` (around `:248`), immediately BEFORE the bulk `self._device_apps.clear()` call, add:

```python
        from app.simulation import write_tracker
        for device_id in list(self._device_apps.keys()):
            write_tracker.clear(device_id)
```

- [ ] **Step 5: Run the new test — confirm PASS**

Run: `... pytest tests/test_bacnet_write_detection.py -v`
Expected: 2 passed.

- [ ] **Step 6: Run BACnet regression**

Run: `... pytest tests/test_bacnet_fault.py tests/test_bacnet_adapter.py -v`
Expected: all pass (recording + ack is additive; the only behaviour change is writes now ack instead of rejecting — confirm no existing test asserted the rejection; if one does, it documented the OLD behaviour and must be updated to expect the ack, with a note).

- [ ] **Step 7: Ruff + commit**

```
cd "/Users/kenchen/Claude Project/enol-next-modbus-write-detection/backend" && ./.venv/bin/python -m ruff check app/protocols/bacnet_agent.py tests/test_bacnet_write_detection.py
cd "/Users/kenchen/Claude Project/enol-next-modbus-write-detection"
git add backend/app/protocols/bacnet_agent.py backend/tests/test_bacnet_write_detection.py
git commit -m "feat: record BACnet WriteProperty attempts (accept-and-ignore) (#72)"
```

---

## Task 4: Documentation

**Files:**
- Modify: `CHANGELOG.md`, `docs/api-reference.md`, `docs/development-log.md`, `docs/development-phases.md`

- [ ] **Step 1: CHANGELOG**

Under `## [Unreleased]` `### Added` (create if absent):

```markdown
### Added
- **BACnet client write detection** (issue #72): the read-only simulator now records client `WriteProperty` requests against BACnet devices and acknowledges success (accept-and-ignore, like Modbus) instead of rejecting with `writeAccessDenied`. Reuses the shared write-events ring buffer / API / Monitor badge from #71.

### Changed
- **Write-event model generalized** to fit any protocol: the Modbus-specific `function_code` (int) is now a human `operation` label (e.g. `Write Register`, `WriteProperty`) and `values` are strings (so a BACnet float present-value and a Modbus 16-bit word share one shape). Affects `GET /api/v1/devices/{id}/write-events` and the WebSocket monitor snapshot.
```

- [ ] **Step 2: API reference**

In `docs/api-reference.md`, update the `WriteEvent` schema table for `GET .../write-events`: rename the `function_code` row to `operation` (string — "human-readable write operation label"), and change the `values` type from `int[]` to `string[]`.

- [ ] **Step 3: Development log**

Prepend a dated `## 2026-06-25 — BACnet 寫入偵測 + 模型一般化（#72）` entry summarizing: why the model needed generalizing (BACnet has no function code and writes floats), the accept-and-ignore behaviour change (record + SimpleAck, no `obj.write_property`), the bacpypes3 `cast_out` extraction, and that the shared ring buffer / API / UI were reused.

- [ ] **Step 4: Development phases**

In `docs/development-phases.md`, under the current milestone, change the `#72` follow-up line to mark BACnet done and note OPC UA / SNMP / MQTT still pending (each needs its own design — OPC UA read-back premise, MQTT command-topic).

- [ ] **Step 5: Commit**

```
cd "/Users/kenchen/Claude Project/enol-next-modbus-write-detection"
git add CHANGELOG.md docs/api-reference.md docs/development-log.md docs/development-phases.md
git commit -m "docs: BACnet write detection + model generalization (#72)"
```

---

## Final verification (before opening the PR)

- [ ] `cd backend && ... pytest -q` — full backend suite green (modulo the known `test_health` version-pin caveat).
- [ ] `cd frontend && npx tsc --noEmit && npm run lint && npm run build` — clean.
- [ ] Open a PR `feature/claude-bacnet-write-detection-20260625 → dev` titled `feat: BACnet client write detection + write-event model generalization (#72)`, body summarizing the model change, the BACnet accept-and-ignore behaviour change, and verification evidence. Do not merge — wait for human review.
