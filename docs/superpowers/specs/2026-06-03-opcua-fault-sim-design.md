# OPC UA Comm-layer Fault Simulation — Design Spec

- **Date:** 2026-06-03
- **Status:** Approved (brainstorming complete) — ready for implementation plan
- **Branch:** `feature/claude-opcua-fault-sim-20260603`
- **Scope label:** B-light (OPC UA only; lightly generalized so SNMP can adopt later)

## 1. Goal

Comm-layer fault injection (delay / timeout / exception / intermittent) is GhostMeter's
core selling point but currently exists **only on Modbus**. SNMP, MQTT, and OPC UA have
value-level anomaly injection only. This work brings all four fault types to the **OPC UA**
adapter, reusing the existing protocol-agnostic fault state and REST API, and leaving the
Modbus implementation untouched.

### Success criteria

A real `asyncua` client connecting to the GhostMeter OPC UA server observes:

- `exception` → reads return a Bad status code (`BadDeviceFailure`)
- `timeout` → reads return `BadTimeout`
- `delay` → reads measurably slower (bounded)
- `intermittent` → reads alternate Bad / Good per `failure_rate`
- after `clear` → reads return normal values again **and subscriptions resume**

## 2. Background — current state (verified against code 2026-06-03)

- **Fault state is protocol-agnostic and in-memory.** `app/simulation/fault_simulator.py`
  holds `FaultConfig(fault_type, params)` per device via the module singleton
  `fault_simulator` (`set_fault` / `clear_fault` / `get_fault` / `clear_all`).
- **REST `/devices/{id}/fault` (PUT/GET/DELETE)** in `app/api/routes/simulation.py` only
  mutates `fault_simulator` and writes an activity-log event. It does **not** touch any
  adapter today.
- **Modbus is pull-based.** `modbus_tcp.py` `_create_trace_pdu` polls
  `fault_simulator.get_fault(dev_id)` on every PDU and applies the fault there. That is why
  Modbus needs no adapter wiring at fault set/clear, and why a fault survives a device
  restart automatically.
- **OPC UA adapter** (`opcua_agent.py`) is a single shared `asyncua.Server`. Each device is
  an Object node; each register a read-only Variable node. The simulation engine pushes
  values via `update_register()` → `node.write_value(...)`, and asyncua delivers
  subscription notifications on value change (covered by an existing test).
- **A device's protocol lives on its `template` (`template.protocol`)**, not on the device
  row. `device_service.start_device` calls `protocol_manager.add_device(template.protocol, …)`
  and `stop_device` calls `remove_device` (nodes are deleted on stop, recreated on start).
- **Frontend** `pages/Simulation/FaultTab.tsx` has no protocol gating — the fault panel is
  already shown for OPC UA devices. Frontend work here is verification, not development.

## 3. Binding constraint discovered (asyncua value callbacks)

The OPC UA injection hook is a per-node value callback:
`server.iserver.aspace.set_attribute_value_callback(nodeid, ua.AttributeIds.Value, cb)`,
where `cb(nodeid, attr) -> ua.DataValue` is invoked on **every** client read
(spike-verified live on asyncua 1.1.8).

Reading the asyncua `address_space.py` source established the exact semantics:

1. When a value callback is set, reads call the callback **instead of** the stored value.
2. `set_attribute_value_callback` sets `attval.value = None` and `attval.value_callback = cb`.
   It does **not** accept `callback=None` to clear, and has no value-seed parameter.
3. While a callback is set, the normal write path would **overwrite/clear** it.
4. `write_attribute_value` (i.e. the normal `node.write_value()` path) sets
   `attval.value = value`, sets `attval.value_callback = None`, **and** fires the
   `datachange_callbacks` (subscription notifications).

### Consequences (these drive the design)

- A **permanent / pull-style callback is out** — it would clear the stored value, break
  `update_register`'s writes, and silence subscriptions (a tested feature). Fault
  application must be **push-based: attach the callback only while a fault is active.**
