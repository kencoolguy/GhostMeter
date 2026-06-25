# OPC UA Write Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record client OPC UA `Write` requests against simulated Variable nodes, reusing the shared write-events infrastructure (#71/#72).

**Architecture:** Make Variable nodes writable; subscribe a `PostWrite` server callback that records each write into the shared `write_tracker` (generalized `operation`/string model). The write is applied to the node (read-back friendly) and overwritten on the next simulation tick — accept-and-persist-until-tick. No frontend change (the Monitor drawer already renders any protocol's events generically).

**Tech Stack:** Python 3.12 / asyncua; the write-events model/API/UI from #71/#72 are already in place. TDD; backend pytest.

**Spec:** `docs/superpowers/specs/2026-06-25-opcua-write-detection-design.md`

**Branch:** `feature/claude-opcua-write-detection-20260625` (worktree, off dev incl. #77).

**Backend test command (EXACT, from `backend/`):**
```
cd "/Users/kenchen/Claude Project/enol-next-modbus-write-detection/backend" && DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter" ./.venv/bin/python -m pytest <args>
```

**Verified facts:**
- `write_tracker.record(device_id, operation: str, address: int, values: list[str], register_name=None)` (generalized model already merged).
- `opcua_agent.py`: nodes created in `_do_add_device` via `var = await dev_obj.add_variable(...)`; `self._nodes[(device_id, reg.address, reg.function_code)] = var`; `self._node_device[var.nodeid] = device_id`; `node_name = reg.name or f"reg_{reg.address}"`. `_node_device` is cleared in `stop()` and filtered in `_do_remove_device`. `start()` already does `self._server.subscribe_server_callback(CallbackType.PreRead, self._pre_read_fault_delay)`. `CallbackType` is imported.
- asyncua (verified in venv): `InternalSession.write` dispatches `PreWrite` then `PostWrite` (both awaited) with `ServerItemCallback(params, ...)`; `event.request_params.NodesToWrite` is a list of `WriteValue` with `.NodeId`, `.AttributeId`, `.Value` (a `DataValue`; `wv.Value.Value.Value` is the python scalar). `Node.set_writable(writable=True)` exists. `ua.AttributeIds.Value` identifies a value write.
- Test fixture pattern (`test_opcua_fault.py`): `OpcUaAdapter(host="127.0.0.1", port=free_tcp_port())`; `adapter.set_device_meta(dev, name)` then `add_device(dev, 1, [RegisterInfo(0, 3, "float32", "big_endian", name="v")])`; url `opc.tcp://127.0.0.1:{port}/ghostmeter/server/`; namespace `http://ghostmeter.local/opcua/`; browse `GhostMeter → "{name} (#1)" → "v"`; `await var.write_value(x)` / `await var.read_value()`.

---

## Task 1: Record OPC UA writes

**Files:**
- Modify: `backend/app/protocols/opcua_agent.py`
- Test: `backend/tests/test_opcua_write_detection.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/test_opcua_write_detection.py`:

```python
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
```

- [ ] **Step 2: Run — confirm FAILS**

Run: `... pytest tests/test_opcua_write_detection.py -v`
Expected: FAIL — the write currently returns `BadNotWritable` (nodes aren't writable) and nothing is recorded.

- [ ] **Step 3: Add the per-node write metadata map**

In `opcua_agent.py.__init__`, next to `self._node_device: dict[ua.NodeId, UUID] = {}`, add:
```python
        self._node_write_meta: dict[ua.NodeId, tuple[int, str]] = {}  # nodeid → (address, name)
```

- [ ] **Step 4: Make nodes writable + populate the map**

In `_do_add_device`, in the per-register loop, after `self._node_device[var.nodeid] = device_id`, add:
```python
            await var.set_writable(True)
            self._node_write_meta[var.nodeid] = (reg.address, node_name)
```
(`node_name` is the local already computed as `reg.name or f"reg_{reg.address}"`.)

- [ ] **Step 5: Subscribe the PostWrite callback**

In `start()`, immediately after the existing `subscribe_server_callback(CallbackType.PreRead, ...)` call, add:
```python
            self._server.subscribe_server_callback(
                CallbackType.PostWrite, self._post_write_record,
            )
```

- [ ] **Step 6: Add the callback method**

Add this method to `OpcUaAdapter` (place it near `_pre_read_fault_delay`):
```python
    async def _post_write_record(self, event, dispatcher) -> None:  # noqa: ANN001
        """PostWrite server callback: record client writes to our Variable nodes.

        Fires after asyncua applied the write, so the node holds the written
        value until the next simulation tick overwrites it (read-back friendly).
        Defensive: a recording failure must not disrupt the server."""
        try:
            from app.simulation import write_tracker

            for wv in getattr(event.request_params, "NodesToWrite", None) or []:
                if wv.AttributeId != ua.AttributeIds.Value:
                    continue  # ignore non-Value attribute writes (e.g. Description)
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

- [ ] **Step 7: Clean up the new map + tracker on remove/stop**

In `stop()`, add `self._node_write_meta.clear()` next to the existing `self._node_device.clear()`, and before clearing the maps add:
```python
        from app.simulation import write_tracker
        for device_id in set(self._node_device.values()):
            write_tracker.clear(device_id)
```
In `_do_remove_device`, immediately AFTER the existing line that filters `_node_device`
(`self._node_device = {nid: did for nid, did in self._node_device.items() if did != device_id}`),
add this — it keeps `_node_write_meta` entries only for nodeids that survive in the just-filtered
`_node_device` (order-independent, no need to capture ids beforehand), then clears the tracker:
```python
        self._node_write_meta = {
            nid: meta
            for nid, meta in self._node_write_meta.items()
            if nid in self._node_device
        }
        from app.simulation import write_tracker
        write_tracker.clear(device_id)
```

- [ ] **Step 8: Run the new test — confirm PASS**

Run: `... pytest tests/test_opcua_write_detection.py -v`
Expected: 2 passed.

- [ ] **Step 9: OPC UA regression**

Run: `... pytest tests/test_opcua_fault.py -v`
Expected: all pass (making nodes writable + a PostWrite recorder is additive to reads/faults).

- [ ] **Step 10: Ruff + commit**

```
cd "/Users/kenchen/Claude Project/enol-next-modbus-write-detection/backend" && ./.venv/bin/python -m ruff check app/protocols/opcua_agent.py tests/test_opcua_write_detection.py
cd "/Users/kenchen/Claude Project/enol-next-modbus-write-detection"
git add backend/app/protocols/opcua_agent.py backend/tests/test_opcua_write_detection.py
git commit -m "feat: record OPC UA client writes (accept + persist until tick) (#72)"
```

---

## Task 2: Documentation

**Files:** `CHANGELOG.md`, `docs/api-reference.md`, `docs/development-log.md`, `docs/development-phases.md`

- [ ] **Step 1: CHANGELOG**

Under `## [Unreleased]` `### Added`:
```markdown
- **OPC UA client write detection** (issue #72): the simulator's Variable nodes are now writable; client `Write` requests are recorded into the shared write-events buffer and applied to the node (read-back friendly — the value is overwritten on the next simulation tick, not permanently persisted). Reuses the #71/#72 ring buffer / API / Monitor badge. **Known limitation:** OPC UA writes are not yet fault-gated (a device under a timeout/intermittent fault still accepts and acks writes, though the attempt is recorded) — unlike Modbus/BACnet, asyncua's write path has no clean drop-the-response hook; tracked as a #72 follow-up.
```

- [ ] **Step 2: API reference**

In `docs/api-reference.md`, the `GET .../write-events` `operation` row already lists example labels — add `Write` (OPC UA) to the examples if the row enumerates them. No schema change.

- [ ] **Step 3: Development log**

Prepend a dated `## 2026-06-25 — OPC UA 寫入偵測（#72）` entry: the accept-and-persist-until-tick decision (read-back friendly), the `PostWrite` server callback + `set_writable` mechanism (same `subscribe_server_callback` family as the PreRead fault hook), value extraction (`wv.Value.Value.Value`), and the documented write-fault-gating limitation.

- [ ] **Step 4: Development phases**

In `docs/development-phases.md`, under the `#72 (remaining)` line, mark OPC UA done and leave SNMP / MQTT pending.

- [ ] **Step 5: Commit**

```
cd "/Users/kenchen/Claude Project/enol-next-modbus-write-detection"
git add CHANGELOG.md docs/api-reference.md docs/development-log.md docs/development-phases.md
git commit -m "docs: OPC UA write detection (#72)"
```

---

## Final verification (before opening the PR)

- [ ] `cd backend && ... pytest -q` — full backend suite green (modulo the known `test_health` version-pin caveat).
- [ ] Open a PR `feature/claude-opcua-write-detection-20260625 → dev` titled `feat: OPC UA client write detection (#72)`, body summarizing the accept-and-persist decision, the PostWrite mechanism, the fault-gating limitation, and verification evidence. Do not merge — wait for human review.
```
