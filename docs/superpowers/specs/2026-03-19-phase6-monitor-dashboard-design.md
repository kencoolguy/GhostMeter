# Phase 6: Monitor Dashboard — Design Spec

## Overview

GhostMeter Phase 6 adds a real-time monitoring dashboard that displays live device register values, communication statistics, anomaly/fault status, and system events via WebSocket.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data push strategy | Full broadcast (all running devices, 1Hz) | MVP device count is small (<50), simplest architecture, easy to add subscription later |
| Communication stats lifecycle | Per device run session | Stats reset on device start, cleared on stop — each simulation run is an independent test session |
| Chart register selection | User-selectable | Users pick which registers to chart (checkbox list), most flexible |
| Event log scope | Global + per-device filtered | Single event buffer, frontend filters by device_id — minimal added complexity |
| Architecture approach | Centralized MonitorService + WebSocket broadcast | Follows existing layered pattern (routes → services → models), clean separation of concerns |

---

## Backend Architecture

### 1. Communication Stats (modify ModbusTcpAdapter)

Add per-device statistics tracking in `backend/app/protocols/modbus_tcp.py`:

```python
@dataclass
class DeviceStats:
    request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_response_time_ms: float = 0.0

    @property
    def avg_response_time_ms(self) -> float:
        return self.total_response_time_ms / self.success_count if self.success_count else 0.0
```

- Increment counters in existing `_create_trace_pdu()` callback (request interception point already exists)
- `get_stats(device_id: UUID) -> DeviceStats | None`
- Initialize on device start, clear on device stop

### 2. MonitorService (new)

`backend/app/services/monitor_service.py` — singleton pattern (consistent with `simulation_engine`, `anomaly_injector`, `fault_simulator`):

```
MonitorService
├── _event_log: deque(maxlen=100)           # Global event buffer (in-memory only, no DB table)
├── log_event(device_id, event_type, detail) # Record event with UTC timestamp
├── get_events(device_id=None) -> list       # All events or filtered by device
└── get_snapshot() -> MonitorSnapshot        # Aggregate all data for WebSocket broadcast
```

`get_snapshot()` queries on each call:
- `SimulationEngine.get_current_values(device_id)` — live register values
- `AnomalyInjector.get_active(device_id)` — active anomaly register names
- `FaultSimulator.get_fault(device_id)` — current fault config
- `ModbusTcpAdapter.get_stats(device_id)` — communication statistics
- Device status from DB (running/stopped/error)
- Recent events from `_event_log`

Event sources — add `monitor_service.log_event()` calls in:
- `device_service`: device start/stop
- Anomaly routes: inject/remove
- Fault routes: set/clear

### 3. WebSocket Endpoint (new)

`backend/app/api/websocket.py`:

- Endpoint: `GET /ws/monitor`
- On connect: add to client set. On disconnect: remove.
- Dedicated asyncio task: every 1 second, call `MonitorService.get_snapshot()`, serialize to JSON, broadcast to all connected clients.
- Start/stop broadcast task in FastAPI lifespan.

### WebSocket Message Format

```json
{
  "type": "monitor_update",
  "timestamp": "2026-03-19T10:00:00Z",
  "devices": {
    "<device_id>": {
      "name": "Three-Phase Meter #1",
      "status": "running",
      "slave_id": 1,
      "registers": { "voltage_a": 220.5, "current_a": 5.2 },
      "active_anomalies": ["voltage_a"],
      "fault": null,
      "stats": {
        "request_count": 150,
        "success_count": 148,
        "error_count": 2,
        "avg_response_time_ms": 12.3
      }
    }
  },
  "events": [
    {
      "timestamp": "2026-03-19T10:00:01Z",
      "device_id": "uuid-here",
      "device_name": "Three-Phase Meter #1",
      "type": "anomaly_injected",
      "detail": "spike on voltage_a"
    }
  ]
}
```

---

## Frontend Architecture

### 1. WebSocket Hook (new)

`frontend/src/hooks/useWebSocket.ts`:

- Connect to `ws://{host}/ws/monitor`
- Auto-reconnect with exponential backoff: 1s → 2s → 4s, cap at 30s
- On `monitor_update` message: call `monitorStore.handleMonitorUpdate()`
- Return connection status (`connected` | `connecting` | `disconnected`) for UI display

### 2. Monitor Store (new)

`frontend/src/stores/monitorStore.ts` (Zustand):

```typescript
interface MonitorState {
  // Live data (replaced each second by WebSocket)
  devices: Record<string, DeviceMonitorData>;
  events: MonitorEvent[];

  // Chart history (accumulated on frontend)
  registerHistory: Record<string, RegisterHistoryPoint[]>;  // key: `${deviceId}:${registerName}`

  // UI state
  selectedDeviceId: string | null;
  selectedRegisters: string[];  // user-selected registers for chart display
  connectionStatus: 'connected' | 'connecting' | 'disconnected';

  // Actions
  handleMonitorUpdate(data: MonitorUpdate): void;
  selectDevice(deviceId: string | null): void;
  toggleRegister(registerName: string): void;
}
```

`registerHistory` rolling buffer: max 300 points per register (5 minutes @ 1Hz). Only accumulate history for `selectedDeviceId`'s registers. Clear history on device switch.

### 3. TypeScript Types (new)

`frontend/src/types/monitor.ts`:

```typescript
interface DeviceMonitorData {
  name: string;
  status: 'running' | 'stopped' | 'error';
  slave_id: number;
  registers: Record<string, number>;
  active_anomalies: string[];
  fault: FaultInfo | null;
  stats: CommunicationStats;
}

interface CommunicationStats {
  request_count: number;
  success_count: number;
  error_count: number;
  avg_response_time_ms: number;
}

interface MonitorEvent {
  timestamp: string;
  device_id: string;
  device_name: string;
  type: 'device_started' | 'device_stopped' | 'anomaly_injected' | 'anomaly_removed' | 'fault_set' | 'fault_cleared';
  detail: string;
}

interface MonitorUpdate {
  type: 'monitor_update';
  timestamp: string;
  devices: Record<string, DeviceMonitorData>;
  events: MonitorEvent[];
}

interface RegisterHistoryPoint {
  timestamp: number;  // Unix ms for chart X-axis
  value: number;
}
```

---

## Monitor Dashboard UI

### Page Layout

Two modes in a single page:

**Overview mode (default):**
```
┌─────────────────────────────────────────────┐
│ [●] Connected    Monitor Dashboard          │
├─────────────────────────────────────────────┤
│ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐           │
│ │Dev 1│ │Dev 2│ │Dev 3│ │Dev 4│  ← CardGrid│
│ │ 🟢  │ │ 🟢  │ │ ⚫  │ │ 🔴  │           │
│ └─────┘ └─────┘ └─────┘ └─────┘           │
├─────────────────────────────────────────────┤
│ Event Log (global, last 100, scrollable)    │
└─────────────────────────────────────────────┘
```

**Device detail mode (on card click):**
```
┌─────────────────────────────────────────────┐
│ [← Back]  Device 1 - SDM630 (Slave 1)      │
├──────────────────────┬──────────────────────┤
│ Register Table       │ Communication Stats  │
│ voltage_a  220.5 V   │ Requests: 1500       │
│ current_a  5.2 A  ⚠️  │ Success:  1498       │
│ power      1146.6 W  │ Errors:   2          │
│                      │ Avg RT:   12.3 ms    │
├──────────────────────┴──────────────────────┤
│ Register Chart (user-selected registers)    │
│ [✓voltage_a] [✓current_a] [☐power]         │
│ ┌───────────────────────────────────────┐   │
│ │ ~~~~~ -----   (last 5 min)            │   │
│ └───────────────────────────────────────┘   │
├─────────────────────────────────────────────┤
│ Event Log (this device only)                │
└─────────────────────────────────────────────┘
```

### Component Breakdown

| Component | Responsibility |
|-----------|---------------|
| `MonitorPage` | Page container, manages overview/detail toggle |
| `DeviceCardGrid` | Card wall, displays all device status cards |
| `DeviceCard` | Single card: name, slave ID, status light, anomaly/fault badges |
| `DeviceDetailPanel` | Detail panel container |
| `RegisterTable` | Live value table, warning indicator for registers under anomaly |
| `RegisterChart` | Recharts line chart + register checkbox selector |
| `StatsPanel` | Communication stats (4 metric cards) |
| `EventLog` | Event list, accepts `deviceId` prop for filtering (null = global) |
| `ConnectionBadge` | WebSocket connection status indicator |

### Chart Library

**Recharts** — lightweight, React-native, listed as option in CLAUDE.md:
- `LineChart` with multiple `Line` components (one per selected register)
- X-axis: time (last 5 minutes)
- Y-axis: auto-scale
- Tooltip showing precise values

### Card Status Visuals

| Status | Color | Description |
|--------|-------|-------------|
| running | Green border + badge | Normal operation |
| stopped | Gray border + badge | Stopped |
| error | Red border + badge | Error state |
| running + anomaly | Green border + orange badge | Running with anomaly injection active |
| running + fault | Green border + red badge | Running with communication fault active |

---

## Testing Strategy

### Backend Tests
- **MonitorService unit tests**: event logging, get_events filtering, get_snapshot aggregation
- **WebSocket integration test**: connect, receive monitor_update, verify message shape
- **DeviceStats unit test**: counter increment, avg calculation, reset on stop

### Frontend Tests
- **monitorStore**: handleMonitorUpdate correctly updates state, history rolling buffer logic, device selection
- **Component rendering**: DeviceCard shows correct status colors, RegisterTable displays values

---

## Files to Create/Modify

### New Files
- `backend/app/services/monitor_service.py`
- `backend/app/api/websocket.py`
- `frontend/src/hooks/useWebSocket.ts`
- `frontend/src/stores/monitorStore.ts`
- `frontend/src/types/monitor.ts`
- `frontend/src/pages/Monitor/DeviceCardGrid.tsx`
- `frontend/src/pages/Monitor/DeviceCard.tsx`
- `frontend/src/pages/Monitor/DeviceDetailPanel.tsx`
- `frontend/src/pages/Monitor/RegisterTable.tsx`
- `frontend/src/pages/Monitor/RegisterChart.tsx`
- `frontend/src/pages/Monitor/StatsPanel.tsx`
- `frontend/src/pages/Monitor/EventLog.tsx`
- `frontend/src/pages/Monitor/ConnectionBadge.tsx`

### Modified Files
- `backend/app/protocols/modbus_tcp.py` — add DeviceStats tracking
- `backend/app/main.py` — register WebSocket route, start broadcast task in lifespan
- `backend/app/services/device_service.py` — add monitor_service.log_event() calls
- `backend/app/api/routes/anomaly.py` — add monitor_service.log_event() calls
- `backend/app/api/routes/simulation.py` — add monitor_service.log_event() calls (fault endpoints)
- `frontend/src/pages/Monitor/index.tsx` — replace empty skeleton with full dashboard
- `frontend/package.json` — add recharts dependency