- **Detach is trivial:** calling `node.write_value(cached_value)` simultaneously restores
  the stored value, clears the fault callback, and resumes subscriptions. No special API.
- During an active fault, `update_register` **must not** call `write_value` (it would clear
  the callback and silently remove the fault). It must update a cache only.
- For `delay` and `intermittent`-good reads the callback must return the **current
  simulated value**; since the stored value is unavailable while a callback is set, the
  adapter keeps its own per-node last-value cache.

## 4. Architecture decision

**Approach A — base hook + explicit REST trigger** (chosen over an update-loop self-trigger
alternative for immediacy, explicit data flow, and SNMP reuse).

- `fault_simulator` remains the **single source of truth**; the OPC UA callback polls it
  live on each read (same model as Modbus `trace_pdu`).
- A new base hook is a **presence toggle** only ("this device now has / no longer has a
  fault — attach/detach callbacks"). It carries no `FaultConfig`, so `base.py` stays
  decoupled from the simulation layer.

## 5. Detailed design

### 5.1 Base hook — `app/protocols/base.py`

Add two methods to `ProtocolAdapter`, both default no-op:

```python
async def apply_fault(self, device_id: UUID) -> None:
    """A fault became active for this device. Default no-op.

    Modbus polls fault_simulator live in trace_pdu, so it needs no action here.
    """

async def remove_fault(self, device_id: UUID) -> None:
    """The fault was cleared for this device. Default no-op."""
```

Modbus inherits both no-ops; its behavior is unchanged.

### 5.2 OPC UA adapter — `app/protocols/opcua_agent.py`

New state:

- `_last_values: dict[tuple[UUID, int, int], tuple[float | int, ua.VariantType]]`
  — updated on every `update_register`; seeded with `(0, vtype)` per node in
  `_do_add_device` so the callback always has a value to serve.
- `_faulted: set[UUID]` — devices whose nodes currently have a fault callback attached.

Behavior:

- **`update_register`**: always update `_last_values`. If `device_id in _faulted`, **skip**
  `write_value` (it would clear the callback); otherwise `write_value` as today.
- **`apply_fault(device_id)`** (idempotent — return early if already in `_faulted`): for each
  node of the device call
  `self._server.iserver.aspace.set_attribute_value_callback(node.nodeid, ua.AttributeIds.Value, cb)`;
  add to `_faulted`.
- **`remove_fault(device_id)`** (no-op if not in `_faulted`): for each node call
  `await node.write_value(<cached value as Variant>)` to restore value + clear callback +
  resume subscriptions; remove from `_faulted`.
- **callback `cb(nodeid, attr) -> ua.DataValue`** (synchronous, per asyncua contract):
  - `f = fault_simulator.get_fault(device_id)`
  - `f is None` → return cached Good `DataValue` (defensive; shouldn't happen while attached)
  - dispatch on `f.fault_type` (see §5.3)
- **Lifecycle:**
  - `_do_add_device`: after creating nodes + seeding cache, if
    `fault_simulator.get_fault(device_id)` is set, call `apply_fault(device_id)` — so a fault
    survives a device stop/start, matching Modbus.
  - `_do_remove_device`: drop the device's entries from `_last_values` and `_faulted`
    (callbacks die with the deleted nodes).
  - `stop`: also clear `_last_values` and `_faulted` (alongside the existing map clears).

### 5.3 Fault-type → OPC UA mapping

| Modbus semantics | OPC UA implementation |
|---|---|
| `exception` | return `DataValue(status=BadDeviceFailure)` (fixed for MVP; param-overridable later) |
| `timeout` | return `DataValue(status=BadTimeout)` — shared single server can't drop one device's response, so a Bad status is the idiomatic representation |
| `delay` | `time.sleep(min(params.delay_ms (default 500), 10000) / 1000)`, then return cached Good value |
| `intermittent` | `random.random() < params.failure_rate (default 0.5)` → return `BadCommunicationError`; else cached Good value |

DataValue construction for Bad status follows the spike-verified pattern (a `DataValue`
carrying the Bad `StatusCode` makes the client read raise that status). Good values are
returned as `ua.DataValue(ua.Variant(value, vtype))`.

### 5.4 REST wiring — `app/api/routes/simulation.py`

- `set_fault`: add the DB `session` dependency. After `fault_simulator.set_fault(...)`,
  resolve the device's `template.protocol` (as `device_service` does), get the adapter via
  `protocol_manager.get_adapter(protocol)`, and if present + running call
  `await adapter.apply_fault(device_id)`.
- `clear_fault`: symmetric — after `fault_simulator.clear_fault(...)`, call
  `await adapter.remove_fault(device_id)`.
- Modbus adapters run the inherited no-ops, so their REST behavior is unchanged.
- Keep the existing activity-log events.

## 6. Edge cases & lifecycle

- **Fault set then device stopped:** `fault_simulator` keeps the fault; `remove_device`
  deletes nodes/callbacks and cleans adapter caches. On `start_device` → `_do_add_device`
  re-attaches the callback (§5.2 lifecycle), so the fault resumes — consistent with Modbus.
- **Backend restart:** `fault_simulator` is in-memory and is wiped, so faults do not survive
  a backend restart (same as Modbus). Acceptable.
- **Replace an active fault** (set_fault called again with a new type/params): callback reads
  `fault_simulator` live, so the new config applies immediately; `apply_fault` is idempotent.
- **Cache cold** (fault set before first `update_register`): seeded `(0, vtype)` in
  `_do_add_device` guarantees a serveable value.

## 7. Caveats (to document)

- **`delay` blocks the event loop:** the value callback is synchronous, so `time.sleep`
  briefly blocks the shared backend event loop (affecting all OPC UA reads). This mirrors
  Modbus `trace_pdu`'s existing `time.sleep`. Bounded at 10s; bounded blocking accepted. A
  truly non-blocking delay is out of scope.
- **`timeout` is represented as a Bad status, not a real dropped connection** — a limitation
  of the shared single-session server.

## 8. Testing (real end-to-end)

Run on the host per the documented env: Python 3.12 venv,
`pymodbus==3.12.1`, `DATABASE_URL=…@localhost:5434/ghostmeter`, postgres up via
`docker compose up -d postgres`.

- **Integration (real client round-trip):** start the OPC UA server, add a device, connect
  a real `asyncua` client, then for each fault type assert the §1 success criteria,
  including that `clear` restores normal reads and a subscription fires again afterward.
- **Adapter unit tests:** `apply_fault`/`remove_fault` attach/detach correctly; callback
  returns the right `DataValue`/status per type; `_last_values` cache is maintained;
  `update_register` does not clobber the callback while faulted; re-attach on
  `_do_add_device` when a fault is already active.

## 9. Out of scope

- SNMP / MQTT fault application (the base-hook pattern is reusable, but not implemented here).
- Any change to the Modbus implementation.
- True connection-level drop for `timeout`.
- Perfect non-blocking `delay`.

## 10. Docs to update on push

- `CHANGELOG.md` — new OPC UA fault simulation entry.
- `docs/development-log.md` — what/why/decisions/asyncua constraint.
- `docs/development-phases.md` — mark this milestone in progress → complete.
- `docs/api-reference.md` — note OPC UA semantics for `/devices/{id}/fault` (no schema change).
- `docs/database-schema.md` — no change (faults are in-memory).

## 11. Implementation order (small, compilable, testable steps)

1. Add `apply_fault` / `remove_fault` no-op hooks to `ProtocolAdapter` base.
2. OPC UA adapter: add `_last_values` + `_faulted` state; seed cache in `_do_add_device`;
   maintain cache in `update_register` (skip `write_value` while faulted); clear in
   `stop` / `_do_remove_device`.
3. OPC UA adapter: implement `apply_fault` / `remove_fault` + the value callback with the
   §5.3 fault mapping; re-attach in `_do_add_device` when a fault is already active.
4. Wire REST `set_fault` / `clear_fault` to resolve protocol and call the hooks.
5. Adapter unit tests, then real e2e integration tests.
6. Update docs (§10).
