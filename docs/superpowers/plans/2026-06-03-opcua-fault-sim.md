# OPC UA Comm-layer Fault Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the four comm-layer fault types (delay/timeout/exception/intermittent) to the OPC UA adapter, triggered by the existing REST `/fault` endpoint, without touching the Modbus implementation.

**Architecture:** Push-based fault application. A new no-op `apply_fault`/`remove_fault` hook on `ProtocolAdapter` is implemented by the OPC UA adapter to attach/detach per-node value callbacks via `asyncua`'s `set_attribute_value_callback`. The callback polls the existing in-memory `fault_simulator` (single source of truth) on every client read. A per-node last-value cache lets `delay`/`intermittent` serve the latest simulated value; detaching simply re-writes the cached value (which restores the stored value, clears the callback, and resumes subscriptions). The REST endpoint resolves the device's protocol and calls the hook.

**Tech Stack:** Python 3.12, FastAPI, asyncua 1.1.8, pytest + pytest-asyncio, real `asyncua.Client` round-trip tests.

---

## Background the engineer needs

- **Spec:** `docs/superpowers/specs/2026-06-03-opcua-fault-sim-design.md` (read it first).
- **Fault state** lives in `backend/app/simulation/fault_simulator.py`: module singleton `fault_simulator` with `set_fault(device_id, FaultConfig)`, `clear_fault(device_id)`, `get_fault(device_id) -> FaultConfig | None`, `clear_all()`. `FaultConfig` has `.fault_type: str` and `.params: dict`.
- **OPC UA adapter:** `backend/app/protocols/opcua_agent.py`. One shared `asyncua.Server`. Per device: an Object node; per register: a Variable node stored in `self._nodes[(device_id, address, function_code)] = node`. Values pushed via `update_register()` → `node.write_value(ua.Variant(...))`. `_TYPE_MAP[data_type] -> (ua.VariantType, caster)`. `_coerce_to_range(value, vtype)` clamps values.
- **asyncua callback semantics (verified against source):** `server.iserver.aspace.set_attribute_value_callback(nodeid, ua.AttributeIds.Value, cb)` makes reads call `cb(nodeid, attr) -> ua.DataValue` instead of the stored value, and sets the stored value to `None`. There is no API to clear the callback with `None`; instead the normal write path (`node.write_value`) sets the value, clears the callback, and fires subscription notifications. So **while a fault is active, `update_register` must NOT call `write_value`** (it would clear the callback) — it updates the cache only.
- **Client-side observation of a Bad status without an exception:** `dv = await node.read_data_value(raise_on_bad_status=False)` returns the full `ua.DataValue`; check `dv.StatusCode_.value`. (`read_value()` raises on Bad status.)
- **Device protocol** is on the template: `template.protocol`. `device_service._get_device_raw(session, id)` returns the device ORM; `device_service.get_template_with_registers(session, template_id)` (alias of `template_service.get_template`) returns the `DeviceTemplate` (has `.protocol`).
- **Test env (host):** Python 3.12 venv, `pymodbus==3.12.1`, postgres up (`docker compose up -d postgres`), and `DATABASE_URL` overridden to host port 5434. The full command prefix used in every test step below:
  ```bash
  cd backend && DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter" ./.venv/bin/python -m pytest
  ```
  (Create the venv once if missing: `/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv backend/.venv && ./backend/.venv/bin/python -m pip install -r backend/requirements.txt "pymodbus==3.12.1" ruff`.)

## File structure

- **Modify** `backend/app/protocols/base.py` — add two no-op fault hooks to `ProtocolAdapter`.
- **Modify** `backend/app/protocols/opcua_agent.py` — cache + `_faulted` state, `apply_fault`/`remove_fault`, value callback, `update_register` skip, lifecycle cleanup/re-attach.
- **Modify** `backend/app/services/device_service.py` — add `get_device_protocol` helper.
- **Modify** `backend/app/api/routes/simulation.py` — wire `set_fault`/`clear_fault` to the adapter hook.
- **Create** `backend/tests/test_opcua_fault.py` — adapter-level + REST-level e2e fault tests.
- **Modify** `backend/tests/test_modbus_fault.py` — assert the base hooks are inherited no-ops (Modbus untouched).
- **Modify** docs: `CHANGELOG.md`, `docs/development-log.md`, `docs/development-phases.md`, `docs/api-reference.md`.

