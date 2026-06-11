# Scenario Mode Design

**Date**: 2026-03-27
**Status**: Approved

## Goal

Add a scenario system that allows users to define, save, and execute coordinated multi-register anomaly sequences with a visual timeline editor. Scenarios are reusable, template-bound, and include built-in presets for common energy device situations.

## Scope

- New DB tables: `scenarios`, `scenario_steps`
- New backend module: scenario service, API routes, ScenarioRunner (in-memory executor)
- New frontend page: Scenarios (list + timeline editor)
- Device Detail: Scenario execution card
- Built-in seed scenarios for existing templates
- JSON export/import for scenarios
- MVP targets single-device scenarios; data model supports future cross-device extension

## Data Model

### `scenarios` table

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| id | UUID | PK | |
| template_id | UUID | FK → device_templates.id | Bound template |
| name | VARCHAR(255) | NOT NULL | Scenario name |
| description | TEXT | nullable | |
| is_builtin | BOOL | default false | Built-in cannot be deleted |
| total_duration_seconds | INT | NOT NULL | Total scenario length (computed from steps, stored for query convenience) |
| created_at | TIMESTAMP | auto | |
| updated_at | TIMESTAMP | auto | |

**Unique constraint:** `(template_id, name)` — no duplicate names per template.

### `scenario_steps` table

| Column | Type | Constraint | Description |
|--------|------|------------|-------------|
| id | UUID | PK | |
| scenario_id | UUID | FK → scenarios.id ON DELETE CASCADE | Parent scenario |
| register_name | VARCHAR(100) | NOT NULL | Target register (must exist in template) |
| anomaly_type | VARCHAR(50) | NOT NULL | spike / drift / flatline / out_of_range / data_loss |
| anomaly_params | JSONB | NOT NULL, default {} | Type-specific parameters |
| trigger_at_seconds | INT | NOT NULL, ≥ 0 | Seconds after scenario start |
| duration_seconds | INT | NOT NULL, > 0 | How long the anomaly lasts |
| sort_order | INT | NOT NULL, default 0 | Display ordering |

**Validation:** Steps on the same register within the same scenario must not have overlapping time ranges. Overlap check: `[trigger_at, trigger_at + duration)` intervals must not intersect for the same `register_name`.

**Register validation:** `register_name` must exist in the bound template's register definitions.

## Backend API

### Scenario CRUD — `/api/v1/scenarios`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/scenarios` | List all scenarios. Optional `?template_id=` filter |
| GET | `/scenarios/{id}` | Get scenario with all steps |
| POST | `/scenarios` | Create scenario with steps |
| PUT | `/scenarios/{id}` | Update scenario (full replace of steps) |
| DELETE | `/scenarios/{id}` | Delete (403 if is_builtin) |
| POST | `/scenarios/{id}/export` | Export as JSON file |
| POST | `/scenarios/import` | Import from JSON file |

**Create/Update request body:**
```json
{
  "template_id": "uuid",
  "name": "Power Outage",
  "description": "Simulates complete power loss",
  "steps": [
    {
      "register_name": "voltage_l1",
      "anomaly_type": "out_of_range",
      "anomaly_params": {"value": 0},
      "trigger_at_seconds": 0,
      "duration_seconds": 30
    }
  ]
}
```

**Response shape:** Standard `ApiResponse` wrapper with `ScenarioDetail` (includes steps).

**`total_duration_seconds`** is computed server-side as `max(trigger_at_seconds + duration_seconds)` across all steps.

### Scenario Execution — `/api/v1/devices/{device_id}/scenario`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/{device_id}/scenario/{scenario_id}/start` | Start executing scenario on device |
| POST | `/{device_id}/scenario/stop` | Stop running scenario, clear all injected anomalies |
| GET | `/{device_id}/scenario/status` | Get execution status |

**Start preconditions:**
- Device must be in `running` state
- No other scenario already running on this device
- Scenario's `template_id` must match the device's template

**Status response:**
```json
{
  "scenario_id": "uuid",
  "scenario_name": "Power Outage",
  "status": "running",
  "elapsed_seconds": 12,
  "total_duration_seconds": 30,
  "active_steps": [
    {
      "register_name": "voltage_l1",
      "anomaly_type": "out_of_range",
      "remaining_seconds": 18
    }
  ]
}
```

