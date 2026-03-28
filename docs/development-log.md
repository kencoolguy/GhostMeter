# Development Log

## 2026-03-29 — Auto-resume & Monitor UX Improvements

### What was done
- **Auto-resume on startup**: Backend lifespan now queries `device_instances` for `status=running`, registers each device in the protocol adapter (Modbus/SNMP), and restarts simulation engine. Previously, a backend restart left all devices in a "running" DB state but with no actual simulation running.
- **Monitor card defaults**: DeviceCard preview changed from voltage_l1/l2 to total_power + total_energy (with fallback for templates without those registers)
- **Monitor chart multi-select**: Chart section now supports multiple selected registers, defaults to total_power + total_energy
- **Batch name prefix fix**: Removed extra space between prefix and slave ID — users control separators in the prefix itself
- **.gitignore**: Added `.mcp.json`
- **README.md**: Added Docker operations quick reference

### Decisions
- Auto-resume runs after protocol adapters are started but before WebSocket broadcast — ensures values start flowing immediately on first client connect
- Monitor register preference uses a hardcoded `["total_power", "total_energy"]` list with fallback to first registers — simple and sufficient for current templates

### Root cause of the "no values" bug
After `docker compose down -v`, DB was wiped. User rebuilt devices and started them via UI (status=running in DB), but when backend later restarted, the lifespan only started protocol adapters — it never re-registered devices or restarted simulation tasks. The simulation engine's in-memory state was empty.

---

## 2026-03-27 — Scenario Mode (Milestone 8.5)

### What was done
- **DB models + migration**: `scenarios` and `scenario_steps` tables with UUID PKs, JSONB anomaly_params, cascade delete from templates
- **Pydantic schemas**: ScenarioCreate, ScenarioUpdate, ScenarioDetail, ScenarioSummary, ScenarioStepCreate, ScenarioExport, ScenarioExecutionStatus, ActiveStepStatus
- **Scenario CRUD service**: Full REST API at `/api/v1/scenarios` — list (with template filter), get, create, update (full replace), delete, export, import
- **ScenarioRunner**: Async executor that schedules anomaly injections on a timeline using asyncio tasks; tracks elapsed time, active steps, and auto-cleans up on completion
- **Execution API**: `POST /devices/{id}/scenario/{id}/start`, `POST /devices/{id}/scenario/stop`, `GET /devices/{id}/scenario/status` — validates device running state, template match, and single-scenario-per-device constraint
- **Built-in seed scenarios**: 3 scenarios for Three-Phase Meter template — Power Outage Recovery (60s), Voltage Instability (90s), Inverter Fault Sequence (120s)
- **Frontend types, API client, store**: `scenario.ts` types, `scenarioApi.ts`, `scenarioStore.ts` following existing patterns
- **ScenarioList page**: Table with template filter dropdown, create/edit/delete actions, clone, export (JSON download), import (JSON upload)
- **TimelineEditor**: Visual drag-and-drop blocks on a register x time grid; StepPopover for editing anomaly params; auto-computes total_duration_seconds
- **ScenarioExecutionCard**: Device Detail component with scenario selector, start/stop buttons, progress bar with real-time polling (1s interval)
- **19 integration tests**: CRUD operations, seed loading, idempotency, built-in protection, export/import round-trip

### Decisions
- Scenarios are template-bound (not device-bound) — reusable across all devices of the same template
- Steps use `register_name` (not register ID) for portability in export/import
- `total_duration_seconds` is computed as `max(trigger_at + duration)` across all steps on create/update
- Built-in scenarios: cannot be updated or deleted (403/409), but can be cloned and exported
- ScenarioRunner is in-memory only — no execution history persisted to DB (sufficient for MVP)
- Timeline editor uses CSS-based positioning (percentage of total duration) rather than a charting library

### Test results
- 278 backend tests passing (19 new for scenarios)
- Frontend TypeScript check + Vite build pass

---

## 2026-03-27 — Publish/Stop UX Unification (#11)

### What was done
- MQTT card redesigned with edit/publish mode separation
  - All form fields disabled during publishing
  - Info alert: "Stop publishing to edit settings"
  - Auto-save on Start Publishing
