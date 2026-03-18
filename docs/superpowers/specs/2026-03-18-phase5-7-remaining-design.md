# GhostMeter Phase 5.2–7 Design Spec

> Covers all remaining work from Phase 5.2 through Phase 7 (simplified).
> Phase 8 (Post-MVP) items are listed but not designed here.

---

## Phase 5.2: Anomaly Injection Engine

### Overview

Adds an anomaly injection layer between DataGenerator and ProtocolAdapter. Normal values are generated first, then AnomalyInjector decides whether to modify them. Supports both real-time API control (in-memory, immediate effect) and relative-time schedules (DB-persisted, auto-triggered after device start).

### Data Flow

```
DataGenerator.generate() → AnomalyInjector.apply() → ProtocolAdapter.update_register()
```

SimulationEngine's `_run_device()` loop calls AnomalyInjector after generating each register value. The injector checks:
1. Is there an active real-time anomaly for this register? → apply it
2. Is there a scheduled anomaly whose time window includes current elapsed time? → activate and apply it

Real-time anomalies take precedence over scheduled ones for the same register.

### Anomaly Types

| Type | Behavior | Parameters | Example |
|------|----------|------------|---------|
| `spike` | Multiply current value by multiplier (probabilistic) | `multiplier: float`, `probability: float (0-1)` | `{multiplier: 3.0, probability: 0.1}` — 10% chance of 3x spike |
| `drift` | Accumulate offset over time | `drift_per_second: float`, `max_drift: float` | `{drift_per_second: 0.5, max_drift: 50.0}` — drift up to +50 |
| `flatline` | Freeze at a fixed value | `value: float` (optional) | `{value: 230.0}` or `{}` (freeze at current) |
| `out_of_range` | Force to an extreme value | `value: float` | `{value: 999.0}` |
| `data_loss` | Set to zero | (none) | `{}` |

### Schedule Mechanism (Relative Time)

Schedules are defined relative to device start time. When a device starts, SimulationEngine records `start_time`. Each tick, elapsed seconds are calculated and compared against schedule windows.

**DB Model: `anomaly_schedules`**

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | PK |
| `device_id` | UUID | FK → device_instances (CASCADE) |
| `register_name` | VARCHAR(100) | Target register |
| `anomaly_type` | VARCHAR(20) | One of: spike, drift, flatline, out_of_range, data_loss |
| `anomaly_params` | JSONB | Type-specific parameters |
| `trigger_after_seconds` | INTEGER | Seconds after device start to activate |
| `duration_seconds` | INTEGER | How long the anomaly stays active |
| `is_enabled` | BOOLEAN | Default true |
| `created_at` | TIMESTAMP(tz) | |
| `updated_at` | TIMESTAMP(tz) | |

**Unique constraint:** `(device_id, register_name, trigger_after_seconds)` — prevents duplicate trigger times.

**Overlap handling:** Application-level validation in `anomaly_service.py` rejects schedules with overlapping time windows for the same register. When saving via `PUT /anomaly/schedules`, check that no two entries for the same `register_name` have overlapping `[trigger_after_seconds, trigger_after_seconds + duration_seconds)` ranges. Return 422 if overlap detected.

### In-Memory State

`AnomalyInjector` maintains:
- `_active_anomalies: dict[UUID, dict[str, AnomalyState]]` — device_id → register_name → active anomaly
- `AnomalyState` tracks: anomaly_type, params, activated_at (for drift calculation), frozen_value (for flatline)

### API Endpoints

All under `/api/v1/devices/{device_id}/anomaly`. Anomaly routes are defined in a separate `APIRouter` in `anomaly.py`, mounted on the existing devices router prefix (same pattern as simulation routes).

### Parameter Validation

Pydantic validators enforce required params per anomaly type:
- `spike`: requires `multiplier` (float, > 0) and `probability` (float, 0-1)
- `drift`: requires `drift_per_second` (float) and `max_drift` (float, > 0)
- `flatline`: `value` is optional (float); if omitted, freezes at current value
- `out_of_range`: requires `value` (float)
- `data_loss`: no params required

#### Real-time Control

| Method | Path | Behavior |
|--------|------|----------|
| `POST` | `/anomaly` | Inject anomaly on a register (immediate, in-memory) |
| `GET` | `/anomaly` | List all active anomalies for device |
| `DELETE` | `/anomaly/{register_name}` | Remove anomaly from specific register |
| `DELETE` | `/anomaly` | Remove all anomalies |

