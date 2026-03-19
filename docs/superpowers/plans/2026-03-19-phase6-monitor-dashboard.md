# Phase 6: Monitor Dashboard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real-time monitoring dashboard with WebSocket-powered live device data, communication statistics, and event logging.

**Architecture:** Centralized MonitorService aggregates data from SimulationEngine, AnomalyInjector, FaultSimulator, and ModbusTcpAdapter. A WebSocket endpoint broadcasts snapshots at 1Hz. Frontend uses Zustand store + Recharts for live visualization.

**Tech Stack:** FastAPI WebSocket, asyncio broadcast task, Zustand, Recharts, Ant Design 5

**Spec:** `docs/superpowers/specs/2026-03-19-phase6-monitor-dashboard-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `backend/app/services/monitor_service.py` | Event log buffer + snapshot aggregation |
| `backend/app/api/websocket.py` | WebSocket endpoint + broadcast loop |
| `backend/tests/test_monitor_service.py` | MonitorService unit tests |
| `backend/tests/test_websocket.py` | WebSocket integration tests |
| `frontend/src/types/monitor.ts` | Monitor TypeScript interfaces |
| `frontend/src/hooks/useWebSocket.ts` | WebSocket connection hook |
| `frontend/src/stores/monitorStore.ts` | Zustand monitor state |
| `frontend/src/pages/Monitor/ConnectionBadge.tsx` | WS connection status indicator |
| `frontend/src/pages/Monitor/DeviceCard.tsx` | Single device status card |
| `frontend/src/pages/Monitor/DeviceCardGrid.tsx` | Card wall container |
| `frontend/src/pages/Monitor/DeviceDetailPanel.tsx` | Detail panel container |
| `frontend/src/pages/Monitor/RegisterTable.tsx` | Live register value table |
| `frontend/src/pages/Monitor/RegisterChart.tsx` | Recharts line chart |
| `frontend/src/pages/Monitor/StatsPanel.tsx` | Communication stats display |
| `frontend/src/pages/Monitor/EventLog.tsx` | Event log list |

### Modified Files
| File | Change |
|------|--------|
| `backend/app/protocols/modbus_tcp.py` | Add `DeviceStats`, per-device stat tracking in `_create_trace_pdu()` |
| `backend/app/main.py` | Register WS route, start/stop broadcast task in lifespan |
| `backend/app/services/device_service.py` | Add `monitor_service.log_event()` on start/stop |
| `backend/app/api/routes/anomaly.py` | Add `monitor_service.log_event()` on inject/remove/clear |
| `backend/app/api/routes/simulation.py` | Add `monitor_service.log_event()` on fault set/clear |
| `frontend/src/types/index.ts` | Re-export monitor types |
| `frontend/src/pages/Monitor/index.tsx` | Replace skeleton with full dashboard |
| `frontend/package.json` | Add `recharts` dependency |

---

## Chunk 1: Backend — Communication Stats + MonitorService

### Task 1: Add DeviceStats to ModbusTcpAdapter

**Files:**
- Modify: `backend/app/protocols/modbus_tcp.py`
- Test: `backend/tests/test_device_stats.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_device_stats.py`:

```python
"""Unit tests for DeviceStats in ModbusTcpAdapter."""

import uuid

import pytest

from app.protocols.modbus_tcp import DeviceStats


class TestDeviceStats:
    def test_initial_values(self):
        stats = DeviceStats()
        assert stats.request_count == 0
        assert stats.success_count == 0
        assert stats.error_count == 0
        assert stats.total_response_time_ms == 0.0

    def test_avg_response_time_no_success(self):
        stats = DeviceStats()
        assert stats.avg_response_time_ms == 0.0

    def test_avg_response_time_with_data(self):
        stats = DeviceStats(
            success_count=10,
            total_response_time_ms=250.0,
        )
        assert stats.avg_response_time_ms == 25.0

    def test_to_dict(self):
        stats = DeviceStats(
            request_count=100,
            success_count=95,
            error_count=5,
            total_response_time_ms=950.0,
        )
        result = stats.to_dict()
        assert result == {
            "request_count": 100,
            "success_count": 95,
            "error_count": 5,
            "avg_response_time_ms": 10.0,
        }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_device_stats.py -v`
Expected: FAIL — `DeviceStats` not found or `to_dict` not defined.

- [ ] **Step 3: Add DeviceStats dataclass to modbus_tcp.py**

Add at top of `backend/app/protocols/modbus_tcp.py`, after existing imports (before `class ModbusTcpAdapter`):

```python
from dataclasses import dataclass, field