- Device list: added `mqtt_publishing` boolean to API response (LEFT JOIN mqtt_publish_configs)
- Device list: green MQTT tag shown for devices actively publishing
- Device detail: MQTT Publishing tag shown in status area
- Button style unification (green primary for start, danger for stop)

### Decisions
- Kept Modbus and MQTT architecturally separated (no state machine changes)
- Used LEFT JOIN + boolean field instead of N+1 frontend queries for MQTT status
- MQTT tag only shown when device is running AND mqtt_publishing is true

---

## 2026-03-25 — Frontend Profile Selector (Phase 8.3)

### What was done
- **Profile types, API client, store**: New `profile.ts` types, `profileApi.ts`, `profileStore.ts` following existing patterns
- **ProfilesTab**: Profile list table in template detail with edit/delete/set-default actions, built-in protection
- **ProfileFormModal**: Create/edit modal with per-register config table (reuses DataModeTab pattern)
- **TemplateForm Tabs**: Wrapped Register Map + Profiles in Tabs for edit/view mode
- **CreateDeviceModal profile dropdown**: Fetches profiles on template change, pre-selects default, shared between single/batch tabs
- **Device types**: Added `profile_id` to `CreateDevice` and `BatchCreateDevice`

### Decisions
- Profile dropdown hidden when template has zero profiles (clean UX)
- Shared profile state between single/batch tabs (not per-form)
- Built-in profile configs are read-only in modal; name/description still editable

---

## 2026-03-25 — MQTT Adapter (Phase 8.2)

### What was done
- **MQTT protocol adapter**: `MqttAdapter` class extending `ProtocolAdapter` base, using `aiomqtt` for async MQTT publish
- **DB models + migration**: `mqtt_broker_settings` (global, single-row) and `mqtt_publish_configs` (per-device, one-to-one)
- **MQTT service layer**: CRUD functions for broker settings and per-device publish configs with upsert semantics
- **API routes**: `GET/PUT /system/mqtt` (broker), `GET/PUT/DELETE /system/devices/{id}/mqtt` (publish config), `POST /system/mqtt/test` (connection test), `POST /system/devices/{id}/mqtt/start|stop` (publish control)
- **Frontend UI**: Broker settings form in Settings page, per-device MQTT publish config card in Device Detail page
- **System export/import integration**: Broker settings and publish configs included in export JSON, imported with upsert
- **Docker Compose**: Optional mosquitto service behind `profiles: ["mqtt"]` for dev testing
- **Tests**: 30 new tests (22 MQTT CRUD/adapter + 8 export/import integration)
- **Rebase onto dev**: Resolved conflicts with simulation profiles branch (5 conflict files)

### Decisions
- MQTT adapter reads values from SimulationEngine at publish time (no register sync needed)
- Broker connection is lazy — adapter starts inactive if no settings configured, does not block other adapters
- Password masking: API responses show `****`, PUT with `****` preserves existing password
- Mosquitto in docker-compose is dev-only (profiles flag), production uses external broker
- Export includes unmasked password for portability; import preserves existing password on `****`

### Issues encountered
- MQTT branch diverged from dev before simulation profiles were added — required rebase with 5 conflict resolutions
- Template creation tests initially failed due to wrong `byte_order` value (`"big"` vs `"big_endian"`)

### Test results
- 229 backend tests passing (30 new for MQTT)
- All existing tests unaffected by rebase

---

## 2026-03-25 — Simulation Profiles

### What was done
- **New `simulation_profiles` table**: ORM model, Alembic migration, JSONB configs column storing reusable simulation parameter sets
- **Profile CRUD API**: Full REST endpoints at `/api/v1/simulation-profiles` with list, get, create, update, delete operations
- **Profile auto-apply on device creation**: `profile_id` field added to `DeviceCreate`/`DeviceBatchCreate`. Absent = auto-apply default profile; explicit `null` = skip; UUID = apply specific profile
- **Built-in profiles**: Three seed JSON files (three-phase meter, single-phase meter, solar inverter) loaded at startup with physically consistent simulation parameters
- **Seed loader**: `seed_builtin_profiles()` function added to loader, called from app startup after template seeding
- **Comprehensive tests**: 22 new tests covering CRUD, auto-apply, batch apply, seed loading, idempotency, and built-in protection

