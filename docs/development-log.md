# Development Log

## 2026-04-10 — Simulation engine crash recovery and error counting fix

### What was done
- Added `add_done_callback` on each device simulation task to detect unexpected crashes
- Implemented auto-restart with exponential backoff (2s → 4s → 8s → 16s → 32s), max 5 attempts
- After max restart attempts exceeded, device DB status is updated to "error" so the UI reflects reality
- Fixed inner error counting: `adapter.update_register` failures (e.g. pymodbus write errors) now count toward the consecutive error threshold (5 ticks)
- Introduced `_DeviceTaskState` dataclass to track restart count per device, replacing the bare `dict[UUID, Task]`

### Why
When pymodbus lost connectivity (e.g. network disconnection), `adapter.update_register` raised exceptions caught by the inner try-except (line 235). These errors were logged but never counted toward `error_count`, so the outer loop's `error_count` was always reset to 0 — the simulation task kept running but producing no useful output. If the task crashed entirely (unhandled exception), it silently disappeared from `_device_tasks` while the DB still showed `status="running"`. Users saw all register values stuck/null with no indication of a problem.

### Decisions
- Chose exponential backoff (base 2s, max 5 attempts = up to 32s delay) as a balance between quick recovery from transient issues and not hammering a persistently broken adapter
- Kept backward-compatible `_device_tasks` property so existing code (monitor_service, tests) that reads task state doesn't break
- `_on_task_done` callback distinguishes between: cancelled (normal stop), normal return (max errors hit, already handled), and exception (unexpected crash needing restart)

### Files changed
- `backend/app/simulation/engine.py` — crash recovery, error counting, `_DeviceTaskState`
- `CHANGELOG.md` — Fixed section
- `docs/development-log.md` — this entry

### Verification
- `python -m py_compile app/simulation/engine.py` — OK
- `pytest tests/test_simulation_engine.py` — 4/4 passed
- `pytest tests/test_anomaly_*.py tests/test_*simulation*.py` — 45/45 passed
- `ruff check app/simulation/engine.py` — all checks passed

---

## 2026-04-08 — Remove VirtualBox shared-folder path hacks from frontend tooling

### What was done
- Removed `/home/ken/.ghostmeter-frontend-modules/...` absolute paths from `frontend/package.json` scripts. `dev`, `build`, `lint` are now standard `vite` / `tsc -b && vite build` / `eslint .` and work on any machine after `npm install`.
- Deleted `frontend/tsconfig.local.json`, `tsconfig.local.app.json`, `tsconfig.local.node.json` — these pointed at the external `node_modules` directory via `typeRoots` / `paths` and were only useful on the VM.
- Deleted `frontend/.npmrc` (only held a comment describing the workaround).
- Removed the workaround comment block from `frontend/vite.config.ts`.

### Why
These hacks existed because the project lived on a VirtualBox shared folder (`vboxsf`) which does not support the symlinks npm uses in `node_modules`. The workaround was to install `node_modules` in `/home/ken/.ghostmeter-frontend-modules/` (outside the shared folder) and have every script reach into that path explicitly. Current development environment (macOS) no longer needs this, and the hard-coded absolute paths meant nobody else could run `npm run dev` after cloning — first blocker flagged in the consolidation audit.

### Decisions
- Chose full removal over keeping `build:local` as a fallback. The workaround is specific to one obsolete environment; keeping it would force future readers to wonder which script to run. If the VirtualBox setup is ever needed again, the original commit can be reverted from git history.
- `Dockerfile` already used standard `npm run build`, so the container build path was unaffected — verified before deleting.

### Files changed
- `frontend/package.json` — simplified scripts block
- `frontend/vite.config.ts` — removed workaround comment
- `frontend/tsconfig.local.json` — deleted
- `frontend/tsconfig.local.app.json` — deleted
- `frontend/tsconfig.local.node.json` — deleted
- `frontend/.npmrc` — deleted
- `CHANGELOG.md` — Fixed + Removed sections
- `docs/development-log.md` — this entry

### Verification
- Confirmed no remaining references to `ghostmeter-frontend-modules`, `/home/ken`, or `sf_AI_Service_Chatbot` in the repo via grep.
- Dockerfile build path (`RUN npm ci && npm run build`) unaffected since it never touched the removed files.
- `npm run dev` / `npm run build` verification on a clean checkout requires running `npm install` and should be done before merging.

### Next steps
- Consolidation step 4: run a docs-vs-implementation drift check on `api-reference.md` and `database-schema.md`.

---

## 2026-04-08 — Restore GitHub Actions CI pipeline (consolidation step 2)

