# Protocol Adapter Abstraction Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Formalize the ProtocolAdapter base class so that new protocol adapters get stats lifecycle automatically and consumers access stats through ProtocolManager without knowing adapter types.

**Architecture:** Template method pattern for `add_device`/`remove_device` in base class handles `DeviceStats` lifecycle. Concrete `get_stats`/`reset_stats` in base. ProtocolManager proxies stats with graceful error handling. MonitorService decoupled from ModbusTcpAdapter.

**Tech Stack:** Python 3.12, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-23-protocol-adapter-abstraction-design.md`

**Note on tests:** No test file imports `DeviceStats` from `modbus_tcp.py`, and all tests use the public `adapter.add_device()` / `adapter.remove_device()` API. These will route through the base class template methods transparently — no test changes needed.

---

## Chunk 1: Base Class + ModbusTcpAdapter Refactor

### Task 1: Move DeviceStats to base.py and add template methods

**Files:**
- Modify: `backend/app/protocols/base.py`

- [ ] **Step 1: Write the updated base.py**

Replace the entire `base.py` with:

```python
"""Protocol adapter base class and shared types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass
class RegisterInfo:
    """Lightweight register descriptor passed to protocol adapters."""

    address: int
    function_code: int  # 3=holding, 4=input
    data_type: str      # int16, uint16, int32, uint32, float32, float64
    byte_order: str     # big_endian, little_endian, etc.


@dataclass
class DeviceStats:
    """Per-device communication statistics."""

    request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_response_ms: float = 0.0

    @property
    def avg_response_ms(self) -> float:
        """Average response time in milliseconds."""
        if self.success_count == 0:
            return 0.0
        return self.total_response_ms / self.success_count


class ProtocolAdapter(ABC):
    """Base class for protocol adapters.

    Subclasses implement _do_add_device / _do_remove_device for protocol-specific
    setup. Stats lifecycle (create on add, remove on remove) is handled here.
    """

    def __init__(self) -> None:
        self._device_stats: dict[UUID, DeviceStats] = {}

    # --- Stats (concrete, inherited by all adapters) ---

    def get_stats(self, device_id: UUID) -> DeviceStats | None:
        """Get communication stats for a device."""
        return self._device_stats.get(device_id)

    def reset_stats(self, device_id: UUID) -> None:
        """Reset stats counters for a device."""
        if device_id in self._device_stats:
            self._device_stats[device_id] = DeviceStats()

    # --- Device lifecycle (template methods) ---

    async def add_device(
        self,
        device_id: UUID,
        slave_id: int,
        registers: list[RegisterInfo],
    ) -> None:
        """Register a device — creates stats entry, then delegates to subclass."""
        self._device_stats[device_id] = DeviceStats()
        await self._do_add_device(device_id, slave_id, registers)

    async def remove_device(self, device_id: UUID) -> None:
        """Unregister a device — delegates to subclass, then cleans up stats.

        Subclass cleanup runs first so it can still access stats during teardown.
        Stats are removed last.
        """
        await self._do_remove_device(device_id)
        self._device_stats.pop(device_id, None)

    # --- Abstract methods (subclasses must implement) ---

    @abstractmethod
    async def start(self) -> None:
        """Start the protocol server."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the protocol server."""

    @abstractmethod
    async def _do_add_device(
        self,
        device_id: UUID,
        slave_id: int,
        registers: list[RegisterInfo],
    ) -> None:
        """Protocol-specific device registration."""

    @abstractmethod
    async def _do_remove_device(self, device_id: UUID) -> None:
        """Protocol-specific device unregistration."""

    @abstractmethod
    async def update_register(
        self,
        device_id: UUID,
        address: int,
        function_code: int,
        value: float,
        data_type: str,
        byte_order: str,
    ) -> None:
        """Update a register value (called by simulation engine)."""

    @abstractmethod
    def get_status(self) -> dict:
        """Return adapter status info."""
```

- [ ] **Step 2: Verify base.py is syntactically valid**

Run: `cd /media/sf_AI_Service_Chatbot/GhostMeter/backend && python -c "from app.protocols.base import ProtocolAdapter, DeviceStats, RegisterInfo; print('OK')"`

Expected: `OK`

---

### Task 2: Refactor ModbusTcpAdapter to use base class

**Files:**
- Modify: `backend/app/protocols/modbus_tcp.py`

**Important notes:**
- `self._device_stats` is referenced directly in `_create_trace_pdu` (lines 133, 157 of original). These references remain valid because the dict is now initialized by the base class `__init__`.
- `self._device_stats.clear()` in `stop()` (line 240 of original) remains as-is — it clears all stats when the server stops, which is correct behavior. This is adapter-specific teardown, not lifecycle management.
- `_do_remove_device` must preserve the early-return pattern for non-existent devices (the existing `if slave_id is None: return` guard).

- [ ] **Step 1: Update imports — replace local DeviceStats with base import**

Change:
```python
from app.protocols.base import ProtocolAdapter, RegisterInfo
```
to:
```python
from app.protocols.base import DeviceStats, ProtocolAdapter, RegisterInfo
```

Remove the entire `DeviceStats` class definition (lines 25-38 of original).

- [ ] **Step 2: Update `__init__` — call super, remove `_device_stats` init**

Add `super().__init__()` as the first line of `__init__`.

Remove `self._device_stats: dict[UUID, DeviceStats] = {}` from `__init__` (handled by super).

Keep `self._device_stats.clear()` in `stop()` — it's adapter-level cleanup.

- [ ] **Step 3: Rename `add_device` → `_do_add_device`, remove stats line**

Rename the method from `add_device` to `_do_add_device`.

Remove this line from inside the method:
```python
self._device_stats[device_id] = DeviceStats()
```

Keep all other logic (context creation, slave registration, etc.) unchanged.

- [ ] **Step 4: Rename `remove_device` → `_do_remove_device`, remove stats line**

Rename the method from `remove_device` to `_do_remove_device`.

Remove this line from inside the method:
```python
self._device_stats.pop(device_id, None)
```

Keep the early-return guard `if slave_id is None: return` — it ensures non-existent device removal is a no-op.

- [ ] **Step 5: Remove `get_stats` and `reset_stats` methods**

Delete the `get_stats` and `reset_stats` methods entirely (inherited from base).

- [ ] **Step 6: Run existing tests to verify nothing broke**

Run: `cd /media/sf_AI_Service_Chatbot/GhostMeter/backend && python -m pytest tests/test_modbus.py tests/test_modbus_fault.py -v`

Expected: All tests PASS. Tests call `adapter.add_device()` / `adapter.remove_device()` which now route through base class template methods → `_do_add_device` / `_do_remove_device`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/protocols/base.py backend/app/protocols/modbus_tcp.py
git commit -m "refactor: move DeviceStats to base class, use template methods for device lifecycle"
```