Status values: `"running"` | `"completed"` | `null` (no scenario running — return 404 for GET).

## ScenarioRunner (In-Memory Executor)

```python
class ScenarioRunner:
    _running: dict[UUID, RunningScenario]  # device_id → state

    async def start(self, device_id, scenario, steps) -> None
    async def stop(self, device_id) -> None
    def get_status(self, device_id) -> ScenarioStatus | None
```

**RunningScenario state:**
- `scenario_id`, `scenario_name`
- `started_at`: `asyncio.get_event_loop().time()` (monotonic)
- `total_duration_seconds`: int
- `status`: `"running"` | `"completed"`
- `active_anomalies`: `set[str]` — register names currently injected
- `task`: asyncio.Task — the timeline driver

**Timeline driver logic (asyncio task):**
1. Sort steps by `trigger_at_seconds`
2. Loop: every 1 second tick:
   - `elapsed = loop.time() - started_at`
   - For each step not yet triggered where `elapsed >= trigger_at_seconds`: call `AnomalyInjector.inject(device_id, register_name, anomaly_type, params)`, add to `active_anomalies`
   - For each active anomaly where `elapsed >= trigger_at_seconds + duration_seconds`: call `AnomalyInjector.remove(device_id, register_name)`, remove from `active_anomalies`
   - If `elapsed >= total_duration_seconds` and no active anomalies: set status to `"completed"`, break
3. On cancel (stop): remove all `active_anomalies` via `AnomalyInjector.remove`, set status to `"completed"`

**Constraint:** One scenario per device at a time. Starting a new scenario while one is running returns 409 Conflict.

**Device stop integration:** When `device_service.stop_device()` is called, also call `ScenarioRunner.stop(device_id)` if a scenario is running (best-effort, like MQTT).

## Built-in Seed Scenarios

### Three-Phase Meter — Power Outage
```
voltage_l1:  out_of_range(0)  T+0s  → 30s
voltage_l2:  out_of_range(0)  T+0s  → 30s
voltage_l3:  out_of_range(0)  T+0s  → 30s
current_l1:  out_of_range(0)  T+2s  → 28s
current_l2:  out_of_range(0)  T+2s  → 28s
current_l3:  out_of_range(0)  T+2s  → 28s
total_power: out_of_range(0)  T+3s  → 27s
```
Total: 30 seconds

### Three-Phase Meter — Voltage Instability
```
voltage_l1:  spike(probability=0.8, multiplier=1.5)  T+0s  → 15s
voltage_l2:  drift(drift_per_second=2, max_drift=30)  T+5s  → 20s
voltage_l3:  spike(probability=0.6, multiplier=2.0)  T+10s → 10s
```
Total: 25 seconds

### Solar Inverter — Fault Disconnect
```
ac_power:    flatline(value=0)                       T+0s  → 30s
dc_voltage:  drift(drift_per_second=-5, max_drift=-50) T+2s → 28s
efficiency:  out_of_range(value=0)                   T+5s  → 25s
```
Total: 30 seconds

## Frontend

### New Sidebar Item: "Scenarios"

Add to the existing sidebar navigation, after "Simulation".

### Scenario List Page (`/scenarios`)

- Table columns: Name | Template | Duration | Built-in tag | Actions
- Actions: Edit (navigate to editor) | Delete (with confirm, disabled for built-in) | Export
- Header: "New Scenario" button + "Import" button
- Optional template filter dropdown

### Scenario Editor Page (`/scenarios/{id}` or `/scenarios/new`)

**Top section:** Name input, Description textarea, Template select (locked after creation)

**Timeline Editor (core component):**

Visual representation — horizontal axis is time (seconds), vertical axis is registers:

```
Register        0s    5s    10s   15s   20s   25s   30s
─────────────────────────────────────────────────────────
voltage_l1      [████ spike ████]
voltage_l2             [████████ drift ████████]
voltage_l3                   [████ spike ████]
current_l1      [████████████ flatline ████████████]
```