### What was done
- Recreated `.github/workflows/ci.yml` with the same two-job structure as the original (backend lint/test + frontend typecheck/build).
- Updated two details vs the historical file:
  - Frontend Node version bumped from 20 → 22 to match `frontend/Dockerfile` (`FROM node:22-alpine`)
  - Frontend type check changed from `npx tsc --noEmit` to `npx tsc -b` to match the project-references setup now used by `tsconfig.json`

### Why
The consolidation audit flagged "CI status unknown". Investigation showed:
- Repo had no `.github/workflows/` directory
- `gh run list` returned empty
- But `CLAUDE.md`, `docs/development-log.md`, and `docs/development-phases.md` all claimed "GitHub Actions CI" was in place

This was a docs-vs-reality drift. `git log --all -- '.github/workflows/*'` turned up:
- 655c977 (2026-03-20) `ci: add GitHub Actions pipeline for backend lint/test and frontend build`
- 6d92a2c (2026-03-20, 17 minutes later) `chore: temporarily remove CI workflow (requires workflow scope token)`

The removal was "temporary" pending a PAT with `workflow` scope — never reverted. Restoring it now closes the drift and actually enforces lint/tests on future PRs.

### Decisions
- Restored as a new commit rather than `git revert 6d92a2c` because the file needed the Node 22 / `tsc -b` updates anyway; a revert would have landed stale content.
- Kept the original environment variables hard-coded in the workflow (`POSTGRES_*`, `APP_NAME`, etc.) — these are test-only values, not secrets.
- Did not yet add any new steps (e.g. Playwright e2e smoke) — those belong in a later consolidation task once the baseline is green.

### Files changed
- `.github/workflows/ci.yml` — created (restored + updated)
- `CHANGELOG.md` — CI section
- `docs/development-log.md` — this entry

### Verification
- File content matches the historical 655c977 version character-for-character except for the two documented updates (diffable against `git show 655c977:.github/workflows/ci.yml`).
- YAML structure verified by visual inspection — no Python `yaml` module or `actionlint` available in the local environment to run a formal parse. Will be validated by GitHub itself on first push.
- Pushing this change requires a token/gh auth with `workflow` scope (the same reason it was removed in 6d92a2c). This is a push-time concern, not a commit-time concern.

### Next steps
- Push to remote once the token/auth has `workflow` scope, then verify the pipeline actually runs green on this feature branch's PR.
- Consolidation step 4: docs-vs-implementation drift check on `api-reference.md` and `database-schema.md`.

---

## 2026-04-08 — API reference drift fix (consolidation step 4)

### What was done
Fixed documentation drift found by a systematic comparison of `docs/api-reference.md` against `backend/app/api/routes/` and `backend/app/schemas/`. Added 18 previously undocumented endpoints plus a field and note fix on `RegisterValue`.

Changes to `docs/api-reference.md`:

1. **`RegisterValue` schema block**:
   - Added `oid: string | null` field (used by SNMP templates, `null` for Modbus)
   - Replaced the stale "`Phase 3: always null`" note on `value` with an accurate description: value is the last tick's value (null when stopped / no tick yet) and live clients should subscribe to `/ws/monitor` rather than poll the detail endpoint.

2. **New section: Simulation Configuration** (inserted between Simulation Profiles and MQTT).
   Covers:
   - Schemas: `SimulationConfigCreate`, `SimulationConfigBatchSet`, `SimulationConfigResponse`, `FaultConfigSet`, `FaultConfigResponse` (including fault-type param tables)
   - Endpoints: `GET/PUT/DELETE /devices/{id}/simulation`, `PATCH /devices/{id}/simulation/{register_name}`, `GET/PUT/DELETE /devices/{id}/fault`
   - Documented in-memory-only behaviour of faults (cleared on restart).