### Decisions
- Profile configs are **copied** into `simulation_configs` at apply time — no ongoing reference. This allows users to customize per-device without affecting the profile
- At most one `is_default=true` per template, enforced via PostgreSQL partial unique index
- Built-in profiles: configs are immutable (403 on update), cannot be deleted (403), but name/description can be changed
- `profile_id` absent vs explicit `null` distinguished via `model_fields_set` in Pydantic

### Issues encountered
- Alembic autogenerate produced empty migration when run inside Docker container without volume mount — solved by rebuilding the image after code changes
- Test ordering issue: `seed_builtin_profiles` uses global `async_session_factory` which gets stale connections across event loops — solved by patching with a fresh session factory in tests

---

## 2026-03-22 — Template & Device UX Improvements

### What was done
- **Device edit UI**: Added `EditDeviceModal` component for editing name, description, slave ID, port. Integrated into DeviceList (pen icon) and DeviceDetail (Edit button). Slave ID/port disabled when running.
- **Built-in template read-only view**: Added View button (eye icon) on TemplateList for built-in templates. TemplateForm now detects `is_builtin` and shows read-only mode with "Built-in" tag, disabled inputs, and Back button instead of Save.
- **Template import error feedback**: ImportExportButtons now shows a detailed error modal on import failure, including the specific validation error and a collapsible section with expected JSON format.
- **Port change**: Frontend Docker port changed from 3000 to 3002; CORS updated accordingly.
- **Demo script**: Added `scripts/start-demo.sh` — one-command startup that builds Docker containers, creates a test device, configures simulation, and verifies Modbus TCP reads.
- **Cleanup**: Removed unused imports in AnomalyTab and Simulation index.

### Decisions
- Edit modal reused across both list and detail pages for consistency
- Running devices can still open edit modal (to change name/description), but Slave ID and port fields are disabled — backend also enforces this but frontend gives immediate feedback
- Built-in templates use the same TemplateForm in read-only mode rather than a separate component
- Port 3002 chosen to avoid conflicts with other local services on 3000

### Issues encountered
- Pre-existing TypeScript errors in other pages (antd v6 icon imports, recharts types) — not related to these changes

---

## 2026-03-20 — Phase 7: System Finalization

### What was done
- Implemented system config export API (`GET /api/v1/system/export`) — full snapshot of templates, devices, simulation configs, anomaly schedules as JSON file download
- Implemented system config import API (`POST /api/v1/system/import`) — upsert by name/slave_id, skips built-in templates, all-or-nothing transaction
- Created Pydantic schemas for export/import format (reference by name, not UUID)
- Built frontend Settings page with export button (file download) and import button (file upload with result summary modal)
- Added Settings route and sidebar menu item
- Created GitHub Actions CI pipeline: backend (Python 3.12 + PostgreSQL 16 service + ruff lint + pytest) and frontend (Node 20 + tsc + build)
- Added Playwright smoke tests for all 5 pages (Templates, Devices, Simulation, Monitor, Settings)
- Added `.dockerignore` files for backend and frontend
- Created CONTRIBUTING.md with development setup, conventions, and PR process
- Backend test coverage: 71% (177 tests passing, 14 new tests for export/import)

### Decisions
- Export format uses names (template_name, device_name) instead of UUIDs for cross-machine portability
- Import upserts templates by `name`, devices by `(slave_id, port)` — existing data gets updated, not duplicated
- Built-in templates (`is_builtin=true`) are exported but skipped on import (already seeded)
- Simulation configs and anomaly schedules are replaced per-device on import (delete-then-insert)
- Playwright tests run against built preview server — no backend required for smoke tests
- CI skips Playwright (not installed in CI yet) — frontend job only does typecheck + build

### Issues encountered
- npm install fails on shared folder (VirtualBox) due to symlink permissions — Playwright added to package.json manually
- Pre-existing antd v6 + React 19 TypeScript issues in icon imports — not related to Phase 7 changes

### Test results
- 177 backend tests passing (14 new for export/import)
- Frontend TypeScript check passes (`tsc --noEmit`)
- Overall backend coverage: 71%

---

## 2026-03-19 — Phase 6: Real-time Monitor Dashboard