**POST body:**
```json
{
  "register_name": "voltage_l1",
  "anomaly_type": "spike",
  "anomaly_params": {"multiplier": 3.0, "probability": 0.1}
}
```

#### Schedule Management

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/anomaly/schedules` | List all schedules |
| `PUT` | `/anomaly/schedules` | Batch set schedules (replace all) |
| `DELETE` | `/anomaly/schedules` | Clear all schedules |

**PUT body:**
```json
{
  "schedules": [
    {
      "register_name": "voltage_l1",
      "anomaly_type": "spike",
      "anomaly_params": {"multiplier": 3.0, "probability": 0.1},
      "trigger_after_seconds": 300,
      "duration_seconds": 60,
      "is_enabled": true
    }
  ]
}
```

### Files

| File | Purpose |
|------|---------|
| `backend/app/simulation/anomaly_injector.py` | AnomalyInjector class: apply logic + schedule checking |
| `backend/app/models/anomaly.py` | AnomalySchedule ORM model |
| `backend/app/schemas/anomaly.py` | Pydantic request/response schemas |
| `backend/app/services/anomaly_service.py` | CRUD + register validation |
| `backend/app/api/routes/anomaly.py` | API route handlers |
| `backend/tests/test_anomaly_api.py` | API integration tests |
| `backend/tests/test_anomaly_injector.py` | Unit tests for injection logic |

### Singleton Pattern

Add to `simulation/__init__.py`, consistent with existing `simulation_engine` and `fault_simulator`:

```python
from app.simulation.anomaly_injector import AnomalyInjector
anomaly_injector = AnomalyInjector()
```

### Integration with SimulationEngine

Modify `engine.py` `_run_device()`. The actual DataGenerator call uses `generate(mode, params, context)`:

```python
# After generating value (existing code)
generated = self._data_generator.generate(
    config.data_mode, config.mode_params, context,
)

# Apply anomaly (new step)
generated = anomaly_injector.apply(
    device_id=device_id,
    register_name=config.register_name,
    value=generated,
    elapsed_seconds=context.elapsed_seconds,
)

# Scale and write to adapter (existing code)
if reg.scale_factor != 0:
    raw_value = generated / reg.scale_factor
else:
    raw_value = generated
current_values[config.register_name] = generated

await adapter.update_register(
    device_id, reg.address, reg.function_code,
    raw_value, reg.data_type, reg.byte_order,
)
```

### Current Values Exposure

Promote `current_values` from local variable to instance state for Phase 6 WebSocket access:

```python
# In SimulationEngine.__init__
self._device_values: dict[UUID, dict[str, float]] = {}

# In _run_device(), replace local current_values with:
self._device_values[device_id] = {}
# ... use self._device_values[device_id] throughout the loop

# In stop_device(), cleanup:
self._device_values.pop(device_id, None)

# Public accessor for Phase 6:
def get_current_values(self, device_id: UUID) -> dict[str, float]:
    return dict(self._device_values.get(device_id, {}))
```

---

## Phase 5.3: Fault Integration + Integration Tests

### Problem

FaultSimulator stores fault state and the API works, but faults are not intercepted in the Modbus TCP adapter. A Modbus client reading registers will never experience any fault behavior.

### Design: Custom Request Handler

Modify `ModbusTcpAdapter` to intercept incoming Modbus requests before processing:

```python
async def _handle_request(self, request):
    device_id = self._slave_to_device.get(request.unit_id)
    if device_id is None:
        return await self._default_handler(request)

    fault = fault_simulator.get_fault(device_id)
    if fault is None:
        return await self._default_handler(request)

    match fault.fault_type:
        case "delay":
            await asyncio.sleep(fault.params["delay_ms"] / 1000)
            return await self._default_handler(request)
        case "timeout":
            return None  # no response, client times out
        case "exception":
            return ExceptionResponse(
                request.function_code,
                fault.params.get("exception_code", 0x04)
            )
        case "intermittent":
            if random.random() < fault.params.get("failure_rate", 0.5):
                return None
            return await self._default_handler(request)
