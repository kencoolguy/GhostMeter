# Protocol Adapter Abstraction — Design Spec

**Date**: 2026-03-23
**Status**: Approved
**Scope**: Refactor `backend/app/protocols/` to formalize the adapter abstraction layer

## Goal

Clean up the Protocol Adapter interface so that adding a second protocol (MQTT, BACnet, SNMP) requires only implementing a new adapter class — no changes to the Manager, MonitorService, or other consumers.

## Current State

- `base.py` defines `ProtocolAdapter` ABC with 6 abstract methods: `start`, `stop`, `add_device`, `remove_device`, `update_register`, `get_status`
- `modbus_tcp.py` implements `ModbusTcpAdapter` with additional non-interface methods: `get_stats`, `reset_stats`, `get_device_id_for_slave`
- `manager.py` provides `ProtocolManager` that routes calls by protocol name
- `DeviceStats` dataclass lives in `modbus_tcp.py` but is conceptually protocol-agnostic
- `MonitorService` uses `protocol_manager.get_adapter("modbus_tcp")` with a `type: ignore` cast to `ModbusTcpAdapter` to access stats

## Design Decisions

### 1. Move `DeviceStats` and stats methods to base class

**Why**: Communication statistics (request count, error count, latency) are universal across protocols. Every adapter needs them for the Monitor Dashboard.

**What**:
- Move `DeviceStats` dataclass from `modbus_tcp.py` to `base.py`
- Add concrete (non-abstract) `get_stats(device_id) -> DeviceStats | None` with default implementation in `ProtocolAdapter`
- Add concrete (non-abstract) `reset_stats(device_id) -> None` with default implementation in `ProtocolAdapter`
- `ProtocolAdapter.__init__` initializes `self._device_stats: dict[UUID, DeviceStats] = {}`
- Abstract method count remains at 6 (unchanged)

**Stats lifecycle managed by base class**: The base `add_device` and `remove_device` are changed from pure abstract to template methods — they handle `_device_stats` creation/removal, then call the abstract `_do_add_device` / `_do_remove_device` that subclasses implement. This ensures every adapter gets correct stats lifecycle without manual bookkeeping.

```python
class ProtocolAdapter(ABC):
    def __init__(self):
        self._device_stats: dict[UUID, DeviceStats] = {}

    async def add_device(self, device_id, slave_id, registers) -> None:
        self._device_stats[device_id] = DeviceStats()
        await self._do_add_device(device_id, slave_id, registers)

    async def remove_device(self, device_id) -> None:
        self._device_stats.pop(device_id, None)
        await self._do_remove_device(device_id)

    @abstractmethod
    async def _do_add_device(self, device_id, slave_id, registers) -> None: ...

    @abstractmethod
    async def _do_remove_device(self, device_id) -> None: ...
```

### 2. Add stats proxy methods to `ProtocolManager`

**Why**: Consumers (MonitorService) should go through Manager, not import specific adapter classes.

**What**:
- `ProtocolManager.get_stats(protocol, device_id) -> DeviceStats | None` — returns `None` if adapter not found (no KeyError)
- `ProtocolManager.reset_stats(protocol, device_id) -> None` — no-op if adapter not found

Error handling: proxy methods catch `KeyError` internally and return `None` / no-op, since stats are non-critical and shouldn't crash the caller.

### 3. Update `ModbusTcpAdapter`

**What**:
- Remove `DeviceStats` class definition (import from `base`)
- Remove `get_stats` / `reset_stats` methods (inherited from base)
- Remove `self._device_stats` initialization from `__init__` (handled by `super().__init__()`)
- Remove `self._device_stats[device_id] = DeviceStats()` from `add_device` (handled by base template)
- Remove `self._device_stats.pop(device_id, None)` from `remove_device` (handled by base template)
- Rename `add_device` → `_do_add_device`, `remove_device` → `_do_remove_device`
- Add `super().__init__()` call in `__init__`
- Keep `get_device_id_for_slave` (Modbus-specific, not in interface)
- Keep `encode_value` helper function (Modbus-specific encoding)
- Keep `trace_pdu` with direct `fault_simulator` import (protocol-specific fault interception)

### 4. Update `MonitorService`

**What**:
- Remove the `adapter: ModbusTcpAdapter` variable and `get_adapter("modbus_tcp")` call with `type: ignore` cast
- Remove `ModbusTcpAdapter` import
- Replace `adapter.get_stats(device_id)` calls with `protocol_manager.get_stats("modbus_tcp", device_id)`

## Not In Scope

- **Fault interception abstraction**: Each protocol intercepts faults differently (`trace_pdu` for Modbus, message-level for MQTT). Adapters import `fault_simulator` directly.
- **Protocol field on device model**: Not needed until a second protocol is actually added.
- **New protocol implementations**: This spec only formalizes the interface.
- **Backward-compatibility re-export**: No external code imports `DeviceStats` from `modbus_tcp.py`, so no re-export needed.

## Files Changed

| File | Change |
|------|--------|
| `backend/app/protocols/base.py` | Add `DeviceStats`, template methods for add/remove, default `get_stats`/`reset_stats`, `__init__` |
| `backend/app/protocols/manager.py` | Add `get_stats`/`reset_stats` proxy methods with graceful error handling |
| `backend/app/protocols/modbus_tcp.py` | Remove duplicated stats code, rename to `_do_add_device`/`_do_remove_device`, call `super().__init__()` |
| `backend/app/services/monitor_service.py` | Remove `ModbusTcpAdapter` import, use `ProtocolManager.get_stats` |
| Tests | Update if any reference `DeviceStats` from old location or call `add_device`/`remove_device` directly |

## Success Criteria

- All existing tests pass (177 tests)
- `DeviceStats` importable from `app.protocols.base`
- `ModbusTcpAdapter` inherits stats methods without overriding
- `MonitorService` accesses stats through `ProtocolManager` only — no direct adapter type references
- New adapter only needs: subclass `ProtocolAdapter`, implement `start`, `stop`, `_do_add_device`, `_do_remove_device`, `update_register`, `get_status`, register in Manager — stats lifecycle is automatic
