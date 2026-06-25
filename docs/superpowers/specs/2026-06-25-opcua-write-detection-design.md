# OPC UA Write Detection — Design (issue #72)

- **Date**: 2026-06-25
- **Issue**: #72 (extend write detection beyond Modbus; this spec covers OPC UA only)
- **Builds on**: #71 (Modbus) + the BACnet/model-generalization work (#72, merged) — shared
  `write_tracker` (generalized `operation: str` + `values: list[str]`), REST, Monitor badge/drawer.
- **Status**: Approved design, ready for implementation plan

## 1. Goal

Extend client write detection to **OPC UA**. EMS developers can verify their system issued the
expected OPC UA `Write` requests against simulated Variable nodes.

## 2. Approved decision: accept + persist until next tick

OPC UA clients commonly read back / subscribe to verify a write. So unlike Modbus/BACnet's
strict accept-and-ignore, OPC UA nodes are made **writable**, the client write is **applied**
to the node, and we record it. The simulation engine overwrites the node on its next tick
(~1 s), so the value is not permanently persisted — but a read-back within the tick sees the
written value, which is the realistic OPC UA behaviour.

## 3. Mechanism (verified against asyncua in this repo's venv)

- `InternalSession.write(params)` dispatches `CallbackType.PreWrite` then, **after** applying
  the write via `attribute_service.write`, `CallbackType.PostWrite` — both awaited, so an async
  server callback works (same pattern the adapter already uses for `PreRead` fault delay).
- The callback receives a `ServerItemCallback` whose `request_params` is a `WriteParameters`
  with `.NodesToWrite` — a list of `WriteValue`, each with `.NodeId`, `.AttributeId`, and
  `.Value` (a `DataValue`; `wv.Value.Value` is the `Variant`, `wv.Value.Value.Value` is the
  Python scalar).
- Nodes are created in `_do_add_device` via `dev_obj.add_variable(...)`; by default they are
  **not writable**, so client writes get `BadNotWritable`. We call `await var.set_writable(True)`
  so writes are accepted (and PostWrite fires). `Node.set_writable(writable=True)` is confirmed.

## 4. Components (`opcua_agent.py`)

### 4.1 Make nodes writable
In `_do_add_device`, after creating each variable node, add `await var.set_writable(True)`.

### 4.2 Track write metadata per node
Add `self._node_write_meta: dict[ua.NodeId, tuple[int, str]] = {}` next to `_node_device`,
mapping `var.nodeid → (reg.address, node_name)`. Populate it in `_do_add_device`, clear it in
`stop()`, and filter it by device in `_do_remove_device` (mirroring `_node_device`).

### 4.3 Subscribe a PostWrite callback
In `start()`, alongside the existing PreRead subscription:
```python
self._server.subscribe_server_callback(CallbackType.PostWrite, self._post_write_record)
```

### 4.4 The callback
```python
async def _post_write_record(self, event, dispatcher) -> None:  # noqa: ANN001
    """PostWrite server callback: record client writes to our Variable nodes.

    Fires after asyncua applied the write, so the node holds the written value
    until the next simulation tick overwrites it (read-back friendly)."""
    try:
        from app.simulation import write_tracker

        for wv in getattr(event.request_params, "NodesToWrite", None) or []:
            if wv.AttributeId != ua.AttributeIds.Value:
                continue  # ignore Description/other-attribute writes
            meta = self._node_write_meta.get(wv.NodeId)
            if meta is None:
                continue  # not one of our register nodes
            device_id = self._node_device.get(wv.NodeId)
            if device_id is None:
                continue
            address, node_name = meta
            value = wv.Value.Value.Value  # DataValue → Variant → python scalar
            write_tracker.record(
                device_id, "Write", address, [str(value)], node_name
            )
    except Exception:  # pragma: no cover — defensive; must not disrupt the server
        logger.warning("Failed to record OPC UA write", exc_info=True)
```
- `operation` label is `"Write"` (the OPC UA service name), consistent with the generalized
  model (Modbus `Write Register`, BACnet `WriteProperty`).
- Recording is wrapped defensively.

### 4.5 Tracker cleanup
Add `write_tracker.clear(device_id)` in `_do_remove_device`, and in `stop()` clear every
device's tracker state before the maps are cleared (mirroring Modbus/BACnet).

## 5. Not doing this iteration (documented limitation, not a silent cut)

- **OPC UA write fault-gating** (decided 2026-06-25: document + follow-up, not fixed here).
  Reads honour faults (PreRead delay + value-callback Bad status). Writes apply through
  asyncua's internal write path; asyncua offers no clean way to turn a write into a
  timeout/no-response. So a device under a timeout/intermittent fault still accepts + applies
  writes — **the attempt is still recorded** (detection works under fault), but the response
  is not gated. This differs from Modbus/BACnet, which reuse a request-path drop gate.
- **Worse sub-case — a client write to a faulted node clears that node's fault callback.**
  asyncua's `attribute_service.write` sets `attval.value = ...; attval.value_callback = None`
  (`address_space.py`), so applying a client write to a node that currently carries a fault
  value-callback **removes the callback**, and `update_register` will not re-attach it (it
  skips faulted devices). Net effect: a client write silently disables the fault for that node
  until the fault is removed and re-applied. This is a real fault-sim correctness gap, but an
  edge case (writing to a device while it is faulted). Tracked as a #72 follow-up; the fix
  (gate faulted-device writes, or re-attach the callback post-write) needs its own design +
  asyncua experimentation. Called out in the PR + CHANGELOG so the gap is explicit.

## 6. Testing

### Backend (new `test_opcua_write_detection.py`, mirror `test_opcua_fault.py` fixtures)
- Start an `OpcUaAdapter`, add a device, connect an asyncua `Client`, write a Variable node's
  Value (`node.write_value(...)`), and assert: an event recorded with `operation == "Write"`,
  `address ==` the register address, `values == [str(written_value)]`, `register_name ==` the
  node name; and `get_unread_count == 1`.
- Assert the write **succeeds** (node is writable now — no `BadNotWritable`), and a read-back
  within the same tick returns the written value (accept-and-persist).
- Assert clear-on-remove.

### Frontend
No change — the Monitor badge/drawer already render any protocol's events generically
(`operation` + string values from #72 model generalization).

## 7. Future (#72 continued)
- SNMP SET detection (needs a `SetCommandResponder` registered + OID resolution).
- MQTT command-topic subscription (needs topic/payload design).
- OPC UA write fault-gating (the limitation in §5).