3. **New section: Anomaly Injection** (inserted after Simulation Configuration).
   Covers:
   - Both real-time injection and persisted schedules as the two mechanisms
   - Schemas: `AnomalyInjectRequest`, `AnomalyActiveResponse`, `AnomalyScheduleCreate`, `AnomalyScheduleBatchSet`, `AnomalyScheduleResponse`
   - Params tables per anomaly type (`spike`, `drift`, `flatline`, `out_of_range`, `data_loss`)
   - Endpoints: `POST/GET/DELETE /devices/{id}/anomaly`, `DELETE /devices/{id}/anomaly/{register_name}`, `GET/PUT/DELETE /devices/{id}/anomaly/schedules`
   - Noted the route ordering constraint (the `/schedules` routes must come before `/{register_name}` to avoid wildcard collision — this was already done in `anomaly.py` but is worth documenting so future editors don't reorder).

4. **Simulation Profiles section**: added the three missing endpoints.
   - `GET /simulation-profiles/template/{template_id}` — download blank profile JSON (raw file download, not `ApiResponse`)
   - `GET /simulation-profiles/{profile_id}/export` — export profile as JSON file
   - `POST /simulation-profiles/import?template_id=...` — upload profile JSON, with the required `template_id` query param documented explicitly

Changes to `docs/development-phases.md`:

- Added **Milestone 8.6 — Polish & UX Fixes** capturing auto-resume, Device Detail live values (#19), Open in Monitor deep-link, anomaly param form, batch naming fix
- Added **Milestone 8.7 — Consolidation** (in progress) with checked boxes for steps done so far and unchecked boxes for remaining work, including the three audit-surfaced issues (#21 #22 #23)

### Why
The consolidation audit surfaced that `api-reference.md` documented only the core CRUD surface — anomaly, simulation-config, fault, and the profile import/export variants were all completely absent despite being shipped and actively used. The `RegisterValue.value` note still said "Phase 3: always null" even though #19 had closed that behaviour weeks ago. This is the kind of drift that silently erodes trust in the docs and makes external integration impossible.

The phases doc wasn't dangerously wrong but also hadn't captured anything after Scenario Mode (milestone 8.5). Adding 8.6 and 8.7 gives a clean line of sight into what's in flight without rewriting earlier phases.

### Decisions
- **Where to put the new sections**: I chose top-level sections ("Simulation Configuration", "Anomaly Injection") rather than sub-sections of Devices because (a) they have their own pydantic schemas with meaningful surface area, and (b) the existing `Simulation Profiles` section is already a peer, so three "Simulation*" / anomaly sections sit consistently together. The table of contents pattern of the file is one H2 per logical resource group, which I followed.
- **Left Devices section alone**: Not re-touched beyond the `RegisterValue` schema fix. Its CRUD docs are accurate.
- **Did NOT document `/ws/monitor` snapshot shape in this pass**: there's a whole monitor snapshot structure worth documenting, but that's a second drift item and the user asked specifically for the drift report's 18 endpoints + oid. Deferred — will add to consolidation backlog if it matters.
- **Left the "Phase 3" vintage comment on `RegisterValue` docstring in `backend/app/schemas/device.py`**: that's code, not docs. Code comments can drift but this one just says "Phase 3: always None" and the user didn't ask for a code sweep. Leave for now.

### Files changed
- `docs/api-reference.md` — ~320 lines added across four edits
- `docs/development-phases.md` — new Milestones 8.6 and 8.7
- `CHANGELOG.md` — Documentation section under [Unreleased]
- `docs/development-log.md` — this entry

### Verification
- `grep -E '^(### )?#{0,3} ?`[A-Z]+ /api/v1' docs/api-reference.md` — every added endpoint can be located by its method + path.
- Cross-checked each new endpoint path against the actual route decorator in `backend/app/api/routes/{anomaly,simulation,simulation_profiles}.py` to make sure method and path match.
- No code was changed — this is documentation-only, so there is no build/test to rerun.

### Next steps
- Consolidation step 6: run backend `pytest` full suite and confirm no skips / flakies.
- Consolidation step 5: cut a release (the README's `0.3.0` badge vs. the pile of Unreleased entries is its own drift).

---

## 2026-04-08 — Clear accumulated ruff lint debt so CI goes green

### What was done
The first real CI run on PR #24 (after restoring `.github/workflows/ci.yml`) surfaced **91 ruff errors** that had accumulated in `backend/` between 2026-03-20 (when CI was removed) and today. Fixed all of them.

**Breakdown:**
- 31× `I001` unsorted-imports — auto-fixed by `ruff check --fix`
- 12× `F401` unused-import — auto-fixed
- 44× `E501` line-too-long — handled manually; 16 of them live in `alembic/versions/*.py` (see decision below), the other 28 were hand-wrapped
- 2× `F841` unused-variable — dropped the unused `devices = await _setup_devices(...)` binding in `tests/test_batch_device_ops.py` where the return value was never read
- 1× `E402` module-level import not at top — added `# noqa: E402` with an explanatory comment in `app/services/scenario_runner.py`, since the late import exists to break a circular dependency
- 1× `W291` trailing-whitespace — removed trailing space on `Revises: ` line in `alembic/versions/448f2e5c6613_...py`

### Why
CI was off from 2026-03-20 to 2026-04-08. During that window several feature branches landed on dev (MQTT, SNMP, Scenarios, Device Detail live values, anomaly params form) without a lint gate. The 91 errors are the accumulated cost. The consolidation audit called this out as the expected consequence of "step 2: restore CI" — first run is guaranteed to be red.

### Decisions
- **`alembic/versions/*` → `E501` per-file-ignore** instead of hand-wrapping 16 lines in migration files. These files are auto-generated by `alembic revision --autogenerate`; hand-wrapping the `sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)` lines would just get overwritten on the next regen. Standard Python ecosystem practice. Added one line to `backend/pyproject.toml` under `[tool.ruff.lint.per-file-ignores]`.
- **Did NOT run `ruff format`** even though it would fix some issues. `ruff format` would reformat 71 files and touch far more than the 91 specific errors — that's churn, not cleanup. Kept the diff scoped to exactly what was needed.
- **`# noqa: E402` over restructuring scenario_runner.py**: the late `from app.simulation import anomaly_injector as _anomaly_injector` was added to avoid a real circular import between `services` and `simulation` packages. Moving it to the top would need a restructure that's out of scope. A documented `noqa` is clearer than rearranging the package boundary.
- **Dropped unused `devices =` bindings in test_batch_device_ops.py** rather than converting to `_` or adding `# noqa: F841`. The tests were using the helper for side effects only — the assignment was a leftover from a refactor. Deleting the assignment is the real fix.
- **Used `def _sort_key` instead of an inline `lambda`** in `engine.py:189`. First attempt was a named lambda with `# noqa: E731`; realized that's trading one lint error for another. A real nested function is cleaner.

### Files changed
- `backend/pyproject.toml` — per-file-ignores
- `backend/app/api/routes/devices.py`, `backend/app/api/routes/scenarios.py` — wrapped long f-strings and decorators
- `backend/app/main.py` — wrapped long logger call and `include_router` calls
- `backend/app/services/scenario_runner.py` — `# noqa: E402` + comment; wrapped long condition and logger call
- `backend/app/simulation/engine.py` — replaced long inline lambda with a named `_sort_key`
- `backend/alembic/versions/448f2e5c6613_*.py` — removed trailing whitespace
- 36 auto-fixed files (imports): `alembic/env.py`, 11 migration files, 11 app files, 13 test files (see `git show` for full list)
- 8 manually-wrapped test files: `test_batch_device_ops.py`, `test_modbus.py`, `test_modbus_fault.py`, `test_device_profile_apply.py`, `test_device_simulation_integration.py`, `test_scenarios.py`, `test_seed_profiles.py`, `test_simulation_api.py`

### Verification
- `ruff check .` from `backend/` → `All checks passed!` (exit 0)
- `python3 -m compileall -q app/ alembic/versions/ tests/` → exit 0 (no syntax errors introduced)
- Pytest not runnable locally in this environment (no venv with backend deps), but all 91 errors are pure formatting / unused-binding / line-wrap — none of them change runtime behaviour. CI will be the real test.

### Next steps
- Push this commit, watch PR #24 CI turn from red to green.
- Consolidation step 6: full `pytest` run in CI.
- Consolidation step 5: cut a release.

---

## 2026-04-08 — API reference drift fix (consolidation step 4)

### What was done
- **Live register values in Device Detail**: Connected Device Detail page to the existing `ws/monitor` WebSocket. Register table now overlays real-time values from the monitor broadcast instead of showing `—` (null). When the device is not running, values remain `—`.
- **"Open in Monitor" button**: Added a button on Device Detail that navigates to `/monitor?device=<id>`, auto-selecting the device in the Monitor page. Button is disabled when the device is not running.
- **Connection status badge**: Register Map card title shows a `Live` / `Disconnected` badge when the device is running.
- **Monitor auto-select via query param**: Monitor page reads `?device=` query param on mount, waits for WebSocket data to arrive, then auto-selects the matching device. Query param is cleared after use to avoid stale state.

### Decisions
- Reused the existing `useWebSocket` hook and `ws/monitor` endpoint — no backend changes needed
- Used `useMemo` to merge live values into the register list (keyed by register name), keeping the original register metadata (address, data type, etc.) from the REST API
- Used a `useRef` flag (`autoSelectApplied`) to ensure the query param auto-select fires only once, even if `devices` array updates multiple times
- Disabled the "Open in Monitor" button for non-running devices since the monitor only shows running devices

### Files changed
- `frontend/src/pages/Devices/DeviceDetail.tsx` — WebSocket connection, live value overlay, Open in Monitor button
- `frontend/src/pages/Monitor/index.tsx` — `?device=` query param auto-select logic

---

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
