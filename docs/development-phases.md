# GhostMeter — 開發階段規劃

## Phase 1：專案骨架與基礎建設（Week 1–2）

### Milestone 1.1：專案初始化
- [x] 建立 GitHub repo，設定 .gitignore / LICENSE (MIT) / README
- [x] 建立專案目錄結構（backend / frontend / docs）
- [x] 放入 CLAUDE.md 和 PRD.md
- [x] 建立 docker-compose.yml（FastAPI + PostgreSQL + Nginx）
- [x] 確認 docker compose up 可以正常啟動所有服務

### Milestone 1.2：後端基礎
- [x] FastAPI 專案骨架 + config（pydantic-settings，從 env 讀取）
- [x] PostgreSQL 連線（SQLAlchemy 2.0 async + asyncpg）
- [x] Alembic 初始化（表結構 migration 延至 Phase 2，因為 ORM models 尚未定義）
- [x] 健康檢查 endpoint `/health`（含 DB connectivity check）
- [x] 統一錯誤處理 middleware + 自訂 exception classes
- [x] Logging 設定

### Milestone 1.3：前端基礎
- [x] Vite + React + TypeScript 專案初始化
- [x] Ant Design 5 安裝 + 基礎 layout（側邊欄導航 + 內容區）
- [x] React Router 設定（Templates / Devices / Simulation / Monitor 四個頁面骨架）
- [x] Zustand store 骨架
- [x] Axios API client 封裝（base URL 設定 + error interceptor）
- [x] 前端 Dockerfile（multi-stage build: build → nginx serve）

---

## Phase 2：設備模板模組（Week 2–3）

### Milestone 2.1：模板後端 CRUD
- [x] SQLAlchemy models：device_templates + register_definitions
- [x] Pydantic schemas：CreateTemplate / UpdateTemplate / TemplateResponse
- [x] Service layer：template_service.py
- [x] API routes：GET / POST / PUT / DELETE `/api/v1/templates`
- [x] 模板匯入匯出 API（JSON）
- [x] Seed data loader：應用啟動時載入內建模板（三相電表 / 單相電表 / 逆變器）
- [x] 單元測試：template CRUD + seed data

### Milestone 2.2：模板前端頁面
- [x] 模板列表頁：表格顯示所有模板 + 新增 / 編輯 / 刪除按鈕
- [x] 模板編輯頁：基本資訊 form + register map 可編輯表格
- [x] Register map 表格：支援新增 / 刪除 / 拖曳排序 register
- [x] JSON 匯入 / 匯出功能（上傳檔案 + 下載檔案）
- [x] 內建模板標示「系統內建」badge，禁止刪除

---

## Phase 3：設備實例模組（Week 3–4）

### Milestone 3.1：設備後端 CRUD
- [x] SQLAlchemy model：device_instances
- [x] Pydantic schemas：CreateDevice / DeviceResponse
- [x] Service layer：device_service.py
- [x] API routes：CRUD + `/start` / `/stop` + `/registers`
- [x] 批量建立 API（指定 slave ID 範圍）
- [x] Slave ID 唯一性驗證（同 port 下不可重複）
- [x] 單元測試

### Milestone 3.2：設備前端頁面
- [x] 設備列表頁：狀態卡片或表格，顯示 slave ID / 模板名 / 狀態
- [x] 建立設備 modal：選模板 → 填 slave ID（支援批量）
- [x] 設備啟停控制按鈕（即時狀態更新）
- [x] 設備詳情頁：顯示所有 register 當前值

---

## Phase 4：Modbus TCP 協議引擎（Week 4–5）

### Milestone 4.1：Protocol Adapter 架構
- [x] `protocols/base.py`：定義 ProtocolAdapter 抽象類
  - `async start()`
  - `async stop()`
  - `async update_register(device_id, register_name, value)`
  - `get_status() -> dict`
- [x] Protocol manager：管理所有 adapter 的生命週期

### Milestone 4.2：Modbus TCP 實作
- [x] `protocols/modbus_tcp.py`：基於 pymodbus async server
- [x] 支援多 slave ID（single TCP port, multiple unit IDs）
- [x] Datastore 與設備實例的 register 值同步
- [x] 支援 FC03 (Read Holding Registers) + FC04 (Read Input Registers)
- [x] Modbus server 在 FastAPI startup event 中啟動
- [x] 整合測試：用 pymodbus client 驗證讀取值正確