@dataclass
class DeviceStats:
    """Per-device communication statistics. Reset on device start, cleared on stop."""

    request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_response_time_ms: float = 0.0

    @property
    def avg_response_time_ms(self) -> float:
        """Average response time in milliseconds."""
        return self.total_response_time_ms / self.success_count if self.success_count else 0.0

    def to_dict(self) -> dict:
        """Serialize to dict for WebSocket broadcast."""
        return {
            "request_count": self.request_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "avg_response_time_ms": self.avg_response_time_ms,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_device_stats.py -v`
Expected: PASS

- [ ] **Step 5: Add stats tracking to ModbusTcpAdapter**

In `backend/app/protocols/modbus_tcp.py`, modify the `ModbusTcpAdapter` class:

1. Add `_device_stats` dict in `__init__` (after `self._device_registers` on line 102):

```python
        self._device_stats: dict[UUID, DeviceStats] = {}
```

2. Add `get_stats`, `init_stats`, `clear_stats` methods (after `get_status` method, around line 283):

```python
    def init_stats(self, device_id: UUID) -> None:
        """Initialize (reset) stats for a device."""
        self._device_stats[device_id] = DeviceStats()

    def clear_stats(self, device_id: UUID) -> None:
        """Remove stats for a device."""
        self._device_stats.pop(device_id, None)

    def get_stats(self, device_id: UUID) -> DeviceStats | None:
        """Get communication stats for a device."""
        return self._device_stats.get(device_id)
```

3. Modify `_create_trace_pdu()` to track stats. Replace the existing method body (lines 104-144) with:

```python
    def _create_trace_pdu(self):
        """Create trace_pdu callback for fault interception + stats tracking."""
        def trace_pdu(sending: bool, pdu):
            if not sending:
                # Incoming request — count it + check timeout/intermittent
                dev_id = self._slave_to_device.get(pdu.dev_id)
                if dev_id is not None:
                    stats = self._device_stats.get(dev_id)
                    if stats:
                        stats.request_count += 1

                    from app.simulation import fault_simulator
                    fault = fault_simulator.get_fault(dev_id)
                    if fault:
                        if fault.fault_type == "timeout":
                            self._suppress_slave(pdu.dev_id)
                            if stats:
                                stats.error_count += 1
                        elif fault.fault_type == "intermittent":
                            rate = fault.params.get("failure_rate", 0.5)
                            if random.random() < rate:
                                self._suppress_slave(pdu.dev_id)
                                if stats:
                                    stats.error_count += 1
                return pdu

            # Outgoing response — track success/error + check delay/exception
            dev_id = self._slave_to_device.get(pdu.dev_id)
            if dev_id is None:
                return pdu

            from app.simulation import fault_simulator
            fault = fault_simulator.get_fault(dev_id)

            if fault is None:
                # Normal response — count as success
                stats = self._device_stats.get(dev_id)
                if stats:
                    stats.success_count += 1
                return pdu

            if fault.fault_type == "delay":
                delay_ms = fault.params.get("delay_ms", 500)
                time.sleep(delay_ms / 1000.0)
                stats = self._device_stats.get(dev_id)
                if stats:
                    stats.success_count += 1
                    stats.total_response_time_ms += delay_ms
            elif fault.fault_type == "exception":
                exc_code = fault.params.get("exception_code", 0x04)
                resp = ExceptionResponse(pdu.function_code, exc_code)
                resp.transaction_id = pdu.transaction_id
                resp.dev_id = pdu.dev_id
                stats = self._device_stats.get(dev_id)
                if stats:
                    stats.error_count += 1
                return resp
            else:
                # Other fault types that reach sending (shouldn't happen, but count success)
                stats = self._device_stats.get(dev_id)
                if stats:
                    stats.success_count += 1

            return pdu

        return trace_pdu
```

4. Call `init_stats`/`clear_stats` in `add_device`/`remove_device`. In `add_device()`, add after the register setup (before the logger.info line):

```python
        self.init_stats(device_id)
```

In `remove_device()`, add after device dict cleanup:

```python
        self.clear_stats(device_id)
```

- [ ] **Step 6: Run existing Modbus tests to verify no regressions**

Run: `cd backend && python -m pytest tests/test_modbus.py tests/test_modbus_fault.py tests/test_modbus_integration.py -v`
Expected: All existing tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/protocols/modbus_tcp.py backend/tests/test_device_stats.py
git commit -m "feat: add DeviceStats tracking to ModbusTcpAdapter"
```

---

### Task 2: Create MonitorService

**Files:**
- Create: `backend/app/services/monitor_service.py`
- Test: `backend/tests/test_monitor_service.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_monitor_service.py`:

```python
"""Unit tests for MonitorService."""

import uuid
from datetime import datetime, timezone

import pytest

from app.services.monitor_service import MonitorService


@pytest.fixture
def service():
    return MonitorService()


@pytest.fixture
def device_id():
    return uuid.uuid4()


class TestEventLog:
    def test_log_event_adds_to_log(self, service, device_id):
        service.log_event(
            device_id=device_id,
            device_name="Meter #1",
            event_type="device_started",
            detail="Device started",
        )
        events = service.get_events()
        assert len(events) == 1
        assert events[0]["device_id"] == str(device_id)
        assert events[0]["device_name"] == "Meter #1"
        assert events[0]["type"] == "device_started"
        assert events[0]["detail"] == "Device started"
        assert "timestamp" in events[0]

    def test_events_ordered_newest_first(self, service, device_id):
        service.log_event(device_id, "M", "device_started", "first")
        service.log_event(device_id, "M", "device_stopped", "second")
        events = service.get_events()
        assert events[0]["type"] == "device_stopped"
        assert events[1]["type"] == "device_started"

    def test_filter_events_by_device(self, service):
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        service.log_event(id1, "M1", "device_started", "d1")
        service.log_event(id2, "M2", "device_started", "d2")
        events = service.get_events(device_id=id1)
        assert len(events) == 1
        assert events[0]["device_id"] == str(id1)

    def test_max_100_events(self, service, device_id):
        for i in range(110):
            service.log_event(device_id, "M", "device_started", f"event {i}")
        events = service.get_events()
        assert len(events) == 100
        # Most recent should be last added
        assert events[0]["detail"] == "event 109"

    def test_get_events_returns_all_when_no_filter(self, service):
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        service.log_event(id1, "M1", "device_started", "d1")
        service.log_event(id2, "M2", "device_started", "d2")
        events = service.get_events()
        assert len(events) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_monitor_service.py -v`
Expected: FAIL — `MonitorService` not found.

- [ ] **Step 3: Implement MonitorService**

Create `backend/app/services/monitor_service.py`:

```python
"""Centralized monitor service for aggregating real-time device data and events."""

import logging
from collections import deque
from datetime import datetime, timezone
from uuid import UUID

logger = logging.getLogger(__name__)


class MonitorService:
    """Aggregates device monitoring data for WebSocket broadcast.

    Maintains an in-memory event log (deque, max 100 entries).
    Snapshot assembly queries singletons: simulation_engine, anomaly_injector,
    fault_simulator, and the modbus adapter.
    """

    def __init__(self) -> None:
        self._event_log: deque[dict] = deque(maxlen=100)

    def log_event(
        self,
        device_id: UUID,
        device_name: str,
        event_type: str,
        detail: str,
    ) -> None:
        """Record a monitor event."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "device_id": str(device_id),
            "device_name": device_name,
            "type": event_type,
            "detail": detail,
        }
        self._event_log.appendleft(event)
        logger.debug("Monitor event: %s %s — %s", event_type, device_name, detail)

    def get_events(self, device_id: UUID | None = None) -> list[dict]:
        """Get events, optionally filtered by device_id."""
        if device_id is None:
            return list(self._event_log)
        device_str = str(device_id)
        return [e for e in self._event_log if e["device_id"] == device_str]

    async def get_snapshot(self) -> dict:
        """Aggregate all monitoring data into a single snapshot for broadcast.

        Queries simulation_engine, anomaly_injector, fault_simulator,
        and protocol_manager for each running device.
        """
        from app.database import async_session_factory
        from app.models.device import DeviceInstance
        from app.protocols import protocol_manager
        from app.simulation import anomaly_injector, fault_simulator, simulation_engine

        from sqlalchemy import select

        devices_data: dict[str, dict] = {}

        async with async_session_factory() as session:
            result = await session.execute(
                select(DeviceInstance).where(DeviceInstance.status != "stopped")
            )
            running_devices = result.scalars().all()

            for device in running_devices:
                device_id = device.id
                device_id_str = str(device_id)

                # Register values from simulation engine
                registers = simulation_engine.get_current_values(device_id)

                # Active anomalies (extract register names only)
                active_anomalies = list(
                    anomaly_injector.get_active(device_id).keys()
                )

                # Fault state
                fault = fault_simulator.get_fault(device_id)
                fault_data = None
                if fault:
                    fault_data = {
                        "fault_type": fault.fault_type,
                        "params": fault.params,
                    }

                # Communication stats from protocol adapter
                stats_data = {
                    "request_count": 0,
                    "success_count": 0,
                    "error_count": 0,
                    "avg_response_time_ms": 0.0,
                }
                try:
                    adapter = protocol_manager.get_adapter("modbus_tcp")
                    stats = adapter.get_stats(device_id)
                    if stats:
                        stats_data = stats.to_dict()
                except KeyError:
                    pass

                devices_data[device_id_str] = {
                    "name": device.name,
                    "status": device.status,
                    "slave_id": device.slave_id,
                    "registers": registers,
                    "active_anomalies": active_anomalies,
                    "fault": fault_data,
                    "stats": stats_data,
                }

        return {
            "type": "monitor_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "devices": devices_data,
            "events": list(self._event_log),
        }


# Module-level singleton
monitor_service = MonitorService()
```

- [ ] **Step 4: Verify existing infrastructure**

`async_session_factory` already exists in `backend/app/database.py` (line 20-24) — no changes needed.

`protocol_manager.get_adapter()` already exists in `backend/app/protocols/manager.py` (line 65-67) but raises `KeyError` if adapter not found. The `get_snapshot()` code above wraps the call with `try/except KeyError` to handle this safely. No changes needed to the manager.

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_monitor_service.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/monitor_service.py backend/tests/test_monitor_service.py
git commit -m "feat: add MonitorService with event log and snapshot aggregation"
```

---

### Task 3: Add Event Logging to Existing Services

**Files:**
- Modify: `backend/app/services/device_service.py`
- Modify: `backend/app/api/routes/anomaly.py`
- Modify: `backend/app/api/routes/simulation.py`

- [ ] **Step 1: Add log_event calls to device_service.py**

In `backend/app/services/device_service.py`:

1. Add import at top (after other imports):

```python
from app.services.monitor_service import monitor_service
```

2. In `start_device()`, add after `device.status = "running"` (line 319), before `await session.commit()`:

```python
    monitor_service.log_event(
        device.id, device.name, "device_started", f"Slave ID {device.slave_id} started"
    )
```

3. In `stop_device()`, add after `device.status = "stopped"` (line 350), before `await session.commit()`:

```python
    monitor_service.log_event(
        device.id, device.name, "device_stopped", f"Slave ID {device.slave_id} stopped"
    )
```

- [ ] **Step 2: Add log_event calls to anomaly routes**

In `backend/app/api/routes/anomaly.py`:

1. Add import:

```python
from app.services.monitor_service import monitor_service
```

2. In `inject_anomaly()`, add before `return`:

```python
    monitor_service.log_event(
        device_id, "", "anomaly_injected",
        f"{data.anomaly_type} on {data.register_name}",
    )
```

3. In `remove_anomaly()`, add before `return`:

```python
    monitor_service.log_event(
        device_id, "", "anomaly_removed",
        f"Anomaly removed from {register_name}",
    )
```

4. In `clear_anomalies()`, add before `return`:

```python
    monitor_service.log_event(
        device_id, "", "anomaly_removed", "All anomalies cleared",
    )
```

Note: `device_name` is passed as `""` here because we don't have the device name in scope in route handlers. The `get_snapshot()` method will include the full device name from DB. This is acceptable — the event log `device_name` is supplementary and can be populated later if needed.

- [ ] **Step 3: Add log_event calls to simulation routes (fault endpoints)**

In `backend/app/api/routes/simulation.py`:

1. Add import:

```python
from app.services.monitor_service import monitor_service
```

2. In `set_fault()`, add before `return`:

```python
    monitor_service.log_event(
        device_id, "", "fault_set",
        f"{data.fault_type} fault configured",
    )
```

3. In `clear_fault()`, add before `return`:

```python
    monitor_service.log_event(
        device_id, "", "fault_cleared", "Fault cleared",
    )
```

- [ ] **Step 4: Run existing tests to verify no regressions**

Run: `cd backend && python -m pytest tests/ -v --timeout=30`
Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/device_service.py backend/app/api/routes/anomaly.py backend/app/api/routes/simulation.py
git commit -m "feat: add monitor event logging to device, anomaly, and fault operations"
```

---

### Task 4: Create WebSocket Endpoint + Broadcast

**Files:**
- Create: `backend/app/api/websocket.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_websocket.py`

- [ ] **Step 1: Create WebSocket handler**

Create `backend/app/api/websocket.py`:

```python
"""WebSocket endpoint for real-time monitor data broadcast."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.monitor_service import monitor_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Connected clients set
_clients: set[WebSocket] = set()

# Broadcast task reference
_broadcast_task: asyncio.Task | None = None


@router.websocket("/ws/monitor")
async def monitor_websocket(websocket: WebSocket):
    """WebSocket endpoint for monitor data stream."""
    await websocket.accept()
    _clients.add(websocket)
    logger.info("Monitor WebSocket client connected (total: %d)", len(_clients))

    try:
        # Send immediate snapshot so client doesn't wait up to 1s
        snapshot = await monitor_service.get_snapshot()
        await websocket.send_text(json.dumps(snapshot, default=str))

        # Keep connection alive — wait for client disconnect
        while True:
            # We don't expect client messages, but must read to detect disconnect
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.warning("WebSocket client error", exc_info=True)
    finally:
        _clients.discard(websocket)
        logger.info("Monitor WebSocket client disconnected (total: %d)", len(_clients))


async def _broadcast_loop():
    """Broadcast monitor snapshot to all clients every 1 second."""
    logger.info("Monitor broadcast loop started")
    while True:
        await asyncio.sleep(1.0)

        if not _clients:
            continue

        try:
            snapshot = await monitor_service.get_snapshot()
            message = json.dumps(snapshot, default=str)
        except Exception:
            logger.error("Failed to build monitor snapshot", exc_info=True)
            continue

        disconnected: list[WebSocket] = []
        for client in _clients.copy():
            try:
                await client.send_text(message)
            except Exception:
                disconnected.append(client)
                logger.warning("Failed to send to WebSocket client, removing")

        for client in disconnected:
            _clients.discard(client)


async def start_broadcast():
    """Start the broadcast background task."""
    global _broadcast_task
    _broadcast_task = asyncio.create_task(_broadcast_loop())
    logger.info("Monitor broadcast task started")


async def stop_broadcast():
    """Stop the broadcast background task."""
    global _broadcast_task
    if _broadcast_task:
        _broadcast_task.cancel()
        try:
            await _broadcast_task
        except asyncio.CancelledError:
            pass
        _broadcast_task = None
        logger.info("Monitor broadcast task stopped")
```

- [ ] **Step 2: Register WebSocket route and broadcast in main.py**

In `backend/app/main.py`:

1. Add import (after other route imports):

```python
from app.api.websocket import router as ws_router, start_broadcast, stop_broadcast
```

2. In `lifespan()`, add after `await protocol_manager.start_all()` / before `yield`:

```python
    # Start monitor WebSocket broadcast
    await start_broadcast()
    logger.info("Monitor broadcast started")
```

3. In `lifespan()`, add at start of shutdown (before simulation_engine.shutdown):

```python
    # Stop monitor broadcast
    await stop_broadcast()
    logger.info("Monitor broadcast stopped")
```

4. Register WS router. Add after `app.include_router(api_v1_router)` (line 102):

```python
# WebSocket route (outside /api/v1 — persistent connection, not REST resource)
app.include_router(ws_router)
```

- [ ] **Step 3: Write WebSocket integration test**

Create `backend/tests/test_websocket.py`:

```python
"""Integration tests for monitor WebSocket endpoint.

Uses Starlette's synchronous TestClient for WebSocket testing,
since httpx AsyncClient does not support WebSocket connections.
The autouse setup_database fixture handles DB setup automatically.
"""

from starlette.testclient import TestClient

from app.main import app


def test_websocket_receives_initial_snapshot():
    """Verify WS client receives an immediate snapshot on connect."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/monitor") as ws:
            data = ws.receive_json()
            assert data["type"] == "monitor_update"
            assert "devices" in data
            assert "events" in data
            assert "timestamp" in data


def test_websocket_snapshot_has_correct_shape():
    """Verify the snapshot message structure."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/monitor") as ws:
            data = ws.receive_json()
            assert isinstance(data["devices"], dict)
            assert isinstance(data["events"], list)
```

Note: These are synchronous tests using Starlette's `TestClient`. The `setup_database` fixture is `autouse=True` so it runs automatically. Starlette `TestClient` manages its own event loop internally, so the async `setup_database` fixture will work correctly in the pytest-asyncio environment.

- [ ] **Step 4: Run WebSocket tests**

Run: `cd backend && python -m pytest tests/test_websocket.py -v`
Expected: PASS

- [ ] **Step 5: Run all backend tests to verify no regressions**

Run: `cd backend && python -m pytest tests/ -v --timeout=30`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/websocket.py backend/app/main.py backend/tests/test_websocket.py
git commit -m "feat: add WebSocket monitor endpoint with 1Hz broadcast"
```

---

## Chunk 2: Frontend — Types, Store, WebSocket Hook

### Task 5: Add Monitor TypeScript Types

**Files:**
- Create: `frontend/src/types/monitor.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Create monitor types file**

Create `frontend/src/types/monitor.ts`:

```typescript
// --- Monitor Dashboard Types ---

export interface DeviceMonitorData {
  name: string;
  status: "running" | "stopped" | "error";
  slave_id: number;
  registers: Record<string, number>;
  active_anomalies: string[];
  fault: FaultInfo | null;
  stats: CommunicationStats;
}

export interface FaultInfo {
  fault_type: string;
  params: Record<string, unknown>;
}

export interface CommunicationStats {
  request_count: number;
  success_count: number;
  error_count: number;
  avg_response_time_ms: number;
}

export interface MonitorEvent {
  timestamp: string;
  device_id: string;
  device_name: string;
  type:
    | "device_started"
    | "device_stopped"
    | "anomaly_injected"
    | "anomaly_removed"
    | "fault_set"
    | "fault_cleared";
  detail: string;
}

export interface MonitorUpdate {
  type: "monitor_update";
  timestamp: string;
  devices: Record<string, DeviceMonitorData>;
  events: MonitorEvent[];
}

export interface RegisterHistoryPoint {
  timestamp: number;
  value: number;
}
```

- [ ] **Step 2: Re-export from index.ts**

Add to `frontend/src/types/index.ts`:

```typescript
export type {
  CommunicationStats,
  DeviceMonitorData,
  FaultInfo,
  MonitorEvent,
  MonitorUpdate,
  RegisterHistoryPoint,
} from "./monitor";
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/monitor.ts frontend/src/types/index.ts
git commit -m "feat: add monitor dashboard TypeScript types"
```

---

### Task 6: Create Monitor Zustand Store

**Files:**
- Create: `frontend/src/stores/monitorStore.ts`

- [ ] **Step 1: Create the store**

Create `frontend/src/stores/monitorStore.ts`:

```typescript
import { create } from "zustand";
import type {
  DeviceMonitorData,
  MonitorEvent,
  MonitorUpdate,
  RegisterHistoryPoint,
} from "../types";

const MAX_HISTORY_POINTS = 300; // 5 minutes @ 1Hz

interface MonitorState {
  // Live data (replaced each second by WebSocket)
  devices: Record<string, DeviceMonitorData>;
  events: MonitorEvent[];

  // Chart history (accumulated on frontend)
  registerHistory: Record<string, RegisterHistoryPoint[]>;

  // UI state
  selectedDeviceId: string | null;
  selectedRegisters: string[];
  connectionStatus: "connected" | "connecting" | "disconnected";

  // Actions
  handleMonitorUpdate: (data: MonitorUpdate) => void;
  setConnectionStatus: (status: "connected" | "connecting" | "disconnected") => void;
  selectDevice: (deviceId: string | null) => void;
  toggleRegister: (registerName: string) => void;
}

export const useMonitorStore = create<MonitorState>((set, get) => ({
  devices: {},
  events: [],
  registerHistory: {},
  selectedDeviceId: null,
  selectedRegisters: [],
  connectionStatus: "disconnected",

  handleMonitorUpdate: (data) => {
    const state = get();
    const now = Date.now();

    // Accumulate history for selected device's selected registers
    const newHistory = { ...state.registerHistory };
    if (state.selectedDeviceId && state.selectedRegisters.length > 0) {
      const deviceData = data.devices[state.selectedDeviceId];
      if (deviceData) {
        for (const regName of state.selectedRegisters) {
          const value = deviceData.registers[regName];
          if (value !== undefined) {
            const key = `${state.selectedDeviceId}:${regName}`;
            const existing = newHistory[key] || [];
            const updated = [...existing, { timestamp: now, value }];
            // Rolling buffer: keep only last MAX_HISTORY_POINTS
            newHistory[key] = updated.length > MAX_HISTORY_POINTS
              ? updated.slice(-MAX_HISTORY_POINTS)
              : updated;
          }
        }
      }
    }

    set({
      devices: data.devices,
      events: data.events,
      registerHistory: newHistory,
    });
  },

  setConnectionStatus: (status) => set({ connectionStatus: status }),

  selectDevice: (deviceId) => {
    // Clear history when switching devices
    set({
      selectedDeviceId: deviceId,
      selectedRegisters: [],
      registerHistory: {},
    });
  },

  toggleRegister: (registerName) => {
    const state = get();
    const isSelected = state.selectedRegisters.includes(registerName);
    if (isSelected) {
      // Remove register and its history
      const newHistory = { ...state.registerHistory };
      const key = `${state.selectedDeviceId}:${registerName}`;
      delete newHistory[key];
      set({
        selectedRegisters: state.selectedRegisters.filter((r) => r !== registerName),
        registerHistory: newHistory,
      });
    } else {
      set({
        selectedRegisters: [...state.selectedRegisters, registerName],
      });
    }
  },
}));
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/stores/monitorStore.ts
git commit -m "feat: add monitor Zustand store with history accumulation"
```

---

### Task 7: Create useWebSocket Hook

**Files:**
- Create: `frontend/src/hooks/useWebSocket.ts`

- [ ] **Step 1: Create the hook**

Create `frontend/src/hooks/useWebSocket.ts`. Uses refs to avoid circular `useCallback` dependency:

```typescript
import { useEffect, useRef } from "react";
import { useMonitorStore } from "../stores/monitorStore";
import type { MonitorUpdate } from "../types";

const WS_URL = `ws://${window.location.hostname}:8000/ws/monitor`;
const MAX_RECONNECT_DELAY = 30000;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelay = useRef(1000);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Use refs for store actions to avoid stale closures
  const handleMonitorUpdate = useMonitorStore((s) => s.handleMonitorUpdate);
  const setConnectionStatus = useMonitorStore((s) => s.setConnectionStatus);
  const handleRef = useRef(handleMonitorUpdate);
  const statusRef = useRef(setConnectionStatus);
  handleRef.current = handleMonitorUpdate;
  statusRef.current = setConnectionStatus;

  useEffect(() => {
    function connect() {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;

      statusRef.current("connecting");

      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        statusRef.current("connected");
        reconnectDelay.current = 1000;
      };

      ws.onmessage = (event) => {
        try {
          const data: MonitorUpdate = JSON.parse(event.data);
          if (data.type === "monitor_update") {
            handleRef.current(data);
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        statusRef.current("disconnected");
        wsRef.current = null;
        scheduleReconnect();
      };

      ws.onerror = () => {
        // onclose will fire after onerror, reconnect handled there
      };
    }

    function scheduleReconnect() {
      if (reconnectTimer.current) return;

      reconnectTimer.current = setTimeout(() => {
        reconnectTimer.current = null;
        reconnectDelay.current = Math.min(
          reconnectDelay.current * 2,
          MAX_RECONNECT_DELAY
        );
        connect();
      }, reconnectDelay.current);
    }

    connect();

    return () => {
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors (monitorStore already exists from Task 6)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useWebSocket.ts
git commit -m "feat: add useWebSocket hook with auto-reconnect"
```

---

## Chunk 3: Frontend — Monitor Dashboard UI Components

### Task 8: Install Recharts + Create ConnectionBadge and EventLog

**Files:**
- Modify: `frontend/package.json` (via npm)
- Create: `frontend/src/pages/Monitor/ConnectionBadge.tsx`
- Create: `frontend/src/pages/Monitor/EventLog.tsx`

- [ ] **Step 1: Install Recharts**

Run: `cd frontend && npm install recharts`

- [ ] **Step 2: Create ConnectionBadge**

Create `frontend/src/pages/Monitor/ConnectionBadge.tsx`:

```tsx
import { Badge, Space, Typography } from "antd";
import { useMonitorStore } from "../../stores/monitorStore";

const STATUS_MAP = {
  connected: { status: "success" as const, text: "Connected" },
  connecting: { status: "processing" as const, text: "Connecting..." },
  disconnected: { status: "error" as const, text: "Disconnected" },
};

export function ConnectionBadge() {
  const connectionStatus = useMonitorStore((s) => s.connectionStatus);
  const { status, text } = STATUS_MAP[connectionStatus];

  return (
    <Space>
      <Badge status={status} />
      <Typography.Text type="secondary">{text}</Typography.Text>
    </Space>
  );
}
```

- [ ] **Step 3: Create EventLog**

Create `frontend/src/pages/Monitor/EventLog.tsx`:

```tsx
import { List, Tag, Typography } from "antd";
import { useMemo } from "react";
import { useMonitorStore } from "../../stores/monitorStore";
import type { MonitorEvent } from "../../types";

const EVENT_COLORS: Record<string, string> = {
  device_started: "green",
  device_stopped: "default",
  anomaly_injected: "orange",
  anomaly_removed: "blue",
  fault_set: "red",
  fault_cleared: "cyan",
};

interface EventLogProps {
  deviceId?: string | null;
  maxHeight?: number;
}

export function EventLog({ deviceId, maxHeight = 300 }: EventLogProps) {
  const events = useMonitorStore((s) => s.events);

  const filtered = useMemo(() => {
    if (!deviceId) return events;
    return events.filter((e) => e.device_id === deviceId);
  }, [events, deviceId]);

  return (
    <List
      size="small"
      dataSource={filtered}
      style={{ maxHeight, overflowY: "auto" }}
      locale={{ emptyText: "No events yet" }}
      renderItem={(event: MonitorEvent) => (
        <List.Item style={{ padding: "4px 0" }}>
          <Typography.Text type="secondary" style={{ fontSize: 12, marginRight: 8 }}>
            {new Date(event.timestamp).toLocaleTimeString()}
          </Typography.Text>
          <Tag color={EVENT_COLORS[event.type] || "default"} style={{ fontSize: 12 }}>
            {event.type.replace(/_/g, " ")}
          </Tag>
          {event.device_name && (
            <Typography.Text strong style={{ marginRight: 8, fontSize: 12 }}>
              {event.device_name}
            </Typography.Text>
          )}
          <Typography.Text style={{ fontSize: 12 }}>{event.detail}</Typography.Text>
        </List.Item>
      )}
    />
  );
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Monitor/ConnectionBadge.tsx frontend/src/pages/Monitor/EventLog.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat: add ConnectionBadge and EventLog components"
```

---

### Task 9: Create DeviceCard and DeviceCardGrid

**Files:**
- Create: `frontend/src/pages/Monitor/DeviceCard.tsx`
- Create: `frontend/src/pages/Monitor/DeviceCardGrid.tsx`

- [ ] **Step 1: Create DeviceCard**

Create `frontend/src/pages/Monitor/DeviceCard.tsx`:

```tsx
import { Badge, Card, Space, Tag, Typography } from "antd";
import type { DeviceMonitorData } from "../../types";

const STATUS_CONFIG = {
  running: { color: "#52c41a", text: "Running" },
  stopped: { color: "#d9d9d9", text: "Stopped" },
  error: { color: "#ff4d4f", text: "Error" },
};

interface DeviceCardProps {
  deviceId: string;
  device: DeviceMonitorData;
  selected: boolean;
  onClick: () => void;
}

export function DeviceCard({ deviceId, device, selected, onClick }: DeviceCardProps) {
  const { color, text } = STATUS_CONFIG[device.status];
  const hasAnomalies = device.active_anomalies.length > 0;
  const hasFault = device.fault !== null;

  return (
    <Card
      hoverable
      size="small"
      onClick={onClick}
      style={{
        borderColor: selected ? "#1677ff" : color,
        borderWidth: 2,
        width: 220,
      }}
    >
      <Space direction="vertical" size={4} style={{ width: "100%" }}>
        <Typography.Text strong ellipsis>
          {device.name}
        </Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Slave ID: {device.slave_id}
        </Typography.Text>
        <Space size={4} wrap>
          <Badge color={color} text={text} />
          {hasAnomalies && <Tag color="orange">Anomaly</Tag>}
          {hasFault && <Tag color="red">Fault</Tag>}
        </Space>
      </Space>
    </Card>
  );
}
```

- [ ] **Step 2: Create DeviceCardGrid**

Create `frontend/src/pages/Monitor/DeviceCardGrid.tsx`:

```tsx
import { Flex, Empty } from "antd";
import { useMonitorStore } from "../../stores/monitorStore";
import { DeviceCard } from "./DeviceCard";

export function DeviceCardGrid() {
  const devices = useMonitorStore((s) => s.devices);
  const selectedDeviceId = useMonitorStore((s) => s.selectedDeviceId);
  const selectDevice = useMonitorStore((s) => s.selectDevice);

  const entries = Object.entries(devices);

  if (entries.length === 0) {
    return <Empty description="No devices available. Start a device to begin monitoring." />;
  }

  return (
    <Flex wrap="wrap" gap={12}>
      {entries.map(([id, device]) => (
        <DeviceCard
          key={id}
          deviceId={id}
          device={device}
          selected={selectedDeviceId === id}
          onClick={() => selectDevice(selectedDeviceId === id ? null : id)}
        />
      ))}
    </Flex>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Monitor/DeviceCard.tsx frontend/src/pages/Monitor/DeviceCardGrid.tsx
git commit -m "feat: add DeviceCard and DeviceCardGrid components"
```

---

### Task 10: Create RegisterTable, StatsPanel, RegisterChart

**Files:**
- Create: `frontend/src/pages/Monitor/RegisterTable.tsx`
- Create: `frontend/src/pages/Monitor/StatsPanel.tsx`
- Create: `frontend/src/pages/Monitor/RegisterChart.tsx`

- [ ] **Step 1: Create RegisterTable**

Create `frontend/src/pages/Monitor/RegisterTable.tsx`:

```tsx
import { Table, Tag } from "antd";
import { useMemo } from "react";
import type { DeviceMonitorData } from "../../types";

interface RegisterTableProps {
  device: DeviceMonitorData;
}

interface RegisterRow {
  key: string;
  name: string;
  value: number;
  hasAnomaly: boolean;
}

export function RegisterTable({ device }: RegisterTableProps) {
  const dataSource: RegisterRow[] = useMemo(() => {
    return Object.entries(device.registers).map(([name, value]) => ({
      key: name,
      name,
      value,
      hasAnomaly: device.active_anomalies.includes(name),
    }));
  }, [device.registers, device.active_anomalies]);

  const columns = [
    {
      title: "Register",
      dataIndex: "name",
      key: "name",
    },
    {
      title: "Value",
      dataIndex: "value",
      key: "value",
      render: (val: number) => val?.toFixed(2) ?? "—",
    },
    {
      title: "Status",
      key: "status",
      render: (_: unknown, row: RegisterRow) =>
        row.hasAnomaly ? <Tag color="orange">Anomaly</Tag> : null,
    },
  ];

  return (
    <Table
      dataSource={dataSource}
      columns={columns}
      size="small"
      pagination={false}
      scroll={{ y: 300 }}
    />
  );
}
```

- [ ] **Step 2: Create StatsPanel**

Create `frontend/src/pages/Monitor/StatsPanel.tsx`:

```tsx
import { Card, Statistic, Row, Col } from "antd";
import type { CommunicationStats } from "../../types";

interface StatsPanelProps {
  stats: CommunicationStats;
}

export function StatsPanel({ stats }: StatsPanelProps) {
  return (
    <Row gutter={[8, 8]}>
      <Col span={12}>
        <Card size="small">
          <Statistic title="Requests" value={stats.request_count} />
        </Card>
      </Col>
      <Col span={12}>
        <Card size="small">
          <Statistic
            title="Success"
            value={stats.success_count}
            valueStyle={{ color: "#3f8600" }}
          />
        </Card>
      </Col>
      <Col span={12}>
        <Card size="small">
          <Statistic
            title="Errors"
            value={stats.error_count}
            valueStyle={stats.error_count > 0 ? { color: "#cf1322" } : undefined}
          />
        </Card>
      </Col>
      <Col span={12}>
        <Card size="small">
          <Statistic
            title="Avg RT"
            value={stats.avg_response_time_ms}
            precision={1}
            suffix="ms"
          />
        </Card>
      </Col>
    </Row>
  );
}
```

- [ ] **Step 3: Create RegisterChart**

Create `frontend/src/pages/Monitor/RegisterChart.tsx`:

```tsx
import { Checkbox, Space, Typography } from "antd";
import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { useMonitorStore } from "../../stores/monitorStore";
import type { DeviceMonitorData } from "../../types";

const COLORS = ["#1677ff", "#52c41a", "#fa8c16", "#eb2f96", "#722ed1", "#13c2c2"];

interface RegisterChartProps {
  deviceId: string;
  device: DeviceMonitorData;
}

export function RegisterChart({ deviceId, device }: RegisterChartProps) {
  const selectedRegisters = useMonitorStore((s) => s.selectedRegisters);
  const registerHistory = useMonitorStore((s) => s.registerHistory);
  const toggleRegister = useMonitorStore((s) => s.toggleRegister);

  const registerNames = useMemo(() => Object.keys(device.registers), [device.registers]);

  // Build chart data: merge all selected register histories by timestamp
  const chartData = useMemo(() => {
    if (selectedRegisters.length === 0) return [];

    // Collect all timestamps from all selected registers
    const timeMap = new Map<number, Record<string, number>>();

    for (const regName of selectedRegisters) {
      const key = `${deviceId}:${regName}`;
      const points = registerHistory[key] || [];
      for (const point of points) {
        const existing = timeMap.get(point.timestamp) || {};
        existing[regName] = point.value;
        timeMap.set(point.timestamp, existing);
      }
    }

    return Array.from(timeMap.entries())
      .sort(([a], [b]) => a - b)
      .map(([timestamp, values]) => ({
        time: new Date(timestamp).toLocaleTimeString(),
        timestamp,
        ...values,
      }));
  }, [selectedRegisters, registerHistory, deviceId]);

  return (
    <div>
      <Space size={[8, 4]} wrap style={{ marginBottom: 12 }}>
        <Typography.Text strong style={{ fontSize: 13 }}>Registers:</Typography.Text>
        {registerNames.map((name) => (
          <Checkbox
            key={name}
            checked={selectedRegisters.includes(name)}
            onChange={() => toggleRegister(name)}
          >
            {name}
          </Checkbox>
        ))}
      </Space>

      {selectedRegisters.length > 0 ? (
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            {selectedRegisters.map((regName, i) => (
              <Line
                key={regName}
                type="monotone"
                dataKey={regName}
                stroke={COLORS[i % COLORS.length]}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <Typography.Text type="secondary">
          Select registers above to display chart
        </Typography.Text>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Monitor/RegisterTable.tsx frontend/src/pages/Monitor/StatsPanel.tsx frontend/src/pages/Monitor/RegisterChart.tsx
git commit -m "feat: add RegisterTable, StatsPanel, and RegisterChart components"
```

---

### Task 11: Create DeviceDetailPanel and Assemble MonitorPage

**Files:**
- Create: `frontend/src/pages/Monitor/DeviceDetailPanel.tsx`
- Modify: `frontend/src/pages/Monitor/index.tsx`

- [ ] **Step 1: Create DeviceDetailPanel**

Create `frontend/src/pages/Monitor/DeviceDetailPanel.tsx`:

```tsx
import { Button, Card, Col, Row, Typography } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useMonitorStore } from "../../stores/monitorStore";
import { RegisterTable } from "./RegisterTable";
import { RegisterChart } from "./RegisterChart";
import { StatsPanel } from "./StatsPanel";
import { EventLog } from "./EventLog";

export function DeviceDetailPanel() {
  const selectedDeviceId = useMonitorStore((s) => s.selectedDeviceId);
  const devices = useMonitorStore((s) => s.devices);
  const selectDevice = useMonitorStore((s) => s.selectDevice);

  if (!selectedDeviceId) return null;

  const device = devices[selectedDeviceId];
  if (!device) return null;

  return (
    <div>
      <Button
        type="link"
        icon={<ArrowLeftOutlined />}
        onClick={() => selectDevice(null)}
        style={{ padding: 0, marginBottom: 12 }}
      >
        Back to overview
      </Button>

      <Typography.Title level={4} style={{ marginTop: 0 }}>
        {device.name} — Slave {device.slave_id}
      </Typography.Title>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="Register Values" size="small">
            <RegisterTable device={device} />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="Communication Stats" size="small">
            <StatsPanel stats={device.stats} />
          </Card>
        </Col>
      </Row>

      <Card title="Register Chart" size="small" style={{ marginTop: 16 }}>
        <RegisterChart deviceId={selectedDeviceId} device={device} />
      </Card>

      <Card title="Device Events" size="small" style={{ marginTop: 16 }}>
        <EventLog deviceId={selectedDeviceId} />
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Replace MonitorPage skeleton**

Replace `frontend/src/pages/Monitor/index.tsx` with:

```tsx
import { Card, Flex, Typography } from "antd";
import { useMonitorStore } from "../../stores/monitorStore";
import { useWebSocket } from "../../hooks/useWebSocket";
import { ConnectionBadge } from "./ConnectionBadge";
import { DeviceCardGrid } from "./DeviceCardGrid";
import { DeviceDetailPanel } from "./DeviceDetailPanel";
import { EventLog } from "./EventLog";

export default function MonitorPage() {
  useWebSocket();
  const selectedDeviceId = useMonitorStore((s) => s.selectedDeviceId);

  return (
    <div>
      <Flex justify="space-between" align="center" style={{ marginBottom: 16 }}>
        <Typography.Title level={2} style={{ margin: 0 }}>
          Real-time Monitor
        </Typography.Title>
        <ConnectionBadge />
      </Flex>

      {selectedDeviceId ? (
        <DeviceDetailPanel />
      ) : (
        <>
          <Card title="Devices" size="small" style={{ marginBottom: 16 }}>
            <DeviceCardGrid />
          </Card>

          <Card title="Event Log" size="small">
            <EventLog />
          </Card>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Verify dev server starts**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Monitor/DeviceDetailPanel.tsx frontend/src/pages/Monitor/index.tsx
git commit -m "feat: complete Monitor dashboard page with overview and detail views"
```

---

## Chunk 4: Integration + Documentation

### Task 12: Full Integration Verification

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && python -m pytest tests/ -v --timeout=30`
Expected: All PASS

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Start backend and verify WebSocket manually (optional)**

Run: `cd backend && python -m app.main`
In another terminal: `websocat ws://localhost:8000/ws/monitor` (or use browser dev tools)
Expected: JSON messages arriving every 1 second

- [ ] **Step 4: Fix any issues found**

Address any compile errors, test failures, or runtime issues.

---

### Task 13: Update Project Documentation

**Files:**
- Modify: `docs/development-phases.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/development-log.md`
- Modify: `docs/api-reference.md`

- [ ] **Step 1: Update development-phases.md**

Mark Phase 5 as ✅ (update any remaining unchecked items that are actually complete).
Mark Phase 6 milestones 6.1 and 6.2 as checked [x].
Update the status table: Phase 5 → ✅, Phase 6 → ✅.

- [ ] **Step 2: Update CHANGELOG.md**

Add under `## [Unreleased]`:

```markdown
### Added
- Real-time Monitor Dashboard with WebSocket-powered live data
- DeviceStats communication statistics tracking in Modbus adapter
- MonitorService for event logging and data aggregation
- WebSocket endpoint `/ws/monitor` with 1Hz broadcast
- Device card grid with status indicators and anomaly/fault badges
- Device detail panel with register table, charts, and stats
- Register line chart with user-selectable registers (Recharts)
- Event log with global and per-device filtering
- WebSocket connection status indicator with auto-reconnect
```

- [ ] **Step 3: Update development-log.md**

Add Phase 6 development log entry.

- [ ] **Step 4: Update api-reference.md**

Add WebSocket endpoint documentation:

```markdown
### WebSocket: `/ws/monitor`

Real-time monitor data stream. Sends `monitor_update` JSON messages at 1Hz.

**Connection:** `ws://{host}:8000/ws/monitor`

**Message format:** See design spec for full schema.
```

- [ ] **Step 5: Commit documentation**

```bash
git add docs/ CHANGELOG.md
git commit -m "docs: update documentation for Phase 6 monitor dashboard"
```