---

## Task 1: Base no-op fault hooks

**Files:**
- Modify: `backend/app/protocols/base.py` (add methods to `ProtocolAdapter`, after `reset_stats`, before the `--- Device lifecycle ---` section)
- Test: `backend/tests/test_modbus_fault.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_modbus_fault.py`:

```python
class TestBaseFaultHooks:
    """The base apply_fault/remove_fault hooks are no-ops; Modbus inherits them
    unchanged (Modbus applies faults via trace_pdu polling, not via these hooks)."""

    @pytest.mark.asyncio
    async def test_modbus_fault_hooks_are_noops(self):
        adapter = ModbusTcpAdapter(host="127.0.0.1", port=15598)
        dev = uuid.uuid4()
        # No start(), no device registered — pure no-ops must not raise.
        await adapter.apply_fault(dev)
        await adapter.remove_fault(dev)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter" ./.venv/bin/python -m pytest tests/test_modbus_fault.py::TestBaseFaultHooks -v`
Expected: FAIL with `AttributeError: 'ModbusTcpAdapter' object has no attribute 'apply_fault'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/protocols/base.py`, add to `ProtocolAdapter` immediately after the `reset_stats` method:

```python
    # --- Fault hooks (concrete no-op default; protocol adapters may override) ---

    async def apply_fault(self, device_id: UUID) -> None:
        """A comm-layer fault became active for this device.

        Presence toggle only — the active FaultConfig lives in
        app.simulation.fault_simulator. Default no-op: Modbus polls
        fault_simulator live in trace_pdu, so it needs no action here.
        OPC UA overrides this to attach value callbacks.
        """

    async def remove_fault(self, device_id: UUID) -> None:
        """The comm-layer fault was cleared for this device. Default no-op."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter" ./.venv/bin/python -m pytest tests/test_modbus_fault.py::TestBaseFaultHooks -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/protocols/base.py backend/tests/test_modbus_fault.py
git commit -m "feat: add no-op apply_fault/remove_fault hooks to ProtocolAdapter base"
```

---

## Task 2: OPC UA last-value cache + `_faulted` state

This adds the per-node value cache and the (still-dormant) `_faulted` set, seeds the cache on device add, maintains it in `update_register` (skipping `write_value` when faulted), and cleans it up on stop/remove. No fault behavior yet — `_faulted` stays empty until Task 3.

**Files:**
- Modify: `backend/app/protocols/opcua_agent.py`
- Test: `backend/tests/test_opcua_fault.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_opcua_fault.py`:

```python
"""Tests for OPC UA comm-layer fault simulation (real asyncua client round-trips)."""

import asyncio
import socket
import time
import uuid

import pytest

pytestmark = pytest.mark.asyncio


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestOpcUaFaultCache:
    async def test_cache_seeded_on_add_and_updated(self):
        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        adapter = OpcUaAdapter(host="127.0.0.1", port=_free_port())
        await adapter.start()
        dev = uuid.uuid4()
        regs = [RegisterInfo(0, 3, "float32", "big_endian", name="v")]
        try:
            await adapter.add_device(dev, 1, regs)
            # Seeded with 0 on add
            assert adapter._last_values[(dev, 0, 3)][0] == 0
            # Updated by update_register
            await adapter.update_register(dev, 0, 3, 12.5, "float32", "big_endian")
            assert abs(adapter._last_values[(dev, 0, 3)][0] - 12.5) < 0.01
        finally:
            await adapter.stop()

    async def test_cache_cleared_on_remove_and_stop(self):
        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        adapter = OpcUaAdapter(host="127.0.0.1", port=_free_port())
        await adapter.start()
        dev = uuid.uuid4()
        regs = [RegisterInfo(0, 3, "float32", "big_endian", name="v")]
        try:
            await adapter.add_device(dev, 1, regs)
            await adapter.remove_device(dev)
            assert all(k[0] != dev for k in adapter._last_values)
        finally:
            await adapter.stop()
        assert adapter._last_values == {}
        assert adapter._faulted == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter" ./.venv/bin/python -m pytest tests/test_opcua_fault.py::TestOpcUaFaultCache -v`