---

## Phase 5：資料模擬引擎（Week 5–7）⭐ 核心

### Milestone 5.1：數據產生引擎
- [x] `simulation/data_generator.py`：
  - Static mode：固定值
  - Random mode：base ± amplitude（uniform / gaussian）
  - Daily Curve mode：基於時間的正弦 / 自訂曲線
  - Computed mode：支援簡單公式（power = voltage × current）
  - Accumulator mode：隨時間遞增的累積值
- [x] Generator 以 async task 運行，按設定頻率更新 register 值
- [x] simulation_configs DB model + CRUD API

### Milestone 5.2：異常注入引擎
- [x] `simulation/anomaly_injector.py`：
  - Spike：瞬間突刺
  - Drift：漸進飄移
  - Flatline：數值凍結
  - Out of Range：超限值
  - Data Loss：歸零或 NaN
- [x] 異常可即時注入 / 移除（API 控制）
- [x] 異常可設定排程（在指定時間自動觸發）

### Milestone 5.3：通訊故障模擬
- [x] `simulation/fault_simulator.py`：
  - Delay：延遲回應 N ms
  - Timeout：完全不回應
  - Exception：回傳 Modbus exception code
  - Intermittent：按機率隨機不回應
- [x] 故障模擬在 protocol adapter 層攔截處理
- [x] 整合測試：驗證各種故障行為

### Milestone 5.4：模擬設定前端
- [x] 模擬設定頁：選擇設備 → 每個 register 設定數據模式
- [x] 異常注入控制面板：選擇異常類型 + 參數 + 即時注入按鈕
- [x] 通訊故障控制面板
- [x] 排程設定 UI

---

## Phase 6：即時監控 Dashboard（Week 7–8）

### Milestone 6.1：WebSocket 後端
- [x] WebSocket endpoint `/ws/monitor`
- [x] 定時推送（1s 間隔）：所有運行設備的 register 值
- [x] 推送通訊統計：request count / success / error / avg response time
- [x] 推送系統事件：設備啟停、異常注入開始/結束

### Milestone 6.2：監控前端頁面
- [x] 設備總覽：狀態卡片牆，running（綠）/ stopped（灰）/ error（紅）
- [x] 設備詳情 Dashboard：
  - 即時數值表格（每秒更新）
  - 關鍵 register 折線圖（最近 5 分鐘）
  - 異常注入狀態指示
- [x] 通訊統計圖表
- [x] 操作日誌列表（最近 100 筆）

---

## Phase 7：系統完善與發布準備（Week 8–9）

### Milestone 7.1：系統功能
- [x] 整體設定匯入 / 匯出（所有模板 + 實例 + 模擬設定 → JSON）
- [x] 操作日誌系統（Phase 6 MonitorService 已包含 in-memory event log）
- [x] Dockerfile 最佳化（.dockerignore 減少 build context）
- [x] docker-compose.yml 正式版（含 volume / health check / restart policy）
- [x] .env.example 檔案

### Milestone 7.2：測試與文件
- [x] 後端測試覆蓋率 > 70%（229 tests）
- [x] 前端關鍵流程 E2E 測試（Playwright smoke tests）
- [x] README.md：專案介紹、快速開始、截圖
- [ ] MkDocs 文件：安裝指南、使用教學、API 參考、開發指南（deferred）
- [x] CONTRIBUTING.md
- [x] GitHub Actions CI：lint + test + build

### Milestone 7.3：首次發布
- [ ] GitHub Release v0.1.0（待 PR merge 後 tag）
- [ ] Docker Hub image publish（deferred）
- [ ] 在相關社群宣傳（deferred）

### Milestone 7.4：正式部署工具 ✅ Complete (2026-06-10)
- [x] `docker-compose.prod.yml`：port 綁定 `BIND_IP`、postgres 不對外（exposed host 安全部署）
- [x] `deploy.sh`：套用 prod overlay + migration + 啟動 一鍵腳本
- [x] `docs/deployment.md`：Linode（Tailscale + Cloudflare Tunnel）部署指南

---

## Phase 8：Post-MVP 功能擴充