```

The `_slave_to_device` reverse mapping already exists from Phase 5 Round 1.

### pymodbus Integration (v3.12.1)

pymodbus 3.x `ModbusTcpServer` accepts a `request_tracer` callback parameter — a callable invoked on each request/response pair. However, `request_tracer` is read-only (for logging) and cannot modify responses.

**Recommended approach:** Use pymodbus's `ModbusRequest` handler override. Subclass `ModbusConnectedRequestHandler` and override the `execute()` method to intercept before datastore access. Pass the custom handler class via `ModbusTcpServer(handler=FaultAwareHandler, ...)`.

In pymodbus 3.x, the request object uses `unit_id` attribute (also aliased as `slave_id` in some versions). Use `request.slave_id` for forward compatibility.

If `request_tracer` + handler subclassing proves insufficient, an alternative is to wrap the `ModbusServerContext` with a proxy that intercepts `getValues()` / `setValues()` calls per slave ID.

### Integration Tests

New file: `backend/tests/test_modbus_integration.py`

Uses pymodbus `AsyncModbusTcpClient` to connect to the running server.

| Test Case | Setup | Assertion |
|-----------|-------|-----------|
| Normal read | Start device with static simulation | Client reads correct value |
| Delay fault | Set delay fault (500ms) | Response time >= 500ms |
| Timeout fault | Set timeout fault | Client raises timeout/connection error |
| Exception fault | Set exception fault (code 0x02) | Client receives Modbus exception with code 0x02 |
| Intermittent fault | Set intermittent (rate=0.5), read 100 times | Failure rate between 30%–70% |
| Anomaly + fault | Set spike anomaly + delay fault | Value is spiked AND response is delayed |
| Clear fault | Set fault → clear → read | Normal response |

### Files

| File | Change |
|------|--------|
| `backend/app/protocols/modbus_tcp.py` | Add request handler with fault interception |
| `backend/tests/test_modbus_integration.py` | New: integration tests with real Modbus client |

---

## Phase 5.4: Simulation Frontend

### Page Structure

Replace the placeholder Simulation page with a 3-tab functional UI.

```
SimulationPage
├── Device Selector (Ant Design Select, top of page)
├── Tabs
│   ├── Tab 1: "Data Mode"    → DataModeTab
│   ├── Tab 2: "Anomaly"      → AnomalyTab
│   └── Tab 3: "Fault"        → FaultTab
```

### Tab 1: DataModeTab

- **Table** with one row per register from the selected device's template
- **Columns:** Register Name | Data Mode (Select dropdown) | Parameters (dynamic form) | Enabled (Switch) | Interval (InputNumber, ms)
- **Dynamic params form** changes based on selected data_mode:
  - `static` → value input
  - `random` → base + amplitude + distribution select
  - `daily_curve` → base + amplitude + peak_hour
  - `computed` → expression textarea
  - `accumulator` → start_value + increment_per_second
- **"Save All" button** at bottom → calls `PUT /devices/{id}/simulation`
- Load existing configs on device selection → pre-fill form

### Tab 2: AnomalyTab

Two sections:

**Real-time Injection:**
- Form: register select → anomaly type select → dynamic params → "Inject" button
- Active anomalies table with "Remove" action per row and "Clear All" button

**Schedule Management:**
- Editable table: register | type | params | trigger_after (s) | duration (s) | enabled
- "Add Row" button, "Save All" button (PUT), "Clear All" button (DELETE)

### Tab 3: FaultTab

- Device-level (not per-register)
- Fault type select → dynamic params form → "Set Fault" button
- Current fault display with "Clear" button
- Show "No active fault" when none is set

### Frontend Files

| File | Purpose |
|------|---------|
| `frontend/src/pages/Simulation/index.tsx` | Main page: device selector + tabs |
| `frontend/src/pages/Simulation/DataModeTab.tsx` | Data mode configuration table |
| `frontend/src/pages/Simulation/AnomalyTab.tsx` | Anomaly injection + schedule UI |
| `frontend/src/pages/Simulation/FaultTab.tsx` | Fault control |
| `frontend/src/services/simulationApi.ts` | Simulation config API calls |
| `frontend/src/services/anomalyApi.ts` | Anomaly + schedule API calls |
| `frontend/src/services/faultApi.ts` | Fault API calls |
| `frontend/src/types/simulation.ts` | TypeScript interfaces |
| `frontend/src/stores/simulationStore.ts` | Zustand store for simulation state |

### TypeScript Types

```typescript
// Simulation Config
interface SimulationConfigRequest {
  register_name: string;
  data_mode: "static" | "random" | "daily_curve" | "computed" | "accumulator";
  mode_params: Record<string, unknown>;
  is_enabled: boolean;
  update_interval_ms: number;
}