Expected: FAIL with `AttributeError: 'OpcUaAdapter' object has no attribute '_last_values'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/protocols/opcua_agent.py`:

(a) Add to the imports at the top (after `import math`):
```python
import random
import time
```

(b) In `__init__`, after the `self._device_meta` line, add:
```python
        self._last_values: dict[tuple[UUID, int, int], tuple[float | int, ua.VariantType]] = {}
        self._faulted: set[UUID] = set()  # devices with fault callbacks attached
```

(c) In `_do_add_device`, in the `for reg in registers:` loop, right after the line `self._nodes[(device_id, reg.address, reg.function_code)] = var`, add:
```python
            self._last_values[(device_id, reg.address, reg.function_code)] = (
                caster(0), vtype,
            )
```

(d) Replace the body of `update_register` (everything after the docstring) with:
```python
        key = (device_id, address, function_code)
        node = self._nodes.get(key)
        if node is None:
            logger.debug(
                "OPC UA: no node for device %s addr %d fc %d",
                device_id, address, function_code,
            )
            return
        vtype, _caster = _TYPE_MAP.get(data_type, (ua.VariantType.Double, float))
        coerced = _coerce_to_range(value, vtype)
        self._last_values[key] = (coerced, vtype)
        if device_id in self._faulted:
            # Node has a fault value-callback attached; writing would clear it.
            return
        await node.write_value(ua.Variant(coerced, vtype))
```

(e) In `_do_remove_device`, after the `self._nodes = {...}` reassignment, add:
```python
        self._last_values = {
            k: v for k, v in self._last_values.items() if k[0] != device_id
        }
        self._faulted.discard(device_id)
```

(f) In `stop`, alongside the existing `self._nodes.clear()` etc., add:
```python
        self._last_values.clear()
        self._faulted.clear()
```

- [ ] **Step 4: Run the new test AND the existing OPC UA suite to verify no regression**

