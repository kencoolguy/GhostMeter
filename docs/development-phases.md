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
- [ ] `protocols/base.py`：定義 ProtocolAdapter 抽象類
  - `async start()`
  - `async stop()`
  - `async update_register(device_id, register_name, value)`
  - `get_status() -> dict`
- [ ] Protocol manager：管理所有 adapter 的生命週期

### Milestone 4.2：Modbus TCP 實作
- [ ] `protocols/modbus_tcp.py`：基於 pymodbus async server
- [ ] 支援多 slave ID（single TCP port, multiple unit IDs）
- [ ] Datastore 與設備實例的 register 值同步
- [ ] 支援 FC03 (Read Holding Registers) + FC04 (Read Input Registers)
- [ ] Modbus server 在 FastAPI startup event 中啟動
- [ ] 整合測試：用 pymodbus client 驗證讀取值正確

---

## Phase 5：資料模擬引擎（Week 5–7）⭐ 核心

### Milestone 5.1：數據產生引擎
- [ ] `simulation/data_generator.py`：
  - Static mode：固定值
  - Random mode：base ± amplitude（uniform / gaussian）
  - Daily Curve mode：基於時間的正弦 / 自訂曲線
  - Computed mode：支援簡單公式（power = voltage × current）
  - Accumulator mode：隨時間遞增的累積值
- [ ] Generator 以 async task 運行，按設定頻率更新 register 值
- [ ] simulation_configs DB model + CRUD API

### Milestone 5.2：異常注入引擎
- [ ] `simulation/anomaly_injector.py`：
  - Spike：瞬間突刺
  - Drift：漸進飄移
  - Flatline：數值凍結
  - Out of Range：超限值
  - Data Loss：歸零或 NaN
- [ ] 異常可即時注入 / 移除（API 控制）
- [ ] 異常可設定排程（在指定時間自動觸發）

### Milestone 5.3：通訊故障模擬
- [ ] `simulation/fault_simulator.py`：
  - Delay：延遲回應 N ms
  - Timeout：完全不回應
  - Exception：回傳 Modbus exception code
  - Intermittent：按機率隨機不回應
- [ ] 故障模擬在 protocol adapter 層攔截處理
- [ ] 整合測試：驗證各種故障行為

### Milestone 5.4：模擬設定前端
- [ ] 模擬設定頁：選擇設備 → 每個 register 設定數據模式
- [ ] 異常注入控制面板：選擇異常類型 + 參數 + 即時注入按鈕
- [ ] 通訊故障控制面板
- [ ] 排程設定 UI（時間軸或簡易 cron 設定）

---

## Phase 6：即時監控 Dashboard（Week 7–8）

### Milestone 6.1：WebSocket 後端
- [ ] WebSocket endpoint `/ws/monitor`
- [ ] 定時推送（1s 間隔）：所有運行設備的 register 值
- [ ] 推送通訊統計：request count / success / error / avg response time
- [ ] 推送系統事件：設備啟停、異常注入開始/結束

### Milestone 6.2：監控前端頁面
- [ ] 設備總覽：狀態卡片牆，running（綠）/ stopped（灰）/ error（紅）
- [ ] 設備詳情 Dashboard：
  - 即時數值表格（每秒更新）
  - 關鍵 register 折線圖（最近 5 分鐘）
  - 異常注入狀態指示
- [ ] 通訊統計圖表
- [ ] 操作日誌列表（最近 100 筆）

---

## Phase 7：系統完善與發布準備（Week 8–9）

### Milestone 7.1：系統功能
- [ ] 整體設定匯入 / 匯出（所有模板 + 實例 + 模擬設定 → JSON）
- [ ] 操作日誌系統（operation_logs 表 + API）
- [ ] Dockerfile 最佳化（multi-stage build, 最小化 image size）
- [ ] docker-compose.yml 正式版（含 volume / health check / restart policy）
- [ ] .env.example 檔案

### Milestone 7.2：測試與文件
- [ ] 後端測試覆蓋率 > 70%
- [ ] 前端關鍵流程 E2E 測試
- [ ] README.md：專案介紹、快速開始、截圖
- [ ] MkDocs 文件：安裝指南、使用教學、API 參考、開發指南
- [ ] CONTRIBUTING.md
- [ ] GitHub Actions CI：lint + test + build

### Milestone 7.3：首次發布
- [ ] GitHub Release v0.1.0
- [ ] Docker Hub image publish
- [ ] 在相關社群宣傳（GitHub Topics、Reddit r/homeautomation、Python 相關）

---

## 時程總覽

| Phase | 內容 | 預估時間 | 狀態 |
|-------|------|----------|------|
| 1 | 專案骨架與基礎建設 | Week 1–2 | ✅ |
| 2 | 設備模板模組 | Week 2–3 | ✅ |
| 3 | 設備實例模組 | Week 3–4 | ✅ |
| 4 | Modbus TCP 協議引擎 | Week 4–5 | 🔲 |
| 5 | 資料模擬引擎（核心）| Week 5–7 | 🔲 |
| 6 | 即時監控 Dashboard | Week 7–8 | 🔲 |
| 7 | 系統完善與發布 | Week 8–9 | 🔲 |

**MVP 預估總時程：9 週**（以 side project 節奏，每週投入 10–15 小時估算）

---

## 開發優先級原則

1. **先通後美**：先讓 Modbus TCP 能收發正確數據，再優化 UI
2. **先核心後周邊**：模擬引擎 > 監控頁面 > 系統管理
3. **先單一後批量**：先做單台設備跑通，再做多設備併發
4. **先手動後自動**：先支援手動注入異常，再做排程自動化