### What was done
- Implemented WebSocket `/ws/monitor` backend with 1Hz broadcast loop
- Created MonitorService with in-memory event log (deque, max 100) and data aggregation
- Added per-device communication statistics (DeviceStats) to ModbusTcpAdapter
- Wired event logging into device start/stop, anomaly inject/clear, fault set/clear
- Built frontend Monitor Dashboard: DeviceCardGrid, DeviceDetailPanel, RegisterChart (Recharts), StatsPanel, EventLog
- Created useWebSocket hook with exponential backoff reconnect
- Created monitorStore (Zustand) with rolling register history buffer (300 points)

### Decisions
- Used `Flex` instead of `Row`/`Col` for antd v6 compatibility (Col has TypeScript index signature conflict with children)
- Icons imported without `@ant-design/icons` barrel to avoid `verbatimModuleSyntax` TS errors
- MonitorService queries DB for running devices each snapshot cycle — acceptable for MVP, may need caching if >100 devices
- WebSocket broadcast sends all device data to all clients (no per-device subscription) — simple for MVP

### Issues encountered
- Missing `pymodbus` in requirements.txt — was never added, Docker build cached old layer
- Missing `MODBUS_HOST`/`MODBUS_PORT` in Settings config — main.py referenced them but config never had them
- antd v6 + React 19 has widespread TypeScript issues with icon imports and Col component — pre-existing across codebase

### Test results
- 163 backend tests passing (all existing tests unaffected)

---

## 2026-03-18 — Phase 3: Device Instance Module

### What was done
- Implemented full device instance CRUD backend (Milestone 3.1)
- Implemented frontend device management UI (Milestone 3.2)
- 50/50 backend tests passing; frontend TypeScript check and Vite build pass

### Backend highlights
- **ORM model**: `DeviceInstance` with FK RESTRICT to `device_templates`, unique constraint on `(slave_id, port)`
- **Alembic migration**: `d013e48e688a` creates `device_instances` table
- **Pydantic schemas**: `DeviceCreate`, `DeviceBatchCreate`, `DeviceUpdate`, `DeviceSummary`, `DeviceDetail`, `RegisterValue`
- **Service layer** (`device_service.py`): CRUD, batch create (atomic, up to 50), start/stop state machine, register view (value=None in Phase 3)
- **API routes** (`/api/v1/devices`): list, create, batch create, get detail, update, delete, start, stop, get registers
- **ConflictException** (HTTP 409): used for running device protection and invalid state transitions
- **Template deletion protection**: `delete_template` now checks for referencing devices before allowing deletion
- **Tests**: `test_devices.py` (24 cases) + `test_template_protection.py` (2 cases) = 26 new tests

### Frontend highlights
- **Types**: `DeviceSummary`, `DeviceDetail`, `RegisterValue`, `CreateDevice`, `BatchCreateDevice`, `UpdateDevice` in `src/types/device.ts`
- **API service**: `src/services/deviceApi.ts` wraps all device Axios calls
- **Zustand store**: `deviceStore` holds device list, current device, loading state
- **Pages**: `DeviceList` (table with status badges, start/stop toggle, delete), `CreateDeviceModal` (single + batch tabs), `DeviceDetail` (register map table)
- **Routing**: `/devices` → list, `/devices/:id` → detail

### Key decisions
- **Status is pure DB field in Phase 3**: start/stop only toggles the `status` column; actual Modbus server lifecycle will be added in Phase 4
- **FK RESTRICT**: templates cannot be deleted while devices reference them; service layer checks first with friendly error, DB constraint acts as safety net
- **Batch create is atomic**: any slave_id conflict fails the entire batch
- **DeviceUpdate is full replacement**: consistent with Phase 2's `TemplateUpdate` pattern; `template_id` and `status` are excluded from update schema

### Issues encountered
- VirtualBox shared folder still cannot run `npm install` (symlink restriction); used existing external node_modules at `/home/ken/.ghostmeter-frontend-modules/`
- Frontend build requires using the custom `vite.config.ts` from the external modules directory

---

## 2026-03-17 — Phase 2: Device Template Module

### What was done
- Implemented full device template CRUD backend (Tasks 1–11 of Phase 2 plan)
- Implemented frontend template management UI (Tasks 12–17 of Phase 2 plan)
- 24/24 backend tests passing; frontend build passes