Run: `cd backend && DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter" ./.venv/bin/python -m pytest tests/test_opcua_fault.py::TestOpcUaFaultCache tests/test_opcua_adapter.py -v`
Expected: all PASS (cache tests pass; existing round-trip + subscription tests still pass because `_faulted` is empty, so `update_register` still calls `write_value`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/protocols/opcua_agent.py backend/tests/test_opcua_fault.py
git commit -m "feat: add OPC UA last-value cache and faulted-device tracking"
```

---

## Task 3: OPC UA `apply_fault`/`remove_fault` + value callback

This is the core. Attaches per-node value callbacks on `apply_fault`, detaches (restoring values + subscriptions) on `remove_fault`, maps the four fault types to OPC UA semantics, and re-attaches automatically when a device is added while a fault is already active.

**Files:**
- Modify: `backend/app/protocols/opcua_agent.py`
- Test: `backend/tests/test_opcua_fault.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_opcua_fault.py`:

```python
class _SubHandler:
    def __init__(self) -> None:
        self.values: list = []

    def datachange_notification(self, node, val, data) -> None:  # noqa: ANN001
        self.values.append(val)


async def _make_running_device(port, name="FaultMeter"):
    """Start an adapter with one device + one float32 register at addr 0/fc 3."""
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


async def _read_status(url, raise_on_bad=False):
    """Connect, read the device's 'v' node DataValue, return (status_name, value)."""
    from asyncua import Client

    async with Client(url=url) as client:
        ns = await client.get_namespace_index("http://ghostmeter.local/opcua/")
        gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
        dev = await gm.get_child([f"{ns}:FaultMeter (#1)"])
        var = await dev.get_child([f"{ns}:v"])
        dv = await var.read_data_value(raise_on_bad_status=raise_on_bad)
        return dv.StatusCode_.name, (dv.Value.Value if dv.Value else None)


class TestOpcUaFaultApplication:
    async def test_exception_fault_yields_bad_device_failure(self):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = _free_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("exception", {}))
            await adapter.apply_fault(dev)
            status, _ = await _read_status(url)
            assert status == "BadDeviceFailure", status
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_timeout_fault_yields_bad_timeout(self):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = _free_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("timeout", {}))
            await adapter.apply_fault(dev)
            status, _ = await _read_status(url)
            assert status == "BadTimeout", status
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_delay_fault_slows_reads(self):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = _free_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("delay", {"delay_ms": 400}))
            await adapter.apply_fault(dev)
            t0 = time.monotonic()
            status, value = await _read_status(url, raise_on_bad=True)
            elapsed = time.monotonic() - t0
            assert status == "Good", status
            assert abs(value - 100.0) < 0.01
            assert elapsed >= 0.3, f"expected >=0.3s, got {elapsed:.3f}s"
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_intermittent_rate_1_always_bad(self):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = _free_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("intermittent", {"failure_rate": 1.0}))
            await adapter.apply_fault(dev)
            for _ in range(3):
                status, _ = await _read_status(url)
                assert status == "BadCommunicationError", status
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_intermittent_rate_0_always_good(self):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = _free_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("intermittent", {"failure_rate": 0.0}))
            await adapter.apply_fault(dev)
            status, value = await _read_status(url, raise_on_bad=True)
            assert status == "Good"
            assert abs(value - 100.0) < 0.01
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_update_register_during_fault_does_not_clear_callback(self):
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = _free_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("exception", {}))
            await adapter.apply_fault(dev)
            # Simulation engine keeps pushing values during the fault:
            await adapter.update_register(dev, 0, 3, 222.0, "float32", "big_endian")
            status, _ = await _read_status(url)
            assert status == "BadDeviceFailure", status  # callback still active
            # but the cache tracked the latest value
            assert abs(adapter._last_values[(dev, 0, 3)][0] - 222.0) < 0.01
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_clear_fault_restores_value_and_subscription(self):
        from asyncua import Client

        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = _free_port()
        adapter, dev, url = await _make_running_device(port)
        try:
            fault_simulator.set_fault(dev, FaultConfig("exception", {}))
            await adapter.apply_fault(dev)
            # clear
            fault_simulator.clear_fault(dev)
            await adapter.remove_fault(dev)

            async with Client(url=url) as client:
                ns = await client.get_namespace_index("http://ghostmeter.local/opcua/")
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                d = await gm.get_child([f"{ns}:FaultMeter (#1)"])
                var = await d.get_child([f"{ns}:v"])
                # value readable again (the cached 100.0)
                assert abs(await var.read_value() - 100.0) < 0.01
                # subscription resumes
                handler = _SubHandler()
                sub = await client.create_subscription(50, handler)
                await sub.subscribe_data_change(var)
                await asyncio.sleep(0.3)
                await adapter.update_register(dev, 0, 3, 175.0, "float32", "big_endian")
                await asyncio.sleep(0.5)
                await sub.delete()
                assert any(abs(v - 175.0) < 0.05 for v in handler.values), handler.values
        finally:
            fault_simulator.clear_all()
            await adapter.stop()

    async def test_fault_reattaches_on_device_add(self):
        """A fault set before the device is added is re-applied on add (parity with
        Modbus, where the fault survives a device stop/start)."""
        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import FaultConfig

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        dev = uuid.uuid4()
        try:
            fault_simulator.set_fault(dev, FaultConfig("exception", {}))
            adapter.set_device_meta(dev, "FaultMeter")
            await adapter.add_device(dev, 1, [RegisterInfo(0, 3, "float32", "big_endian", name="v")])
            assert dev in adapter._faulted
            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            status, _ = await _read_status(url)
            assert status == "BadDeviceFailure", status
        finally:
            fault_simulator.clear_all()
            await adapter.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter" ./.venv/bin/python -m pytest tests/test_opcua_fault.py::TestOpcUaFaultApplication -v`