**Interactions:**
- **Add step:** Click empty area on a register row → popover with anomaly type selector, params form, duration input. Clicking save creates the block.
- **Edit step:** Click existing block → same popover, pre-filled. Can modify type, params, duration.
- **Delete step:** X button on block hover, or delete button in popover.
- **Drag to move:** Drag block body horizontally to change `trigger_at_seconds`.
- **Drag to resize:** Drag block left/right edge to change `trigger_at_seconds` or `duration_seconds`.
- **Zoom:** Zoom in/out buttons or scroll to adjust time scale (pixels per second).
- **Overlap prevention:** Snap/block behavior — cannot drop a block where it overlaps another on the same register.

**Implementation:** Pure React + CSS with absolute positioning. No external timeline library.
- Each register row is a relative-positioned div
- Each step block is an absolute-positioned div: `left = trigger_at * pxPerSecond`, `width = duration * pxPerSecond`
- Color coding by anomaly type: spike=orange, drift=blue, flatline=gray, out_of_range=red, data_loss=purple
- Mouse events (mousedown/mousemove/mouseup) for drag and resize
- Popover uses Ant Design Popover component

**Bottom:** Save button, Cancel button

### Scenario Execution Card (Device Detail Page)

Below the MQTT Publishing card, add a **Scenario Card**:

**Idle state:**
- Dropdown: select a scenario (filtered by device's template)
- "Run Scenario" button (disabled if device not running)

**Running state:**
- Scenario name + status badge (green pulsing "Running")
- Progress bar: `elapsed / total_duration` with percentage
- List of currently active steps (register name + anomaly type + remaining seconds)
- "Stop Scenario" button (danger)
- Auto-refreshes via polling `GET /devices/{id}/scenario/status` every 1 second

**Completed state:**
- "Completed" badge
- "Run Again" button to re-execute the same scenario

## Export/Import Format

```json
{
  "name": "Power Outage",
  "description": "Simulates complete power loss",
  "template_name": "Three-Phase Power Meter (SDM630)",
  "steps": [
    {
      "register_name": "voltage_l1",
      "anomaly_type": "out_of_range",
      "anomaly_params": {"value": 0},
      "trigger_at_seconds": 0,
      "duration_seconds": 30
    }
  ]
}
```

Import resolves `template_name` to `template_id`. Fails if template not found.

## Files to Create/Modify

### Backend — New
- `backend/app/models/scenario.py` — Scenario + ScenarioStep ORM models
- `backend/app/schemas/scenario.py` — Pydantic request/response schemas
- `backend/app/services/scenario_service.py` — CRUD + validation
- `backend/app/services/scenario_runner.py` — In-memory executor
- `backend/app/api/routes/scenarios.py` — CRUD + execution API routes
- `backend/app/seed/scenarios/` — Built-in scenario JSON files
- `backend/alembic/versions/xxx_add_scenarios.py` — Migration
- `backend/tests/test_scenarios.py` — CRUD + execution tests

### Backend — Modify
- `backend/app/main.py` — Register scenario routes, seed scenarios, init ScenarioRunner
- `backend/app/services/device_service.py` — Stop scenario on device stop
- `backend/app/services/system_service.py` — Include scenarios in system export/import

### Frontend — New
- `frontend/src/pages/Scenarios/ScenarioList.tsx` — List page
- `frontend/src/pages/Scenarios/ScenarioEditor.tsx` — Editor page
- `frontend/src/pages/Scenarios/TimelineEditor.tsx` — Timeline visualization component
- `frontend/src/pages/Scenarios/StepPopover.tsx` — Step edit popover
- `frontend/src/pages/Devices/ScenarioCard.tsx` — Execution card in device detail
- `frontend/src/services/scenarioApi.ts` — API client
- `frontend/src/stores/scenarioStore.ts` — Zustand store
- `frontend/src/types/scenario.ts` — TypeScript interfaces

### Frontend — Modify
- `frontend/src/App.tsx` or router config — Add /scenarios route
- `frontend/src/components/Layout.tsx` or sidebar — Add Scenarios nav item
- `frontend/src/pages/Devices/DeviceDetail.tsx` — Add ScenarioCard

## Out of Scope

- Cross-device scenarios (data model supports via future `scenario_devices` join table, not implemented now)
- Scenario chaining (run scenario A then B sequentially)
- WebSocket push for scenario status (polling is sufficient for MVP)
- Undo/redo in timeline editor
- Step copy/paste in timeline editor
