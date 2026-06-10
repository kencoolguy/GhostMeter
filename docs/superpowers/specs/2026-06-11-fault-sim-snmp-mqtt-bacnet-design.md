# Comm-layer Fault Simulation for BACnet / SNMP / MQTT — Design

**Date:** 2026-06-11
**Status:** Approved (design); pending implementation
**Branch:** `feature/claude-fault-sim-snmp-mqtt-bacnet-20260611`

## Goal

Extend comm-layer fault simulation (`delay` / `timeout` / `exception` / `intermittent`) — today supported only by Modbus TCP and OPC UA — to the remaining three protocol adapters: BACnet/IP, SNMP, and MQTT. After this work, all five protocols support fault simulation through the existing REST API with no API changes (one validation rule added).

Implementation order within the single PR: BACnet → SNMP → MQTT.

## Decisions (user-approved)

1. **One PR, three protocols** — single feature branch and spec; shared fault semantics reviewed once.
2. **MQTT does not support `exception`** — publish-only protocols have no request/response channel to return an error on. `PUT /devices/{id}/fault` with `fault_type=exception` on an MQTT device returns **422 VALIDATION_ERROR** (the project's `ValidationException` convention). The other three types map naturally.
3. **BACnet `timeout`/`intermittent` also suppress Who-Is** — a faulted device goes fully dark (no I-Am), matching how a real dead device behaves on a BACnet network.
4. **Architecture: pull-based everywhere (Approach A, the Modbus model)** — each adapter checks `fault_simulator.get_fault(device_id)` live on its serving path. No `apply_fault`/`remove_fault` overrides; base no-op hooks remain. OPC UA keeps its existing push-based implementation (it was forced into that model by asyncua's lack of a read-interception hook; these three all have natural interception points).

Why pull-based: single source of truth (`fault_simulator`), no fault-state caching or restore logic in adapters, faults automatically survive device stop/start and adapter restarts, and identical mental model to Modbus `trace_pdu`.

## Fault-type mapping

| Fault (params) | BACnet | SNMP | MQTT |
|---|---|---|---|
| `delay` (`delay_ms`, default 500, cap 10 000) | `await asyncio.sleep` then respond normally | `loop.call_later` defers the whole `process_pdu` (non-blocking) | `await asyncio.sleep` then publish normally |
| `timeout` | No response (reads **and** Who-Is) | No response | Skip publish (data flow stops) |
| `exception` | BACnet Error `device` / `operationalProblem` | `genErr` error response | **Rejected at REST with 422** |
| `intermittent` (`failure_rate`, default 0.5) | Probabilistic no-response (reads **and** Who-Is) | Probabilistic no-response | Probabilistic skip of publish |

The 10 s delay cap matches the existing OPC UA implementation.

## Per-protocol design

### BACnet (`backend/app/protocols/bacnet_agent.py`)

Hook: `_DeviceApplication` — the per-device bacpypes3 Application already overrides `do_ReadPropertyRequest`, `do_ReadPropertyMultipleRequest`, and `do_WritePropertyRequest`, and carries `_ghost_device_id`.

- Add a fault check at the top of `do_ReadPropertyRequest` / `do_ReadPropertyMultipleRequest`:
  - `timeout` → return without responding (client times out). Count request + error in stats.
  - `intermittent` → `random.random() < failure_rate` → same as timeout; otherwise serve normally.
  - `delay` → `await asyncio.sleep(min(delay_ms, 10_000) / 1000)` then `super()` (handler is async — no event-loop blocking).
  - `exception` → `raise ExecutionError(errorClass="device", errorCode="operationalProblem")` (bacpypes3 converts this to a BACnet Error APDU). Count request + error.
- Add `do_WhoIsRequest` override: under `timeout`, or `intermittent` (per-request probability), drop the request (no I-Am). `delay` and `exception` do **not** affect Who-Is — delay applies to reads only; exception is a read-level error response.

### SNMP (`backend/app/protocols/snmp_agent.py`)

Two hook points (pysnmp v7's responder path is fully synchronous):

1. **Fault-aware command responders** — subclass `GetCommandResponder` / `NextCommandResponder` / `BulkCommandResponder`, override `process_pdu`:
   - Resolve the target device from the PDU's first varbind OID: exact match in `_oid_map`, else `get_next_oid` then map (GETNEXT requests name a predecessor OID). Unresolvable → serve normally.
   - `timeout` → return without calling `super().process_pdu` (no response datagram; client times out).
   - `intermittent` → probabilistic version of the same.
   - `delay` → `loop.call_later(min(delay_ms, 10_000)/1000, super().process_pdu, …)` — defers the entire response without blocking the event loop (everything downstream of `process_pdu` is sync and ends in a sendto).
   - `exception` → fall through to `super()`; handled at hook 2.
2. **`_DynamicMibController.read_variables` / `read_next_variables`** — if the resolved device has an `exception` fault, `raise pysnmp.smi.error.GenError` → `process_pdu`'s `SmiError` handler maps it to a `genErr` response (verified in pysnmp 7.1.27 source: `SMI_ERROR_MAP`, fallback `genErr`).

Known limitation (documented): a single PDU naming OIDs of **multiple** devices is treated by the first resolvable device's fault state, because drop/delay act on the whole PDU. In practice GhostMeter assigns distinct OID subtrees per device and pollers query one device at a time.

### MQTT (`backend/app/protocols/mqtt_adapter.py`)

Hook: inside `_publish_loop`, after the interval sleep and before building the payload:

- `timeout` → skip this publish (`continue`). Count request + error so Monitor shows the failure.
- `intermittent` → probabilistic skip, same counting.
- `delay` → `await asyncio.sleep(min(delay_ms, 10_000)/1000)` then publish normally (messages arrive late with stale-but-honest timestamps).
- `exception` → unreachable (rejected at REST); `_publish_loop` treats it as no fault.

### REST validation (`backend/app/api/routes/simulation.py`)

`set_fault` already resolves the device's protocol to find the adapter. Add: if protocol is `mqtt` and `fault_type == "exception"` → raise the existing validation exception type (HTTP 422, `error_code=VALIDATION_ERROR`, detail explaining MQTT has no request/response channel). No schema changes; `GET`/`DELETE /fault` unchanged.

## Stats convention

Faulted interactions count as `request_count + error_count` (no success, no response-time sample) in the existing per-device `DeviceStats` — consistent with Modbus and with MQTT's current broker-disconnected counting. BACnet counts in `_DeviceApplication`; SNMP gains no new stats plumbing (its responders don't currently track per-device stats — out of scope); MQTT counts in `_publish_loop`.

## Error handling

- Fault checks must never crash the serving path: `fault_simulator.get_fault` is a dict lookup; param reads use `.get` with defaults (`delay_ms=500`, `failure_rate=0.5`), matching Modbus.
- Malformed params (e.g. negative delay) clamp to sane bounds (`0 ≤ delay_ms ≤ 10_000`, `0 ≤ failure_rate ≤ 1`).
- SNMP `loop.call_later` callbacks wrap `super().process_pdu` so an exception inside a deferred response is logged, not swallowed silently.

## Testing

Follow the existing real-client integration-test pattern (`test_bacnet_adapter.py`, OPC UA fault tests):

- **BACnet** (`test_bacnet_adapter.py`): per fault type with a real bacpypes3 client on loopback — `exception` → `ErrorRejectAbortNack` with `operational-problem`; `timeout` → client read raises timeout; `delay` → elapsed ≥ delay_ms; `intermittent` (rate 1.0) → timeout, (rate 0.0) → serves; Who-Is suppressed under timeout; fault cleared → reads recover.
- **SNMP** (`test_snmp_adapter.py`): real GET/GETNEXT through the agent — `timeout` → no response; `exception` → `errorStatus == genErr`; `delay` → elapsed ≥ delay_ms and event loop stays responsive during the wait; `intermittent` boundary rates; fault cleared → recovers.
- **MQTT**: follow existing MQTT test patterns — assert publish skipped under timeout/intermittent (stats error counted), delayed under delay; REST e2e: `PUT /fault` `exception` on an MQTT device → 422.
- **REST e2e** for one protocol (BACnet): set fault via API → behavior observed by real client → clear via API → recovery.

## Out of scope

- OPC UA refactor to pull-based (works today; don't touch).
- SNMP per-device request stats.
- BACnet COV / WriteProperty / BBMD (tracked separately in development-phases).
- Fault persistence across backend restarts (`fault_simulator` stays in-memory — existing behavior for all protocols).

## Docs to update before push

`CHANGELOG.md`, `docs/development-log.md`, `docs/development-phases.md` (new milestone), `docs/api-reference.md` (fault endpoint: MQTT exception 422 note). `docs/database-schema.md` unaffected (no DB changes).