### Milestone 8.1：Simulation Profiles
- [x] `simulation_profiles` DB table + ORM model + migration
- [x] Pydantic schemas（Create / Update / Response / ProfileConfigEntry）
- [x] Profile CRUD service + API routes (`/api/v1/simulation-profiles`)
- [x] Device creation auto-apply: `profile_id` field in DeviceCreate / DeviceBatchCreate
- [x] Built-in seed profiles for all 3 templates (physically consistent data)
- [x] Seed loader: `seed_builtin_profiles()` called at app startup
- [x] 22 integration tests (CRUD, auto-apply, seed, protection)

### Milestone 8.2：MQTT Adapter ✅
- [x] MQTT protocol adapter (`MqttAdapter` extending `ProtocolAdapter`)
- [x] DB models + migration: `mqtt_broker_settings`, `mqtt_publish_configs`
- [x] MQTT service layer + API routes (broker CRUD, publish config CRUD, start/stop, test)
- [x] Frontend UI: broker settings in Settings page, publish config in Device Detail
- [x] System export/import integration (broker settings + publish configs)
- [x] Docker Compose mosquitto service (dev-only, `--profile mqtt`)
- [x] 30 integration tests (MQTT CRUD, adapter, export/import)

### Milestone 8.3：Frontend Profile Selector (#13) ✅
- [x] Profile selector dropdown in device creation UI (single + batch)
- [x] Profile management page (Profiles tab in template detail)
- [x] ProfileFormModal with per-register config editor
- [x] Profile Zustand store + API client

### Milestone 8.4：SNMP Agent Adapter ✅
- [x] SnmpAdapter extending ProtocolAdapter (SNMPv2c agent, pysnmp v7)
- [x] OID column on register_definitions + migration
- [x] UPS (SNMP) seed template (RFC 1628 UPS-MIB) + Normal Operation profile
- [x] Frontend OID column and SNMP protocol option in template creation
- [x] OID conflict detection for same-template devices
- [x] 16 integration tests (template CRUD, adapter unit, seed validation)

### Milestone 8.5：Scenario Mode ✅
- [x] `scenarios` + `scenario_steps` DB tables + Alembic migration
- [x] Pydantic schemas (Create / Update / Summary / Detail / StepCreate / Export / ExecutionStatus)
- [x] Scenario CRUD service + API routes (`/api/v1/scenarios`)
- [x] ScenarioRunner: async executor with timeline-based anomaly injection/clear
- [x] Execution API: start/stop/status per device (`/api/v1/devices/{id}/scenario/...`)
- [x] Built-in seed scenarios: Power Outage Recovery, Voltage Instability, Inverter Fault Sequence
- [x] Frontend types, API client (`scenarioApi.ts`), Zustand store (`scenarioStore.ts`)
- [x] ScenarioList page with template filter, CRUD actions, clone, export/import
- [x] TimelineEditor: visual drag-and-drop anomaly blocks on register×time grid
- [x] ScenarioExecutionCard on Device Detail: start/stop with real-time progress polling
- [x] 19 integration tests (CRUD, seed, built-in protection, export/import)