### Backend highlights
- **ORM models**: `DeviceTemplate` + `RegisterDefinition` with cascade delete and two uniqueness constraints (name per template, address+FC per template)
- **Alembic migration**: `448f2e5c6613` creates both tables
- **Pydantic schemas**: `TemplateCreate`/`TemplateUpdate`/`TemplateDetail`/`TemplateSummary`/`TemplateClone` + shared `ApiResponse[T]` envelope
- **Service layer** (`template_service.py`): address overlap validation (per FC, per template), `ForbiddenException` guard on built-in templates for update/delete, export strips IDs for portability
- **API routes** (`/api/v1/templates`): list, create, get, update, delete, clone, export, import
- **Seed loader** (`seed/loader.py`): runs at FastAPI startup, idempotent — skips templates that already exist by name; loads three JSON files: `three_phase_meter.json` (SDM630), `single_phase_meter.json` (SDM120), `solar_inverter.json` (Fronius Symo / SunSpec)
- **Tests**: `test_templates.py` (API integration, 20 cases) + `test_seed.py` (4 cases)

### Frontend highlights
- **Types**: `DeviceTemplate`, `RegisterDefinition`, `TemplateSummary`, `TemplateDetail` in `src/types/template.ts`
- **API service**: `src/services/templateApi.ts` wraps all Axios calls
- **Zustand store**: `templateStore` holds list, loading state, and selected template
- **Pages**: `TemplateList` (table with built-in badge), `TemplateForm` (create/edit with register table), `RegisterTable` (editable rows), `ImportExportButtons`
- **Routing**: `/templates` → list, `/templates/new` → create, `/templates/:id` → edit

### Key decisions
- **PUT replaces registers wholesale**: simpler than PATCH + partial register diffs; client always sends the full register list
- **`/import` route must precede `/{template_id}`**: FastAPI path matching would otherwise treat the literal string `"import"` as a UUID, causing 422 errors
- **Seed data is idempotent**: loader checks name existence before insert; safe to run on every startup without duplicating templates
- **Address overlap uses half-open ranges per FC**: `float32` at address 0 occupies registers 0–1; any other register with address 1 in the same FC would overlap and is rejected
- **VirtualBox workaround carries over**: pytest and npm still run from outside the shared folder (`/home/ken/ghostmeter-venv` and `/home/ken/ghostmeter-node`)

### Issues encountered
- FastAPI route ordering: `/import` must be registered before `/{template_id}` to prevent the literal `"import"` being parsed as a UUID path parameter
- `updated_at` `onupdate` does not trigger on relationship mutations (registers replaced via `clear()` + reassign); workaround: the `get_template` re-fetch after commit returns the DB-refreshed value which is sufficient for tests

---

## 2026-03-17 — Phase 1: Project Skeleton & Foundation

### What was done
- Completed all 3 milestones of Phase 1 (Docker, Backend, Frontend)
- Full stack verified: `docker compose up --build` starts all 3 services successfully
- Backend health check returns `{"status":"ok","database":"connected","version":"0.1.0"}`
- Frontend serves Ant Design layout with 4 navigable pages via nginx

### Key decisions
- **Local dev approach**: Docker only for PostgreSQL, backend/frontend run natively for faster iteration
- **Port 5434**: PostgreSQL mapped to host port 5434 instead of 5432 due to port conflict with existing service on dev machine
- **DATABASE_URL construction**: Uses `@computed_field` to auto-build from individual `POSTGRES_*` env vars, allowing `.env` to be shared between docker-compose and backend app
- **Health endpoint at root**: `GET /health` is at root path (not under `/api/v1`) — exempt from standard response wrapper for infrastructure monitoring compatibility
- **Alembic migration deferred**: Only Alembic infrastructure set up in Phase 1; actual table migrations will be created in Phase 2 when ORM models are defined
- **VirtualBox workaround**: Python venv and npm node_modules stored outside shared folder due to symlink restrictions on vboxsf filesystem

### Issues encountered
- VirtualBox shared folder (`vboxsf`) does not support symlinks, which breaks both Python venv and npm node_modules creation. Solved by placing these in native Linux filesystem (`/tmp/` and `/home/ken/`).
- Port 5432 occupied by existing `enol-pgbouncer` container, switched to 5434.
