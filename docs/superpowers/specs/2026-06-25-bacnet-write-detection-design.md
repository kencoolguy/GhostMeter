# BACnet Write Detection + Write-Event Model Generalization — Design (issue #72)

- **Date**: 2026-06-25
- **Issue**: #72 (extend write detection beyond Modbus; this spec covers BACnet only)
- **Builds on**: #71 (Modbus write detection — `write_tracker`, monitor snapshot, REST, UI badge/drawer)
- **Status**: Approved design, ready for implementation plan

## 1. Goal

Extend client write detection (issue #71, Modbus-only) to **BACnet/IP**, the most direct
next protocol. EMS developers can then verify their system issued the expected BACnet
`WriteProperty` requests against simulated devices.

Doing this surfaces that the #71 write-event data model is Modbus-shaped (`function_code: int`,
`values: list[int]`). So this work has two parts:

- **Part A — generalize the write-event model** so it fits any protocol.
- **Part B — record BACnet writes** in the BACnet adapter, reusing the shared infrastructure.

## 2. Approved decisions

1. **BACnet write behaviour: record + return success (accept-and-ignore)** — consistent with
   Modbus. The simulated `AnalogInputObject` currently rejects writes with
   `writeAccessDenied`; we change it to acknowledge success WITHOUT persisting the value
   (the simulation engine still owns the value). The premise (EMS does not read back to
   verify) is the same one accepted for #71.
2. **Generalize the model with a human `operation` label + string values**:
   - `WriteEvent.function_code: int` → `WriteEvent.operation: str`
   - `WriteEvent.values: list[int]` → `WriteEvent.values: list[str]`
   - The Modbus FC→label mapping moves from the frontend into the Modbus adapter.

## 3. Part A — generalized write-event model

### 3.1 `write_tracker.WriteEvent` (backend)

```python
@dataclass(frozen=True)
class WriteEvent:
    timestamp: datetime          # UTC
    operation: str               # human label: "Write Register" (FC6), "WriteProperty" (BACnet), ...
    address: int                 # Modbus address / BACnet object instance
    values: list[str]            # stringified written values (Modbus words / coil 0|1 / BACnet float)
    register_name: str | None    # resolved register/object name, or None
```

`WriteTracker.record(...)` signature changes correspondingly: `operation: str` replaces
`function_code: int`; `values` is `list[str]`. All other methods (`get_events`,
`get_unread_count`, `latest`, `mark_read`, `clear`, `clear_all`) are unchanged.

### 3.2 Modbus adapter (`modbus_tcp.py`)

`_record_write` now computes the operation label and stringifies values:

```python
_MODBUS_WRITE_OPS = {5: "Write Coil", 6: "Write Register", 15: "Write Coils", 16: "Write Registers"}
...
fc = pdu.function_code
if fc in (6, 16):
    values = [str(v) for v in pdu.registers]
else:  # 5, 15 — coils
    values = [str(1 if b else 0) for b in pdu.bits]
operation = _MODBUS_WRITE_OPS.get(fc, f"FC{fc}")
register_name = self._lookup_register_name(device_id, fc, pdu.address)
write_tracker.record(device_id, operation, pdu.address, values, register_name)
```

### 3.3 Monitor snapshot (`monitor_service.build_write_events_payload`)

The `latest` dict uses `operation` instead of `function_code`:

```python
latest_data = {
    "timestamp": latest.timestamp.isoformat(),
    "operation": latest.operation,
    "address": latest.address,
    "values": latest.values,
    "register_name": latest.register_name,
}
```

### 3.4 REST schema (`schemas/write_event.py`)

```python
class WriteEventResponse(BaseModel):
    timestamp: datetime
    operation: str
    address: int
    values: list[str]
    register_name: str | None = None
```

`routes/write_events.py` builds it with `operation=e.operation`. The ack endpoint is unchanged.

### 3.5 Frontend (`types/monitor.ts`, `WriteEventsDrawer.tsx`)

```typescript
export interface WriteEventSummary {
  timestamp: string;
  operation: string;
  address: number;
  values: string[];
  register_name: string | null;
}
```