interface SimulationConfigResponse extends SimulationConfigRequest {
  id: string;
  device_id: string;
  created_at: string;
  updated_at: string;
}

// Anomaly
interface AnomalyInjectRequest {
  register_name: string;
  anomaly_type: "spike" | "drift" | "flatline" | "out_of_range" | "data_loss";
  anomaly_params: Record<string, unknown>;
}

interface AnomalyScheduleRequest {
  register_name: string;
  anomaly_type: string;
  anomaly_params: Record<string, unknown>;
  trigger_after_seconds: number;
  duration_seconds: number;
  is_enabled: boolean;
}

// Fault
interface FaultConfigRequest {
  fault_type: "delay" | "timeout" | "exception" | "intermittent";
  params: Record<string, unknown>;
}
```

---

## Phase 6: Real-time Monitor Dashboard

### 6.1 WebSocket Backend

**Endpoint:** `GET ws://localhost:8000/ws/monitor`

> WebSocket endpoints use `/ws/` prefix (separate from `/api/v1/`). This is standard practice — WS connections are long-lived and don't follow REST versioning semantics.

**Connection lifecycle:**
1. Client connects → server adds to broadcast list
2. Server pushes every 1 second
3. Client disconnects → server removes from list
4. Graceful shutdown → close all connections

**Message format:**

```json
{
  "type": "monitor_update",
  "timestamp": "2026-03-18T12:00:00Z",
  "devices": [
    {
      "device_id": "uuid",
      "name": "Meter-01",
      "slave_id": 1,
      "port": 502,
      "status": "running",
      "registers": [
        {"name": "voltage_l1", "value": 231.5, "unit": "V"},
        {"name": "current_l1", "value": 15.2, "unit": "A"}
      ],
      "active_anomalies": ["voltage_l1:spike"],
      "active_fault": {"fault_type": "delay", "params": {"delay_ms": 500}},
      "stats": {
        "request_count": 1500,
        "success_count": 1480,
        "error_count": 20,
        "avg_response_ms": 12.3
      }
    }
  ]
}
```

**Data sources:**
- `registers` → from SimulationEngine's last generated values (add a `get_current_values(device_id)` method)
- `active_anomalies` → from AnomalyInjector's `_active_anomalies`
- `active_fault` → from FaultSimulator's `get_fault()`
- `stats` → from Modbus adapter's request counter (new)

### Communication Statistics

Add to `ModbusTcpAdapter`:
- `_device_stats: dict[UUID, DeviceStats]` — per-device counters
- `DeviceStats`: request_count, success_count, error_count, total_response_ms
- Increment in request handler (before/after fault processing)
- `get_stats(device_id) -> DeviceStats` public method
- Clear on device stop

### Event Log (In-Memory)

`MonitorService` maintains a circular buffer (collections.deque, maxlen=100):

```python
@dataclass
class EventLogEntry:
    timestamp: str          # ISO 8601 UTC
    device_id: str
    device_name: str
    event_type: str         # "device_start", "device_stop", "anomaly_inject", "fault_set", etc.
    detail: str             # human-readable description
```

Events are emitted by calling `monitor_service.log_event()` from device_service, anomaly_service, fault routes. Pushed to WebSocket clients included in `monitor_update` messages.

**MonitorService instantiation:** Module-level singleton in `services/monitor_service.py`, consistent with simulation engine pattern:

```python
# services/monitor_service.py
monitor_service = MonitorService()

# Other services import it:
from app.services.monitor_service import monitor_service
```

### Backend Files

| File | Purpose |
|------|---------|
| `backend/app/api/websocket.py` | WebSocket handler + broadcast loop |
| `backend/app/services/monitor_service.py` | Data aggregation + event log buffer |

### 6.2 Frontend Dashboard

**Page Layout:**

```
MonitorPage
├── DeviceCardGrid (top)
│   └── DeviceCard × N
│       ├── Status indicator (green/gray/red dot)
│       ├── Device name + slave_id
│       ├── Key metrics (1-2 register values)
│       └── Anomaly/fault badges
├── DeviceDetailPanel (bottom, shown on card click)
│   ├── Register table (live updating)
│   ├── RegisterChart (Recharts LineChart, 5-min rolling window)
│   ├── Stats summary (requests, success rate, avg latency)
│   └── Anomaly/fault status badges
└── EventLog (collapsible sidebar or bottom panel)
    └── Scrollable list of recent 100 events
```