Expected: FAIL (e.g. `AttributeError: 'OpcUaAdapter' object has no attribute 'apply_fault'`, or callbacks not applied so status is `Good`).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/protocols/opcua_agent.py`, add these methods to `OpcUaAdapter` (place them after `update_register`, before `set_device_meta`):

```python
    # --- Fault application (overrides base no-op) ---

    def _bad_datavalue(self, status_code: int) -> "ua.DataValue":
        """Build a DataValue carrying a Bad StatusCode (no value)."""
        dv = ua.DataValue()
        dv.StatusCode_ = ua.StatusCode(status_code)
        return dv

    def _good_datavalue(self, key: tuple[UUID, int, int]) -> "ua.DataValue":
        """Build a Good DataValue from the latest cached value for a node."""
        value, vtype = self._last_values.get(key, (0, ua.VariantType.Double))
        return ua.DataValue(ua.Variant(value, vtype))

    def _make_fault_callback(self, device_id: UUID, key: tuple[UUID, int, int]):
        """Create the synchronous value callback asyncua calls on every read.

        Reads fault_simulator live so it reflects the current fault type/params
        (single source of truth, same model as Modbus trace_pdu).
        """
        from app.simulation import fault_simulator

        def cb(nodeid, attr):  # noqa: ANN001 — asyncua calls cb(nodeid, attr)
            fault = fault_simulator.get_fault(device_id)
            if fault is None:
                return self._good_datavalue(key)
            ftype = fault.fault_type
            if ftype == "exception":
                return self._bad_datavalue(ua.StatusCodes.BadDeviceFailure)
            if ftype == "timeout":
                return self._bad_datavalue(ua.StatusCodes.BadTimeout)
            if ftype == "delay":
                delay_ms = min(int(fault.params.get("delay_ms", 500)), 10000)
                time.sleep(delay_ms / 1000.0)  # bounded blocking (mirrors Modbus)
                return self._good_datavalue(key)
            if ftype == "intermittent":
                rate = float(fault.params.get("failure_rate", 0.5))
                if random.random() < rate:
                    return self._bad_datavalue(ua.StatusCodes.BadCommunicationError)
                return self._good_datavalue(key)
            return self._good_datavalue(key)  # unknown type → behave normally

        return cb

    async def apply_fault(self, device_id: UUID) -> None:
        """Attach a value callback to each of the device's nodes (idempotent)."""
        if self._server is None or device_id in self._faulted:
            return
        aspace = self._server.iserver.aspace
        for key, node in list(self._nodes.items()):
            if key[0] != device_id:
                continue
            cb = self._make_fault_callback(device_id, key)
            aspace.set_attribute_value_callback(node.nodeid, ua.AttributeIds.Value, cb)
        self._faulted.add(device_id)
        logger.info("OPC UA: fault callbacks attached for device %s", device_id)

    async def remove_fault(self, device_id: UUID) -> None:
        """Detach callbacks by re-writing cached values (restores value +
        clears callback + resumes subscriptions in one write)."""
        if device_id not in self._faulted:
            return
        for key, node in list(self._nodes.items()):
            if key[0] != device_id:
                continue
            value, vtype = self._last_values.get(key, (0, ua.VariantType.Double))
            try:
                await node.write_value(ua.Variant(value, vtype))
            except Exception:
                logger.debug("OPC UA: error restoring node after fault clear", exc_info=True)
        self._faulted.discard(device_id)
        logger.info("OPC UA: fault callbacks removed for device %s", device_id)