---

## Chunk 2: ProtocolManager + MonitorService + Final Verification

### Task 3: Add stats proxy methods to ProtocolManager

**Files:**
- Modify: `backend/app/protocols/manager.py`

- [ ] **Step 1: Add import for DeviceStats**

Change:
```python
from app.protocols.base import ProtocolAdapter, RegisterInfo
```
to:
```python
from app.protocols.base import DeviceStats, ProtocolAdapter, RegisterInfo
```

- [ ] **Step 2: Add `get_stats` proxy method**

Add to `ProtocolManager` class:

```python
def get_stats(self, protocol: str, device_id: UUID) -> DeviceStats | None:
    """Get device stats via the named adapter. Returns None if adapter not found."""
    adapter = self._adapters.get(protocol)
    if adapter is None:
        return None
    return adapter.get_stats(device_id)
```

- [ ] **Step 3: Add `reset_stats` proxy method**

Add to `ProtocolManager` class:

```python
def reset_stats(self, protocol: str, device_id: UUID) -> None:
    """Reset device stats via the named adapter. No-op if adapter not found."""
    adapter = self._adapters.get(protocol)
    if adapter is not None:
        adapter.reset_stats(device_id)
```

- [ ] **Step 4: Verify import works**

Run: `cd /media/sf_AI_Service_Chatbot/GhostMeter/backend && python -c "from app.protocols.manager import ProtocolManager; print('OK')"`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/protocols/manager.py
git commit -m "feat: add stats proxy methods to ProtocolManager"
```

---

### Task 4: Decouple MonitorService from ModbusTcpAdapter

**Files:**
- Modify: `backend/app/services/monitor_service.py`

- [ ] **Step 1: Remove ModbusTcpAdapter import and get_adapter block**

In `get_snapshot` method, remove this lazy import (line 70):

```python
from app.protocols.modbus_tcp import ModbusTcpAdapter
```

and remove this entire block (lines 84-89):
```python
# Get adapter for stats
adapter: ModbusTcpAdapter | None = None
try:
    adapter = protocol_manager.get_adapter("modbus_tcp")  # type: ignore[assignment]
except KeyError:
    pass
```

- [ ] **Step 2: Replace adapter.get_stats with protocol_manager.get_stats**

Replace this block (lines 127-135):
```python
if adapter:
    stats = adapter.get_stats(device_id)
    if stats:
        stats_data = {
            "request_count": stats.request_count,
            "success_count": stats.success_count,
            "error_count": stats.error_count,
            "avg_response_ms": round(stats.avg_response_ms, 1),
        }
```

with:
```python
stats = protocol_manager.get_stats("modbus_tcp", device_id)
if stats:
    stats_data = {
        "request_count": stats.request_count,
        "success_count": stats.success_count,
        "error_count": stats.error_count,
        "avg_response_ms": round(stats.avg_response_ms, 1),
    }
```

The outer `if adapter:` guard is removed because `protocol_manager.get_stats` handles missing adapters internally (returns None).

- [ ] **Step 3: Run all tests**

Run: `cd /media/sf_AI_Service_Chatbot/GhostMeter/backend && python -m pytest -v`

Expected: All existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/monitor_service.py
git commit -m "refactor: decouple MonitorService from ModbusTcpAdapter, use ProtocolManager for stats"
```

---

### Task 5: Update __init__.py exports and final verification

**Files:**
- Modify: `backend/app/protocols/__init__.py`

- [ ] **Step 1: Update __init__.py to export DeviceStats**

Replace entire file with:

```python
from app.protocols.base import DeviceStats, ProtocolAdapter, RegisterInfo
from app.protocols.manager import ProtocolManager

protocol_manager = ProtocolManager()

__all__ = ["protocol_manager", "DeviceStats", "ProtocolAdapter", "RegisterInfo"]
```

This preserves the existing `protocol_manager` singleton while adding base class exports.

- [ ] **Step 2: Run full test suite one final time**

Run: `cd /media/sf_AI_Service_Chatbot/GhostMeter/backend && python -m pytest -v --tb=short`

Expected: All tests PASS.

- [ ] **Step 3: Verify no remaining ModbusTcpAdapter references in monitor_service.py**

Run: `grep -n "ModbusTcpAdapter" backend/app/services/monitor_service.py`

Expected: No output (no references).

- [ ] **Step 4: Commit**

```bash
git add backend/app/protocols/__init__.py
git commit -m "chore: export DeviceStats from protocols package"
```