**Chart data:**
- `monitorStore` maintains a rolling buffer per register: `{timestamp, value}[]` (max 300 points = 5 min at 1/s)
- On each WebSocket message, push new values and trim old ones
- Recharts `<LineChart>` renders from this buffer

**WebSocket connection management:**
- `useWebSocket` hook: connect on mount, reconnect on disconnect (exponential backoff), cleanup on unmount
- Parse messages → update `monitorStore`

### Frontend Files

| File | Purpose |
|------|---------|
| `frontend/src/pages/Monitor/index.tsx` | Dashboard layout |
| `frontend/src/pages/Monitor/DeviceCardGrid.tsx` | Card grid |
| `frontend/src/pages/Monitor/DeviceDetailPanel.tsx` | Detail panel with table + chart |
| `frontend/src/pages/Monitor/RegisterChart.tsx` | Recharts line chart |
| `frontend/src/pages/Monitor/EventLog.tsx` | Event log list |
| `frontend/src/stores/monitorStore.ts` | WebSocket data + rolling buffers |
| `frontend/src/hooks/useWebSocket.ts` | WebSocket connection hook |

---

## Phase 7: System Finalization (Simplified)

### Docker Compose Production Config

Update `docker-compose.yml`:
- Add health checks for all services (backend: `/health`, postgres: `pg_isready`, frontend: curl)
- Add `restart: unless-stopped` to all services
- Add named volumes for postgres data persistence
- Consolidate environment variables with `env_file: .env`

### .env.example

```env
# Database
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=ghostmeter
POSTGRES_USER=ghostmeter
POSTGRES_PASSWORD=changeme

# Backend
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
MODBUS_PORT=502
LOG_LEVEL=INFO

# Frontend
VITE_API_BASE_URL=http://localhost:8000
```

### README Quick Start

```markdown
## Quick Start
1. Clone the repo
2. Copy `.env.example` to `.env` and adjust if needed
3. `docker compose up -d`
4. Open http://localhost:3000

## For Data Collector Integration
- Modbus TCP: connect to `localhost:502`
- REST API: `http://localhost:8000/api/v1/`
- See `docs/api-curl-samples.md` for examples
```

### Linting Configuration

Add `[tool.ruff]` section to `backend/pyproject.toml` (create if not exists):

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I"]  # pycodestyle + pyflakes + isort
```

### GitHub Actions CI

`.github/workflows/ci.yml`:
- Trigger: push to `dev` / `main`, PR to `main`
- Backend job: Python 3.12, install deps, ruff lint, pytest (with postgres service container)
- Frontend job: Node 20, npm ci, tsc --noEmit, npm run build

### Files

| File | Change |
|------|--------|
| `docker-compose.yml` | Add health checks, restart policy, volumes |
| `.env.example` | New: all configurable variables |
| `README.md` | Update: quick start + data collector section |
| `.github/workflows/ci.yml` | New: CI pipeline |
| `backend/pyproject.toml` | New or update: ruff configuration |

---

## Phase 8: Post-MVP (Record Only)

The following items are deferred and will be planned separately when needed:

- Full config import/export (all templates + devices + simulation → single JSON)
- Operation log system (DB-persisted audit trail)
- MkDocs documentation site
- Docker Hub image publishing
- CONTRIBUTING.md
- Community outreach (GitHub Topics, Reddit, etc.)
- Fault config DB persistence
- Per-register update intervals
- Anomaly schedule with absolute time / cron expressions

---

## Cross-Cutting Concerns

### Error Handling

All new API endpoints follow existing patterns:
- Custom exception classes in `app/exceptions.py`
- Standard `ApiResponse[T]` envelope
- Validation via Pydantic validators
- 404 for missing devices, 422 for invalid params, 409 for state conflicts

### Testing Strategy

| Phase | Test Type | Coverage |
|-------|-----------|----------|
| 5.2 | Unit + API integration | Anomaly logic, schedule activation, CRUD |
| 5.3 | Integration (Modbus client) | All fault types with real TCP connection |
| 5.4 | Manual | Frontend interaction (no E2E tests in MVP) |
| 6 | Unit + manual | WebSocket broadcast, data aggregation |
| 7 | CI | Automated lint + test on push |

### Migration Plan

- Phase 5.2: New Alembic migration for `anomaly_schedules` table
- Phase 5.3–7: No new migrations needed