### Milestone 8.6：Polish & UX Fixes ✅
- [x] Auto-resume: running devices restored after backend restart (re-registers protocol adapters + restarts simulation engine)
- [x] Device Detail live values via `/ws/monitor` WebSocket (closes #19)
- [x] Device Detail "Open in Monitor" button with `?device=<id>` deep link
- [x] Monitor page `?device=` query param auto-selects device on mount
- [x] Anomaly injection panel: replaced raw JSON textarea with dynamic per-type param form
- [x] Batch device name prefix spacing fix

### Milestone 8.8：Monitor Redesign — Glance Dashboard (issue #29) ✅ Complete (2026-04-17)
- [x] Monitor redesigned as glance dashboard: KPI panel, mid-density card grid, sparklines, value-flash animation, status dot pulse
- [x] `/monitor` set as home route (`/` redirects to `/monitor`); Monitor moved to top of sidebar
- [x] Stopped devices surfaced in grid (faded + Start shortcut); guided empty state when no devices exist
- [x] Backend: include stopped devices in monitor snapshot; expose `mqtt_broker_connected`; per-device `template_name`
- [x] Event toast notifications (3s auto-dismiss) + Drawer for accumulated history
- [x] Refactor: shared `pickPrimary` helper module; `ProtocolManager.get_adapter` returns Optional with None checks at all call sites
- [x] Removed DeviceDetailPanel, RegisterChart, StatsPanel, EventLog from Monitor page

### Milestone 8.9：OPC UA Server Adapter ✅ Merged (2026-06-03, PR #33)
- [x] OpcUaAdapter extending ProtocolAdapter (asyncua, single shared server, Anonymous/None)
- [x] Push value-sync: simulation engine update_register → variable node; subscriptions fire automatically
- [x] RegisterInfo extended with name/unit; device name via set_device_meta pre-add hook
- [x] Built-in "Energy Meter (OPC UA)" template (11 registers) + Normal Operation profile
- [x] Frontend OPC UA protocol option; docker-compose port 4840
- [x] Integration tests: server lifecycle, node CRUD, typed value round-trip, subscription, device wiring
- [x] Post-review hardening: out-of-range value clamping, unique `(#slave_id)` node names, `_device_meta` cleanup
- [x] Merged to `dev` via PR #33; follow-up PR #34 pinned `pymodbus<3.13`

### Milestone 8.10：OPC UA Comm-layer Fault Simulation ✅ Complete (2026-06-03)
- [x] `ProtocolAdapter` base gains no-op `apply_fault(device_id)` / `remove_fault(device_id)` hooks; Modbus inherits unchanged (pull-based via trace_pdu)
- [x] `OpcUaAdapter` overrides hooks: `apply_fault` attaches per-node asyncua value callbacks (`set_attribute_value_callback`); `remove_fault` detaches by re-writing cached value (restores stored value, clears callback, resumes subscriptions atomically)
- [x] Per-node last-value cache (`_last_values`); `update_register` skips `write_value` while device is in `_faulted` set
- [x] Fault-type mapping: `exception` → `BadDeviceFailure`, `timeout` → `BadTimeout`, `delay` → bounded server-side `time.sleep` (cap 10 s) + cached value, `intermittent` → random `BadCommunicationError` by `failure_rate`
- [x] Callback reads `fault_simulator` live on every client read (single source of truth; same model as Modbus trace_pdu)
- [x] Auto-reattach on `add_device` if a fault is already active (parity with Modbus surviving stop/start)
- [x] REST `PUT/DELETE /devices/{id}/fault` wired to adapter hook via `get_device_protocol` DB lookup
- [x] 13 new tests: adapter-level fault tests (exception/timeout/delay/intermittent/cache/subscription restore) + REST e2e round-trip
- **Note:** SNMP/MQTT adapters could reuse the same base hook pattern in the future (out of scope here; their fault semantics differ significantly)

### Milestone 8.7：Consolidation (in progress 🔄)
- [x] Remove VirtualBox shared-folder path hacks from `frontend/package.json` + tsconfigs + `.npmrc`
- [x] Restore `.github/workflows/ci.yml` (was removed in 6d92a2c pending workflow-scope token)
- [x] API reference drift fix: document 18 previously undocumented endpoints (anomaly, simulation config, fault, simulation-profile import/export/blank)
- [x] `RegisterValue` schema: document `oid` field and update stale `value` description
- [ ] Push feature branch and verify CI pipeline runs green
- [ ] Backend test health check (`pytest` full run, confirm no skipped/flaky tests)
- [ ] Cut release (resolve README 0.3.0 vs. current unreleased feature gap)
- [ ] Address issues surfaced during audit: #21 (Cloudflare Pages build config), #22 (npm audit vulnerabilities), #23 (frontend bundle >500KB)

---

## 時程總覽

| Phase | 內容 | 預估時間 | 狀態 |
|-------|------|----------|------|
| 1 | 專案骨架與基礎建設 | Week 1–2 | ✅ |
| 2 | 設備模板模組 | Week 2–3 | ✅ |
| 3 | 設備實例模組 | Week 3–4 | ✅ |
| 4 | Modbus TCP 協議引擎 | Week 4–5 | ✅ |
| 5 | 資料模擬引擎（核心）| Week 5–7 | ✅ |
| 6 | 即時監控 Dashboard | Week 7–8 | ✅ |
| 7 | 系統完善與發布 | Week 8–9 | ✅ |
| 8 | Post-MVP 功能擴充 | Week 9+ | 🔄 |

**MVP 預估總時程：9 週**（以 side project 節奏，每週投入 10–15 小時估算）

---

## 開發優先級原則

1. **先通後美**：先讓 Modbus TCP 能收發正確數據，再優化 UI
2. **先核心後周邊**：模擬引擎 > 監控頁面 > 系統管理
3. **先單一後批量**：先做單台設備跑通，再做多設備併發
4. **先手動後自動**：先支援手動注入異常，再做排程自動化