`WriteEventsDrawer.tsx` drops the `FC_LABELS` map and renders `e.operation` directly; the
value line becomes `{e.register_name ?? \`@${e.address}\`} = [{e.values.join(", ")}]`
(values are already strings). `DeviceCard.tsx` badge is unchanged (reads `unread`/`latest`).

## 4. Part B — BACnet recording (`bacnet_agent.py`)

The `_DeviceApplication.do_WritePropertyRequest` override currently is:

```python
async def do_WritePropertyRequest(self, apdu) -> None:
    raise ExecutionError(errorClass="property", errorCode="writeAccessDenied")
```

It becomes (accept-and-ignore + record), mirroring the canonical bacpypes3 extraction
(`bacpypes3/service/object.py:344`) but WITHOUT calling `obj.write_property`:

```python
async def do_WritePropertyRequest(self, apdu) -> None:
    """Read-only sim: record the write attempt, then ack success without
    persisting (the simulation engine owns the value)."""
    obj = self.get_object_id(apdu.objectIdentifier)
    if obj is None:
        raise ExecutionError(errorClass="object", errorCode="unknownObject")
    self._record_write(apdu, obj)
    await self.response(SimpleAckPDU(context=apdu))
```

with a defensive helper that must never break the ack:

```python
def _record_write(self, apdu, obj) -> None:
    try:
        from app.simulation import write_tracker
        property_type = obj.get_property_type(apdu.propertyIdentifier)
        value = apdu.propertyValue.cast_out(
            property_type, null=(apdu.priority is not None)
        )
        instance = apdu.objectIdentifier[1]  # (objectType, instance); instance == register address
        write_tracker.record(
            self._ghost_device_id,
            "WriteProperty",
            instance,
            [str(value)],
            obj.objectName,
        )
    except Exception:  # pragma: no cover — defensive; must not break the ack
        logger.warning("Failed to record BACnet write for %s", self._ghost_device_id, exc_info=True)
```

- `apdu.objectIdentifier[1]` is the object instance, which equals the register address by
  this adapter's convention (`object instance == register address`, see module docstring).
- `obj.objectName` is the register name (set to `reg.name or f"reg_{address}"` at object
  creation), so BACnet write events almost always have a name.
- Tracker cleanup on device remove / adapter stop already exists for Modbus; **BACnet must
  also call `write_tracker.clear(device_id)`** in its own `_do_remove_device` / `stop()`
  paths (verify and add if missing) so state doesn't leak.

### Notes / edge cases
- The exact bacpypes3 value-extraction (`cast_out`, `objectIdentifier[1]`) is pinned by the
  integration test (a real BACnet client round-trip); the implementer verifies against the
  installed bacpypes3 0.0.106.
- Writes to an unknown object still raise `unknownObject` (no record) — consistent with a
  real device and with not fabricating events.
- Faults: BACnet `do_WhoIsRequest` already goes dark under timeout/intermittent; writes are a
  separate path. Recording is independent of fault handling (records the attempt).

## 5. Testing

### Backend
- **Update existing #71 tests** for the model change (operation/string values):
  `test_write_tracker.py`, `test_modbus_write_detection.py`, `test_monitor_write_events.py`,
  `test_write_events_api.py` — assert `operation` strings and stringified `values`.
- **New `test_bacnet_write_detection.py`** (integration, mirror `test_bacnet_*` fixtures):
  start a `BacnetAdapter`, add a device, issue a `WriteProperty` from a BACnet client (or the
  adapter's own application), assert: an event is recorded with `operation == "WriteProperty"`,
  `address == object instance`, `values == [str(written_value)]`, `register_name == objectName`;
  assert the response is a success ack (not `writeAccessDenied`); assert clear-on-remove.

### Frontend
- `tsc --noEmit` + `eslint` + `build` clean. Drawer renders `operation` and string values.

## 6. Not doing (future)

- OPC UA write detection (read-back/subscription premise needs its own brainstorm) — #72 cont.
- SNMP SET detection (lowest priority) — #72 cont.
- MQTT command-topic subscription (needs separate topic/payload design) — #72 cont.
- Persisting written values / write-then-read-back semantics for any protocol.