```

Then, at the END of `_do_add_device` (after the existing `logger.info("OPC UA: added device ...")` call), add the re-attach check:

```python
        from app.simulation import fault_simulator
        if fault_simulator.get_fault(device_id) is not None:
            await self.apply_fault(device_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter" ./.venv/bin/python -m pytest tests/test_opcua_fault.py tests/test_opcua_adapter.py -v`
Expected: all PASS (new fault tests pass; existing adapter/subscription tests still pass).

- [ ] **Step 5: Commit**

```bash
git add backend/app/protocols/opcua_agent.py backend/tests/test_opcua_fault.py
git commit -m "feat: implement OPC UA comm-layer fault application via value callbacks"
```

---

## Task 4: REST wiring (`set_fault`/`clear_fault` → adapter hook)

**Files:**
- Modify: `backend/app/services/device_service.py` (add `get_device_protocol`)
- Modify: `backend/app/api/routes/simulation.py`
- Test: `backend/tests/test_opcua_fault.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_opcua_fault.py`:

```python
class TestOpcUaFaultRestWiring:
    async def test_put_fault_applies_to_opcua_then_delete_clears(self, client):
        from asyncua import Client

        from app.protocols import protocol_manager
        from app.protocols.opcua_agent import OpcUaAdapter
        from app.simulation import fault_simulator

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        protocol_manager.register_adapter("opcua", adapter)
        await protocol_manager.start_all()
        try:
            tpl = await client.post("/api/v1/templates", json={
                "name": "Fault-OPCUA",
                "protocol": "opcua",
                "registers": [
                    {"name": "v", "address": 0, "function_code": 3,
                     "data_type": "float32", "byte_order": "big_endian",
                     "scale_factor": 1.0, "unit": "V", "sort_order": 0},
                ],
            })
            assert tpl.status_code == 201
            template_id = tpl.json()["data"]["id"]

            dev = await client.post("/api/v1/devices", json={
                "name": "RestFaultMeter", "template_id": template_id,
                "slave_id": 1, "port": 4840,
            })
            assert dev.status_code == 201
            device_id = dev.json()["data"]["id"]
            assert (await client.post(f"/api/v1/devices/{device_id}/start")).status_code == 200

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"

            async def read_status():
                async with Client(url=url) as opc:
                    ns = await opc.get_namespace_index("http://ghostmeter.local/opcua/")
                    gm = await opc.nodes.objects.get_child([f"{ns}:GhostMeter"])
                    d = await gm.get_child([f"{ns}:RestFaultMeter (#1)"])
                    var = await d.get_child([f"{ns}:v"])
                    dv = await var.read_data_value(raise_on_bad_status=False)
                    return dv.StatusCode_.name

            # PUT fault → OPC UA reads go Bad
            put = await client.put(
                f"/api/v1/devices/{device_id}/fault",
                json={"fault_type": "exception", "params": {}},
            )
            assert put.status_code == 200
            assert await read_status() == "BadDeviceFailure"

            # DELETE fault → reads recover
            assert (await client.delete(f"/api/v1/devices/{device_id}/fault")).status_code == 200
            assert await read_status() == "Good"
        finally:
            fault_simulator.clear_all()
            await protocol_manager.stop_all()
            protocol_manager._adapters.pop("opcua", None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter" ./.venv/bin/python -m pytest tests/test_opcua_fault.py::TestOpcUaFaultRestWiring -v`
Expected: FAIL — after PUT, status is still `Good` because the REST endpoint does not yet call `apply_fault`.

- [ ] **Step 3: Write minimal implementation**

(a) In `backend/app/services/device_service.py`, add this helper after `_get_device_raw`:

```python
async def get_device_protocol(
    session: AsyncSession, device_id: uuid.UUID,
) -> str:
    """Resolve a device's protocol via its template. Raises 404 if absent."""
    device = await _get_device_raw(session, device_id)
    template = await get_template_with_registers(session, device.template_id)
    return template.protocol
```

(b) In `backend/app/api/routes/simulation.py`, add imports near the existing ones:

```python
from app.protocols import protocol_manager
from app.services import device_service
```

(c) Replace the `set_fault` handler body and signature with:

```python
async def set_fault(
    device_id: uuid.UUID,
    data: FaultConfigSet,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[FaultConfigResponse]:
    """Set a communication fault on a device (in-memory) and apply it to the adapter."""
    fault = FaultConfig(fault_type=data.fault_type, params=data.params)
    fault_simulator.set_fault(device_id, fault)

    protocol = await device_service.get_device_protocol(session, device_id)
    adapter = protocol_manager.get_adapter(protocol)
    if adapter is not None and protocol_manager.is_running:
        await adapter.apply_fault(device_id)

    monitor_service.log_event(
        device_id, str(device_id), "fault_set",
        f"Fault set: {data.fault_type}",
    )
    return ApiResponse(
        data=FaultConfigResponse(
            fault_type=fault.fault_type,
            params=fault.params,
        )
    )
```

(d) Replace the `clear_fault` handler body and signature with:

```python
async def clear_fault(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Clear the active fault for a device and detach it from the adapter."""
    fault_simulator.clear_fault(device_id)

    protocol = await device_service.get_device_protocol(session, device_id)
    adapter = protocol_manager.get_adapter(protocol)
    if adapter is not None and protocol_manager.is_running:
        await adapter.remove_fault(device_id)

    monitor_service.log_event(
        device_id, str(device_id), "fault_clear", "Fault cleared",
    )
    return ApiResponse(message="Fault cleared successfully")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter" ./.venv/bin/python -m pytest tests/test_opcua_fault.py::TestOpcUaFaultRestWiring -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/device_service.py backend/app/api/routes/simulation.py backend/tests/test_opcua_fault.py
git commit -m "feat: wire REST fault set/clear to OPC UA adapter via apply_fault/remove_fault"
```

---

## Task 5: Full suite, lint, and docs

**Files:**
- Modify: `CHANGELOG.md`, `docs/development-log.md`, `docs/development-phases.md`, `docs/api-reference.md`

- [ ] **Step 1: Run the full backend suite + lint**

Run:
```bash
cd backend && DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter" ./.venv/bin/python -m pytest -q
./.venv/bin/ruff check app tests
```
Expected: all tests PASS, ruff clean. Fix any failures before continuing. (If `ruff` flags the new `import random`/`import time` ordering, run `./.venv/bin/ruff check --fix app tests`.)

- [ ] **Step 2: Update `CHANGELOG.md`**

Under `## [Unreleased]`, add to the appropriate `### Added` list:
```markdown
- OPC UA comm-layer fault simulation: delay / timeout / exception / intermittent now
  apply to OPC UA devices via per-node value callbacks (push-based; attaches on fault set,
  detaches on clear). Modbus behavior unchanged.
```

- [ ] **Step 3: Update `docs/development-log.md`**

Add a dated entry summarizing: the asyncua value-callback constraint (callback replaces stored reads + clears stored value; detach via re-write), why the design is push-based, the per-node cache, the base `apply_fault`/`remove_fault` hook, REST wiring, and the bounded-blocking `delay` caveat.

- [ ] **Step 4: Update `docs/development-phases.md`**

Mark the OPC UA fault-simulation milestone status (In Progress → Complete) and note next steps (SNMP/MQTT could reuse the base hook pattern; out of scope here).

- [ ] **Step 5: Update `docs/api-reference.md`**

For `PUT/DELETE /devices/{id}/fault`, add a note that for OPC UA devices the fault is applied at the protocol layer: `exception` → `BadDeviceFailure`, `timeout` → `BadTimeout`, `delay` → bounded server-side sleep, `intermittent` → random `BadCommunicationError` by `failure_rate`. No request/response schema change.

- [ ] **Step 6: Commit**

```bash
git add CHANGELOG.md docs/development-log.md docs/development-phases.md docs/api-reference.md
git commit -m "docs: document OPC UA comm-layer fault simulation"
```

---

## Self-review notes (for the implementer)

- **Modbus untouched:** only `base.py` gains two no-op methods; `modbus_tcp.py` is not modified. Task 1's test proves Modbus inherits no-ops.
- **Subscription safety:** `update_register` only skips `write_value` while `device_id in self._faulted`; outside a fault it behaves exactly as before, so existing subscription tests must keep passing (verified in Tasks 2 & 3 Step 4).
- **Single source of truth:** the callback reads `fault_simulator.get_fault` live; the base hook is a presence toggle only.
- **Cleanup:** every test that calls `fault_simulator.set_fault` must `fault_simulator.clear_all()` in `finally` to avoid leaking fault state across tests (the simulator is a module singleton).
