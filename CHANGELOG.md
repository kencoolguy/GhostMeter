# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Documentation
- Deployment guide: new "team member access" coverage — add teammate emails to the Cloudflare Access policy for Web UI/API, and share the Linode via **Tailscale node sharing** (single-machine share, no tailnet membership needed) for the protocol ports (Modbus 502 / OPC UA 4840 / SNMP 161), including Windows client setup and connectivity checks.

### Added
- **Built-in Cloudflare Tunnel support** for deploy hosts: `docker-compose.prod.yml` gains an opt-in `cloudflared` sidecar (compose profile `tunnel`); `deploy.sh` enables it only when `CLOUDFLARE_TUNNEL_TOKEN` is set in `.env`, so tokenless deployments are unaffected. Deployment guide rewritten with the full Zero Trust procedure — **a Cloudflare Access policy is mandatory before exposing a Public Hostname** (the API has no authentication of its own).

### Removed
- **Fake "Live" badge in the app header**: it was static decoration — always glowing regardless of actual WebSocket state — and its height overflowed the 64px header (antd's inherited `line-height: 64px` + badge padding). The real connection indicator lives on the Monitor page title (green "Live" / red "Disconnected", bound to WS state).

### Fixed
- **All 14 pre-existing ESLint problems fixed (12 errors / 2 warnings) — `npm run lint` is now clean** (issue #63). Highlights: `useWebSocket` rewrote its self-referencing reconnect closure into an effect-scoped lifecycle — the message handler now lives in a ref, so a changed callback identity no longer tears down and reopens the socket; six setState-in-effect occurrences replaced with derived state (`useMemo` base + user-edit overlay in DataModeTab / ProfileFormModal, derived default profile in CreateDeviceModal, async-init in TemplateForm); `handleExport` moved out of `ImportExportButtons.tsx` into `exportTemplate.ts` (react-refresh). WS reconnect verified end-to-end: Monitor shows Live → backend stopped → Disconnected → backend restarted → Live restores automatically.

- **Monitor WebSocket now connects same-origin** (`wss://`/`ws://` + current host + `/ws/monitor`) instead of hardcoding `ws://<hostname>:8000`. The dev server (vite `/ws` proxy) and production nginx (`location /ws/`) have always proxied WebSocket traffic, but the client bypassed them — so live values only worked when the backend port was directly reachable (Tailscale), and broke behind any reverse proxy or HTTPS tunnel (mixed-content `ws://` is blocked on https pages).

## [0.4.2] - 2026-06-11

### Fixed
- **Builtin scenarios never seeded in any environment**: the scenario seed JSONs referenced template names that don't exist in the template seeds (`Solar Inverter (Fronius Symo)` / `Three-Phase Power Meter (SDM630)` vs. the actual `SunSpec Solar Inverter` / `SDM630 Three-Phase Meter`), and `seed_builtin_scenarios` only logs a WARNING on a miss — so every deployment shipped with zero builtin scenarios. Seed names fixed; two guard tests added (static cross-reference of scenario seeds against template seeds, and an end-to-end seed test asserting the builtin scenarios actually land).
- `.env.example` no longer pins `APP_VERSION=0.1.0` — the value overrode the application's real version via pydantic-settings, making deployed instances report a stale version at `/health`. The version is a code constant, not deployment config.

## [0.4.1] - 2026-06-11

### Fixed
- **OPC UA delay fault no longer blocks the event loop**: the delay was a `time.sleep` inside asyncua's synchronous value callback, so while one client read a delay-faulted node, every other protocol server, the REST API, the WebSocket broadcast and all simulation ticks stalled for up to 10 s (a 1 Hz poller re-triggered it continuously). The sleep now runs in an async `CallbackType.PreRead` server callback, suspending only the requesting session. Verified by a regression test that keeps a 50 ms heartbeat ticking during a 1.2 s delayed read.
- **Builtin "Fault Disconnect" scenario flipped dc_voltage upward mid-step**: the seed used `max_drift: -50`, but `max_drift` is a magnitude — the injector clamps with `abs(drift) > abs(max_drift)` and takes the direction from `drift_per_second`'s sign, so once the cap was reached (10 s into the 28 s step) the clamp produced `-max_drift = +50` and the intended -50 V sag jumped to +50 V above baseline for the remaining 18 s. Seed fixed to `max_drift: 50`; Alembic data migration `a7c3e91f4b20` repairs already-seeded builtin rows (user scenarios untouched).

### Changed
- **Scenario steps now validate anomaly params** like real-time injection and schedules already did (shared `AnomalyParamsBase`): required params per type, spike `multiplier > 0` / `probability` in [0,1], drift `max_drift > 0`. Previously a step with missing or invalid params was accepted and only failed at runtime mid-scenario. Affects scenario create / update / import (422 on bad params).

## [0.4.0] - 2026-06-11

### Added
- Comm-layer fault simulation for BACnet, SNMP, and MQTT — all five protocols now support `delay` / `timeout` / `intermittent` faults through `PUT /devices/{id}/fault` (pull-based, same model as Modbus). BACnet: faulted devices also stop answering Who-Is (fully dark, like a real dead device); `exception` maps to BACnet Error `device/operationalProblem`. SNMP: `exception` maps to `genErr`; delayed responses are deferred without blocking the event loop. MQTT: `timeout` stops publishing, `intermittent` randomly skips publishes, `delay` publishes late; `exception` is rejected with 422 (publish-only protocols have no request/response channel to return an error on).
- BACnet/IP protocol adapter (5th protocol): Who-Is/I-Am discovery, ReadProperty / ReadPropertyMultiple. One UDP port (47808) with a virtual-network router topology — each device is an independent BACnet device instance (`100000 + slave_id`); registers map to read-only analog-input objects with engineering units. Per-device read statistics included.
- Builtin template "Energy Meter (BACnet)" with Normal Operation profile.
- Deployment tooling for exposed hosts: `docker-compose.prod.yml` overlay binds all published ports to `BIND_IP` (Tailscale IP) and stops publishing PostgreSQL, so nothing is exposed on the public network interface
- `deploy.sh` one-shot deploy script (applies prod overlay, runs Alembic migrations before startup, brings services up)
- `update.sh` one-shot update script (pulls latest `dev`, checks `.env` has `BIND_IP`, then runs `deploy.sh`)
- `docs/deployment.md` — concise Linode deployment guide (Tailscale + Cloudflare Tunnel)
- `.env.example`: new `BIND_IP` setting (defaults to 127.0.0.1 when unset, failing safe to local-only)
- OPC UA comm-layer fault simulation: delay / timeout / exception / intermittent now
  apply to OPC UA devices via per-node value callbacks (push-based; attaches on fault set,
  detaches on clear). Modbus behavior unchanged.
- OPC UA server adapter: exposes simulated devices as browsable Variable nodes (Read + Subscribe, Anonymous + SecurityPolicy None) via asyncua
- Built-in "Energy Meter (OPC UA)" template (11 registers) + Normal Operation profile
- OPC UA protocol option in template creation
- OPC UA server port 4840 exposed in docker-compose
- OPC UA out-of-range values (e.g. from anomaly injection) are clamped to the node's Variant type range, so an over-range value saturates instead of making the node unreadable for clients
- OPC UA device nodes are browse-addressable with a `(#slave_id)` qualifier, keeping same-named devices distinct in the address space
- Monitor 首頁重做：卡片網格 + KPI panel + sparkline + 即時值動畫 + Event toast/drawer (issue #29)
- 完全沒設備時的引導空狀態（內建模板捷徑）
- WebSocket monitor_update payload 新增 `mqtt_broker_connected` 欄位
- DeviceMonitorData 新增 `mqtt_stats`、`template_name` 欄位

- Auto-resume: backend now automatically resumes running devices on startup (registers in protocol adapters + restarts simulation engine)
- Device Detail: register table now shows live values via WebSocket (replaces hard-coded null)
- Device Detail: "Open in Monitor" button navigates to Monitor page with device auto-selected
- Device Detail: Live/Disconnected connection status badge on Register Map card
- Monitor: supports `?device=<id>` query param for auto-selecting a device on page load

- Scenario mode: reusable anomaly injection timelines bound to device templates
- Scenario CRUD API (`/api/v1/scenarios`) with list, get, create, update, delete, export, import
- Scenario execution API: start/stop/status per device (`/api/v1/devices/{id}/scenario/...`)
- ScenarioRunner: async executor that triggers anomaly injections on a timeline
- Built-in scenario seeds: Power Outage Recovery, Voltage Instability, Inverter Fault Sequence
- `scenarios` and `scenario_steps` DB tables with Alembic migration
- Frontend Scenarios page: list view with template filter, create/edit/delete/clone/export/import
- Frontend timeline editor: drag-and-drop anomaly blocks on a register×time grid
- Frontend scenario execution card on Device Detail page with start/stop and real-time progress
- 19 integration tests for scenario CRUD, seed loading, built-in protection, and export/import

### Changed
- `/` route 改導向 `/monitor`（原 `/templates`）
- 側邊欄 Monitor 移到第一位
- Monitor service 不再 filter 掉 stopped 設備（卡片網格會淡化顯示）
- DeviceCard 點擊行為改為跳轉 `/devices/{id}`（取代同頁展開 detail panel）
- ProtocolManager.get_adapter() 改為回傳 Optional（呼叫端統一加 None check + RuntimeError）
- **Pre-release /simplify 清理**（行為不變的內部重構 + 兩處小幅 UX 補完）：
  - Fault 能力改由 adapter 以 class 屬性 `supported_fault_types` 宣告，REST 層改為泛用檢查（原本是 route 內寫死的 MQTT 字串判斷）；422 訊息文字改為通用格式，`error_code` 不變
  - 設備啟動與重啟自動恢復共用 `device_service.register_device_runtime()`（原本 `app/main.py` 複製了一份註冊流程，兩邊已出現 drift）；SNMP 改為在 `add_device` 直接寫入 OID→register name 對照，移除兩段式的 `set_register_names`
  - `get_device_protocol` 由 3 個 query（含整組 register selectinload）縮成單一 JOIN scalar query（fault set/clear 路徑）
  - OPC UA fault callback 改用共用的 `get_delay_seconds` / `get_failure_rate`（五協議中最後一個 inline 寫死 clamp 的）
  - 前端 anomaly 型別中繼資料（選項、參數欄位 schema、顏色）統一到 `constants/anomaly.ts`；StepPopover 原本宣告卻從未套用的預設值改為套用 AnomalyTab 的版本（spike: multiplier 2.0 / probability 0.1），timeline 與 scenario badge 顏色統一
  - monitorStore 的 register history 只累積 running 設備的 primary register（sparkline 是唯一消費者；原本每秒為所有 register 複製 300 點陣列）
  - DeviceDetail 收到 1 Hz broadcast 時若值未變不再 setState（整頁不再每秒重繪）
  - `/monitor?device={id}` 參數補上消費端：Monitor 頁會捲動到對應設備卡（原本參數寫了沒人讀）
  - Monitor 元件改用 global.css 既有的 `--gm-*` CSS 變數（原本同一份色票 inline 硬編碼 ~25 處）
  - 共用 `utils/download.ts`（downloadBlob/downloadJson）、`services/ws.ts`（MONITOR_WS_URL）；ScenarioEditor 改走 `templateApi`
  - 移除死代碼：SimulationEngine `_device_tasks` 相容 property、從未被讀取的 `last_restart`；BACnet 兩個 byte-identical read handler 合併；scenario step 欄位清單三份手抄合併為 helper
  - 測試:`tests/netutil.py` 共用 free-port helpers（原本 5 個檔案各自定義）、`clean_faults` 改為 conftest 全域 autouse fixture

- Monitor DeviceCard preview: defaults to total_power + total_energy instead of voltage_l1/l2
- Monitor chart selector: changed to multi-select, defaults to total_power + total_energy
- Batch device name prefix: removed extra space between prefix and slave ID (e.g. "Meter1" instead of "Meter 1")

- MQTT publish config card: edit/publish mode separation — fields locked during publishing, "Stop publishing to edit settings" hint
- MQTT publishing status indicator (green `MQTT` tag) in device list and device detail pages
- `mqtt_publishing` boolean field added to device list API response
- Unified button styles: Start Publishing uses green primary, Stop Publishing uses danger

### Fixed
- **Modbus fault params were unsanitized**: `delay_ms` was applied raw with no cap — `delay_ms=999999` blocked the response (and the event loop, since `trace_pdu` is a sync callback) for ~17 minutes, while the other four protocols cap at 10 s; and a malformed `failure_rate` (e.g. a string) raised `TypeError` inside `trace_pdu`, killing the request. Modbus now consumes the shared `get_delay_seconds` (10 s cap, NaN/inf guard) and `get_failure_rate` (0–1 clamp) helpers — fault-param semantics are now identical across all five protocols.
- **BACnet replies deadlocked on wildcard bind (`0.0.0.0/0`, the production default) on hosts that cannot bind 255.255.255.255** (e.g. macOS): bacpypes3 creates a second endpoint task for the subnet broadcast address, and `IPv4DatagramServer.indication()` awaits ALL transport tasks before sending any reply — with `/0` the broadcast is 255.255.255.255, whose bind fails on macOS and retries forever, so inbound requests arrived but every response hung. The adapter now drops the doomed broadcast endpoint task when the configured prefix has no usable subnet broadcast (prefixlen 0) and logs a warning; unicast reads work, broadcast Who-Is discovery requires a concrete interface CIDR.
- **BACnet WriteProperty was accepted (spec violation)**: bacpypes3's local analog-input objects accept writes to presentValue (runtime-verified: wrote 999.0, re-read 999.0). Simulated devices are read-only — values come from the simulation engine — so `WriteProperty` now returns a proper BACnet Error (`property` / `writeAccessDenied`) and the simulated value is untouched.
- **SNMP devices stopped serving values after a restart**: the startup auto-resume path (`app/main.py`) re-registered OIDs but, unlike `device_service.start_device`, never called `set_register_names`, so resumed SNMP devices resolved OIDs by raw-OID key instead of register name and returned `noSuchObject`. Resume now rebuilds the SNMP OID→name map, so SNMP survives restarts / boot auto-start.
- **SNMP agent never served register values**: the adapter registered OIDs and could `resolve_oid()`, but `start()` wired pysnmp's command responders to the default (empty) MIB context, so every real GET/GETNEXT returned `noSuchObject` (unit tests only called `resolve_oid` directly, so they passed). Added a `_DynamicMibController` (`AbstractMibInstrumController`) bridging GET/GETNEXT to `resolve_oid`/`get_next_oid` and registered it on the null context. Added an integration test that performs a real SNMP GET/GETNEXT through the agent.
- **UPS "Normal Operation" profile crashed the simulation engine**: `output_power`'s computed expression used bare variable names (`output_voltage * output_current`) instead of the required `{braces}`, so the parser saw an `ast.Name` and raised, stopping the device after 5 consecutive errors. Fixed the seed expression to `{output_voltage} * {output_current}`; added a seed-validation assertion that all computed expressions use braced variables.
- **CI 6h timeout on OPC UA server tests** (root cause of issue #37, previously mis-attributed to asyncpg): coverage's default C trace function fires per-line on every module, and asyncua rebuilds its ~100k-line standard address space on each `Server.init()`. Under `pytest --cov` each OPC UA server test took ~11 min, blowing the 6h job limit. Fixed by `[tool.coverage.run] core = "sysmon"` (PEP 669 `sys.monitoring`), which skips instrumentation of non-`source` files — `Server.init()` drops from >240s to ~0.4s under coverage.
- Quieted the `asyncua` logger to WARNING in `app/main.py` (secondary cleanup): each `Server.init()` emits ~1100 INFO lines loading the standard address space, spamming startup logs. Not the CI fix.

- Pinned `pymodbus>=3.12,<3.13`: the unbounded `>=3.12` constraint resolved to 3.13.0 on fresh installs (CI / container rebuild), whose `ModbusServerContext(devices={})` change broke the Modbus TCP server and its tests. Capped to the 3.12.x line until the adapter is adapted to 3.13.
- Simulation engine crash recovery: tasks that crash (e.g. network disconnection) now auto-restart with exponential backoff (max 5 attempts), and DB status correctly updates to "error" when recovery fails
- Inner adapter errors (e.g. pymodbus write failures) now count toward consecutive error threshold, preventing silent simulation death while device status stays "running"
- **Test suite now uses an isolated `ghostmeter_test` database** instead of running TRUNCATE on the production database — previously, running pytest inside the backend container would wipe all production data
- Devices with status=running showed no register values after backend restart (simulation engine was not resumed)
- Frontend `package.json` scripts no longer hard-code VirtualBox shared-folder workaround paths (`/home/ken/.ghostmeter-frontend-modules/...`); `npm run dev` / `npm run build` / `npm run lint` now use standard tooling and work on any machine after `npm install`

- Resolved 91 ruff lint errors accumulated in `backend/` since CI was removed on 2026-03-20 (31 unsorted imports, 12 unused imports, 44 line-too-long, 2 unused variables, 1 module-level import not at top, 1 trailing whitespace). CI is now green.
- `backend/pyproject.toml`: added `alembic/versions/*` to ruff `per-file-ignores` for `E501` — auto-generated migration files get long type declarations that reappear on each regen and shouldn't be hand-wrapped.
- `backend/app/services/scenario_runner.py`: documented why the `_anomaly_injector` import is late (circular-import avoidance) and added `# noqa: E402` with the explanation.

### Removed
- `pages/Monitor/DeviceDetailPanel.tsx`、`RegisterChart.tsx`、`StatsPanel.tsx`、`EventLog.tsx`
- monitorStore 的 `selectedDeviceId` / `selectDevice`

- `frontend/tsconfig.local.json`, `tsconfig.local.app.json`, `tsconfig.local.node.json` (VirtualBox shared-folder node_modules workaround — no longer needed)
- `frontend/.npmrc` comment file (workaround documentation)
- `frontend/package.json` `build:local` script (workaround for vboxsf symlink issue)

### CI
- Restored `.github/workflows/ci.yml` (originally added in 655c977 and removed in 6d92a2c due to missing workflow-scope token); pipeline runs on push and PR to `dev`/`main`
- Backend job: Python 3.12 + PostgreSQL 16 service + ruff lint + alembic migrate + pytest with coverage
- Frontend job: Node 22 (aligned with Dockerfile) + `tsc -b` type check + `npm run build`

### Documentation
- `docs/api-reference.md`: documented 18 previously-undocumented endpoints surfaced during consolidation drift check
  - Anomaly injection: `POST/GET/DELETE /devices/{id}/anomaly`, `DELETE /devices/{id}/anomaly/{register_name}`, `GET/PUT/DELETE /devices/{id}/anomaly/schedules`
  - Simulation config: `GET/PUT/DELETE /devices/{id}/simulation`, `PATCH /devices/{id}/simulation/{register_name}`
  - Fault control: `GET/PUT/DELETE /devices/{id}/fault`
  - Simulation profiles: `GET /simulation-profiles/template/{template_id}` (blank template download), `POST /simulation-profiles/import` (with `template_id` query param), `GET /simulation-profiles/{profile_id}/export`
- `docs/api-reference.md` `RegisterValue` schema: added `oid` field (used for SNMP templates) and replaced the stale "Phase 3: always null" note on `value` with an accurate description pointing to `/ws/monitor` for live values
- `docs/development-phases.md`: added Milestone 8.6 (Polish & UX Fixes) and Milestone 8.7 (Consolidation, in progress) to reflect work completed since Scenario Mode shipped

## [0.3.0] - 2026-03-27

### Added
- Simulation profiles: reusable sets of simulation parameters for device templates
- Built-in "Normal Operation" profiles for all three templates (three-phase meter, single-phase meter, solar inverter)
- Automatic profile apply on device creation (default profile auto-applied unless explicitly skipped)
- CRUD API for simulation profiles (`/api/v1/simulation-profiles`)
- `profile_id` field on device creation to control which profile is applied
- Device edit UI: edit modal accessible from both device list (edit icon) and device detail page (Edit button)
- Editable fields: name, description, slave ID, port
- Slave ID and port fields are disabled when device is running (with tooltip explanation)
- Built-in template read-only view: View button (eye icon) on template list, read-only form with "Built-in" tag
- Template import error feedback: import failure now shows detailed error with expected JSON format reference
- Demo startup script (`scripts/start-demo.sh`): one-command setup with auto device creation, simulation config, and Modbus verification
- MQTT protocol adapter: publish simulated device data to external MQTT broker via `aiomqtt`
- MQTT broker settings API (`GET/PUT /api/v1/system/mqtt`) with connection test endpoint
- Per-device MQTT publish config (`GET/PUT/DELETE /api/v1/system/devices/{id}/mqtt`) with start/stop control
- MQTT topic templates with variable substitution (`{device_name}`, `{slave_id}`, `{template_name}`, `{register_name}`)
- Two payload modes: `batch` (all registers in one message) and `per_register` (one message per register)
- MQTT settings included in system export/import for cross-machine portability
- Frontend MQTT broker settings form in Settings page
- Frontend per-device MQTT publish config card in Device Detail page
- Optional mosquitto service in Docker Compose (dev-only, `docker compose --profile mqtt up`)
- Profile management UI: Profiles tab in template detail with full CRUD
- Profile config editor: per-register data mode, params, interval, enabled toggle
- Profile selector dropdown in device creation (single + batch), auto-selects default profile
- Batch device operations: Start All, Stop All, Start/Stop/Delete Selected with checkbox row selection
- Batch API endpoints: `POST /devices/batch/start`, `POST /devices/batch/stop`, `POST /devices/batch/delete`
- Profile export: download individual profiles as standalone JSON files
- Profile import: upload JSON file to create a new profile on a template
- Blank profile template download: pre-populated with all template registers as static defaults
- SNMP agent adapter: SNMPv2c command responder for simulated devices (GET/GETNEXT/WALK)
- Built-in UPS (SNMP) template with RFC 1628 UPS-MIB OIDs (10 registers)
- Built-in UPS simulation profile (Normal Operation)
- OID field on register definitions for SNMP templates
- OID column in frontend register table for SNMP protocol templates
- SNMP protocol option in template creation

### Changed
- Frontend Docker port changed from 3000 to 3002 (avoid port conflicts)
- Backend CORS updated to allow port 3002

### Fixed
- Removed unused imports in Simulation pages (AnomalyTab, index)

## [0.1.0] - 2026-03-20

First MVP release — full Modbus TCP device simulation with web UI.

### Features

#### Device Templates (Phase 2)
- Template CRUD API (`/api/v1/templates`) with register definition management
- Address overlap validation and data type constraints
- Template clone, export (JSON download), and import (JSON upload)
- 3 built-in templates: Three-Phase Meter, Single-Phase Meter, Solar Inverter
- Built-in template protection (cannot update/delete)
- Frontend: template list, create/edit form, register map table

#### Device Instances (Phase 3)
- Device CRUD API (`/api/v1/devices`) with start/stop state control
- Batch creation (up to 50 devices), slave ID uniqueness per port (1–247)
- Template deletion protection when devices reference it
- Frontend: device list with status badges, create modal (single + batch), detail page

#### Modbus TCP Protocol (Phase 4)
- Async Modbus TCP server via pymodbus (FC03 + FC04)
- Multi slave ID on single TCP port
- Datastore synced with simulation engine

#### Simulation Engine (Phase 5)
- DataGenerator: 5 modes (static, random, daily_curve, computed, accumulator)
- Safe AST-based expression parser for computed mode
- AnomalyInjector: spike, drift, flatline, out_of_range, data_loss (real-time + scheduled)
- FaultSimulator: delay, timeout, exception, intermittent communication faults
- Per-register simulation config with JSONB mode params
- Frontend: simulation config page, anomaly injection panel, fault control panel, schedule UI

#### Monitor Dashboard (Phase 6)
- WebSocket `/ws/monitor` broadcasting device state at 1Hz
- MonitorService with in-memory event log (100 events) and data aggregation
- Per-device communication statistics (request/success/error count, avg response time)
- Frontend: device card grid, register table, Recharts line chart (5-min window), stats panel, event log

#### System Finalization (Phase 7)
- System config export/import API (`/api/v1/system/export`, `/api/v1/system/import`)
- Full snapshot: templates + devices + simulation configs + anomaly schedules as portable JSON
- Import upserts by name (templates) and slave_id+port (devices), skips built-in templates
- Frontend: Settings page with export/import buttons
- CONTRIBUTING.md, Playwright smoke tests, `.dockerignore` files

### Infrastructure
- Docker Compose: PostgreSQL 16 + FastAPI backend + Nginx frontend
- Health check endpoint (`GET /health`) with DB connectivity verification
- FastAPI with async lifespan, CORS, structured logging
- SQLAlchemy 2.0 async + asyncpg + Alembic migrations
- Custom exception hierarchy (AppException, NotFoundException, ValidationException, ConflictException, ForbiddenException)
- `ApiResponse[T]` generic envelope for all API responses
- React 18 + TypeScript + Vite + Ant Design + Zustand + Recharts
- Axios API client with error interceptor
- `.env.example` with all configuration variables
