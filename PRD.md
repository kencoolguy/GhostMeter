# GhostMeter — Product Requirements Document

**專案代號**：GhostMeter  
**版本**：v0.1  
**日期**：2026-02-26  
**作者**：Ken  

---

## 1. 產品願景

### 1.1 一句話定位

> 專為能源管理系統開發者打造的多協議設備模擬器，內建真實設備模板和智能異常注入引擎。

### 1.2 解決的問題

能源管理系統（如 BEMS / EMS）的開發者在開發 data collector 時，面臨以下痛點：

- **無設備可測**：開發環境沒有實體電表、逆變器，需要真實設備才能驗證採集邏輯
- **異常難重現**：設備故障、通訊中斷、數據飄移等異常場景無法在真實設備上重現
- **規模難模擬**：測試大量設備併發場景需要大量硬體投入
- **LLM 告警訓練缺數據**：AI 驅動的告警分析系統需要大量的故障 pattern 數據來訓練和驗證

### 1.3 目標用戶

- 能源管理系統開發者（主要目標）
- SCADA / BMS / IoT 平台開發者
- 系統整合商和測試工程師
- 能源領域研究人員和學生

### 1.4 競品分析

| 能力 | pymodbus sim | ModbusTools | cybcon/modbus-server | **GhostMeter** |
|------|:-:|:-:|:-:|:-:|
| Web UI 設定管理 | 基本 | ❌ (桌面) | ❌ | ✅ |
| 能源設備模板（電表/逆變器）| ❌ | ❌ | ❌ | ✅ |
| 真實數據曲線模擬 | ❌ | ❌ | ❌ | ✅ |
| 異常/故障注入 | 很弱 | ❌ | ❌ | ✅ |
| 通訊故障模擬 | ❌ | ❌ | ❌ | ✅ |
| 多設備併發 | ✅ | ✅ | ✅ | ✅ |
| Docker 一鍵部署 | ❌ | ❌ | ✅ | ✅ |
| 多協議擴展 | ❌ | ❌ | ❌ | ✅ |
| 活躍維護 | ✅ | ✅ | ✅ | ✅ |

**核心差異化**：能源領域專屬 + 異常注入引擎 + 現代 Web UI + 多協議擴展路線

---

## 2. 核心概念模型

三層結構：**設備模板 → 設備實例 → 模擬情境**

```
┌─────────────────────────────────────────┐
│           Device Template               │
│  定義設備 register map + 資料型態          │
│  例：三相電表、單相電表、逆變器             │
└──────────────┬──────────────────────────┘
               │ instantiate
               ▼
┌─────────────────────────────────────────┐
│           Device Instance               │
│  綁定 Slave ID，獨立狀態                  │
│  從模板建立，可多個實例                    │
└──────────────┬──────────────────────────┘
               │ apply
               ▼
┌─────────────────────────────────────────┐
│         Simulation Profile              │
│  控制數據產生方式 + 異常注入               │
│  可套用到單一或多個實例                    │
└─────────────────────────────────────────┘
```

---

## 3. 技術架構

### 3.1 技術棧

| 層級 | 技術 | 理由 |
|------|------|------|
| 後端框架 | FastAPI (async) | 高效能、自帶 OpenAPI 文件、async 天然適合多協議併發 |
| 協議模擬 | pymodbus (async) | Python Modbus 生態最成熟，活躍維護 |
| 設備模型 | Pydantic v2 | 驗證 + 序列化，與 FastAPI 無縫整合 |
| 資料庫 | PostgreSQL | 儲存模板、實例、設定、日誌 |
| ORM | SQLAlchemy 2.0 + asyncpg | Async 支援，與 FastAPI 搭配良好 |
| DB Migration | Alembic | SQLAlchemy 標準遷移工具 |
| 前端框架 | React 18 + TypeScript | 主流、生態豐富 |
| 前端建置 | Vite | 快速建置、HMR |
| UI 組件庫 | Ant Design 5 | 企業級組件、中文支援好、表單/表格功能完整 |
| 狀態管理 | Zustand | 輕量、直覺，適合中型工具 |
| 前後端通訊 | REST API + WebSocket | REST 做 CRUD，WebSocket 推即時模擬狀態 |
| 部署 | Docker Compose | 一鍵啟動前後端 + DB |
| 文件 | MkDocs (Material) | 開源社群主流 |

### 3.2 專案結構

```
ghostmeter/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口
│   │   ├── config.py               # 應用設定
│   │   ├── database.py             # DB 連線 & session
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── templates.py    # 設備模板 CRUD
│   │   │   │   ├── devices.py      # 設備實例管理
│   │   │   │   ├── simulations.py  # 模擬控制
│   │   │   │   └── system.py       # 系統狀態 & 設定
│   │   │   └── websocket.py        # WebSocket 即時推送
│   │   ├── models/                 # SQLAlchemy models
│   │   │   ├── template.py
│   │   │   ├── device.py
│   │   │   └── simulation.py
│   │   ├── schemas/                # Pydantic schemas
│   │   │   ├── template.py
│   │   │   ├── device.py
│   │   │   └── simulation.py
│   │   ├── services/               # 業務邏輯
│   │   │   ├── template_service.py
│   │   │   ├── device_service.py
│   │   │   └── simulation_engine.py
│   │   ├── protocols/              # 協議引擎（可插拔）
│   │   │   ├── base.py             # 抽象協議介面
│   │   │   ├── modbus_tcp.py       # Modbus TCP 實作
│   │   │   └── (mqtt.py)           # 未來擴展
│   │   ├── simulation/             # 模擬核心
│   │   │   ├── data_generator.py   # 數據產生引擎
│   │   │   ├── anomaly_injector.py # 異常注入引擎
│   │   │   └── fault_simulator.py  # 通訊故障模擬
│   │   └── seed/                   # 內建模板種子資料
│   │       ├── three_phase_meter.json
│   │       ├── single_phase_meter.json
│   │       └── solar_inverter.json
│   ├── alembic/                    # DB migration
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Templates/          # 模板管理頁
│   │   │   ├── Devices/            # 設備實例頁
│   │   │   ├── Simulation/         # 模擬控制頁
│   │   │   └── Monitor/            # 即時監控 Dashboard
│   │   ├── components/
│   │   ├── stores/                 # Zustand stores
│   │   ├── services/               # API client
│   │   └── types/                  # TypeScript 型別
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── docker-compose.yml
├── docs/                           # MkDocs 文件
├── CLAUDE.md
├── README.md
├── LICENSE                         # MIT
└── .github/
    └── workflows/
        └── ci.yml
```

---

## 4. 功能需求（MVP — Modbus TCP）

### 4.1 設備模板管理

#### 4.1.1 內建模板

專案啟動時自動 seed 以下模板：

**三相電表 (Three-Phase Meter)**

| Register | Address | Data Type | Scale | Unit | Description |
|----------|---------|-----------|-------|------|-------------|
| voltage_a | 30001 | float32 | 0.1 | V | A 相電壓 |
| voltage_b | 30003 | float32 | 0.1 | V | B 相電壓 |
| voltage_c | 30005 | float32 | 0.1 | V | C 相電壓 |
| current_a | 30007 | float32 | 0.01 | A | A 相電流 |
| current_b | 30009 | float32 | 0.01 | A | B 相電流 |
| current_c | 30011 | float32 | 0.01 | A | C 相電流 |
| power_total | 30013 | float32 | 1 | W | 總有功功率 |
| power_factor | 30015 | float32 | 0.001 | - | 功率因數 |
| frequency | 30017 | float32 | 0.01 | Hz | 頻率 |
| energy_total | 30019 | uint32 | 0.01 | kWh | 累積用電量 |

**單相電表 (Single-Phase Meter)** — 簡化版

**太陽能逆變器 (Solar Inverter)** — 含 DC 側 + AC 側 + 發電量

#### 4.1.2 自訂模板

- 使用者可建立自訂模板，定義任意 register map
- 支援的 data type：int16 / uint16 / int32 / uint32 / float32
- 支援的 byte order：AB CD (Big-Endian) / CD AB (Little-Endian Word Swap) / BA DC / DC BA
- 支援 function code：FC03 (Holding Register) / FC04 (Input Register)
- 每個 register 可設定：address、data type、byte order、scale factor、unit、description
- 模板匯入 / 匯出（JSON 格式）

### 4.2 設備實例管理

- 從模板建立實例，指定 Slave ID（1–247）
- 支援同時運行多台設備（MVP：單一 TCP port，多 slave ID）
- 每台設備獨立啟停控制
- 批量建立（例：從同一模板建立 slave ID 1–10 共 10 台設備）
- 即時查看每台設備當前所有 register 值

### 4.3 資料模擬引擎

#### 4.3.1 正常數據模式

| 模式 | 說明 | 參數 |
|------|------|------|
| 固定值 (Static) | 回傳固定數值 | value |
| 隨機波動 (Random) | 基準值 ± 隨機範圍 | base_value, amplitude, interval_ms |
| 日週期曲線 (Daily Curve) | 模擬 24hr 用電/發電 pattern | peak_value, valley_value, peak_hour, curve_type |
| 關聯計算 (Computed) | 從其他 register 計算 | formula（如 `power = voltage * current`） |
| 累積遞增 (Accumulator) | 模擬電度表累加 | increment_per_second |

#### 4.3.2 異常注入

| 類型 | 說明 | 參數 |
|------|------|------|
| 數值突刺 (Spike) | 瞬間飆高或掉低 | spike_value, duration_ms, interval_ms |
| 漸進飄移 (Drift) | 數值慢慢偏離 | drift_rate, direction, max_offset |
| 數值凍結 (Flatline) | 數值卡住不動 | freeze_duration_s |
| 超限值 (Out of Range) | 持續輸出超出合理範圍 | out_value |
| 數據遺失 (Data Loss) | 回傳 0 或 NaN | loss_probability |

#### 4.3.3 通訊故障模擬

| 類型 | 說明 | 參數 |
|------|------|------|
| 延遲回應 (Delay) | 模擬網路延遲 | delay_ms |
| 不回應 (Timeout) | 完全不回應 | - |
| 異常回應碼 (Exception) | 回傳 Modbus exception | exception_code (ILLEGAL_ADDRESS / DEVICE_BUSY / ...) |
| 間歇斷線 (Intermittent) | 隨機機率不回應 | failure_probability |

### 4.4 Web UI

#### 4.4.1 設定頁面

- **模板管理**：CRUD + register map 視覺化表格編輯器 + JSON 匯入匯出
- **實例管理**：從模板建立、批量建立、啟停控制
- **模擬設定**：每台設備的每個 register 可獨立設定數據模式 + 異常注入
- **排程控制**：設定異常注入的觸發時間（例：14:00 開始注入 spike）

#### 4.4.2 監控頁面

- **設備總覽**：所有運行中設備的狀態卡片（running / stopped / error）
- **設備詳情**：單台設備的即時數據表格 + 關鍵數值折線圖
- **通訊統計**：請求數、成功回應數、錯誤數、平均回應時間
- **操作日誌**：誰在什麼時候做了什麼操作

### 4.5 系統功能

- **Modbus TCP Server**：監聽指定 port（預設 502），支援多 slave ID
- **設定持久化**：所有設定存 PostgreSQL
- **整體匯入匯出**：一鍵備份還原所有模板 + 實例 + 情境（JSON）
- **Docker Compose 部署**：前端 + 後端 + PostgreSQL 一鍵啟動
- **API 文件**：FastAPI 自動生成 OpenAPI / Swagger UI
- **健康檢查**：`/health` endpoint

---

## 5. API 設計概要

### 5.1 REST API

```
# 設備模板
GET    /api/v1/templates              # 列出所有模板
POST   /api/v1/templates              # 建立模板
GET    /api/v1/templates/{id}         # 取得模板詳情
PUT    /api/v1/templates/{id}         # 更新模板
DELETE /api/v1/templates/{id}         # 刪除模板
POST   /api/v1/templates/import       # 匯入模板 JSON
GET    /api/v1/templates/{id}/export  # 匯出模板 JSON

# 設備實例
GET    /api/v1/devices                # 列出所有實例
POST   /api/v1/devices                # 建立實例（含批量）
GET    /api/v1/devices/{id}           # 取得實例詳情
PUT    /api/v1/devices/{id}           # 更新實例
DELETE /api/v1/devices/{id}           # 刪除實例
POST   /api/v1/devices/{id}/start     # 啟動設備
POST   /api/v1/devices/{id}/stop      # 停止設備
GET    /api/v1/devices/{id}/registers # 取得目前 register 值

# 模擬控制
GET    /api/v1/simulations                        # 列出所有模擬設定
PUT    /api/v1/devices/{id}/simulation             # 設定設備模擬參數
POST   /api/v1/devices/{id}/simulation/anomaly     # 注入異常
DELETE /api/v1/devices/{id}/simulation/anomaly     # 停止異常注入
POST   /api/v1/devices/{id}/simulation/fault       # 啟動通訊故障
DELETE /api/v1/devices/{id}/simulation/fault       # 停止通訊故障

# 系統
GET    /api/v1/system/status          # 系統狀態（運行中設備數、CPU、記憶體）
POST   /api/v1/system/export          # 匯出所有設定
POST   /api/v1/system/import          # 匯入所有設定
GET    /health                        # 健康檢查
```

### 5.2 WebSocket

```
WS /ws/monitor
  → 推送即時數據：每台設備的 register 值更新
  → 推送通訊統計：請求/回應/錯誤計數
  → 推送系統事件：設備啟停、異常注入開始/結束
```

---

## 6. 資料庫設計概要

### 6.1 主要表

```
device_templates
├── id (UUID, PK)
├── name (VARCHAR)
├── type (ENUM: meter_3p, meter_1p, inverter, custom)
├── description (TEXT)
├── is_builtin (BOOLEAN)
├── created_at (TIMESTAMP)
└── updated_at (TIMESTAMP)

register_definitions
├── id (UUID, PK)
├── template_id (UUID, FK → device_templates)
├── name (VARCHAR)                    # e.g. "voltage_a"
├── address (INTEGER)                 # Modbus register address
├── function_code (ENUM: FC03, FC04)
├── data_type (ENUM: int16, uint16, int32, uint32, float32)
├── byte_order (ENUM: AB_CD, CD_AB, BA_DC, DC_BA)
├── scale_factor (FLOAT)
├── unit (VARCHAR)
├── description (TEXT)
└── sort_order (INTEGER)

device_instances
├── id (UUID, PK)
├── template_id (UUID, FK → device_templates)
├── name (VARCHAR)
├── slave_id (INTEGER, 1-247)
├── status (ENUM: stopped, running, error)
├── created_at (TIMESTAMP)
└── updated_at (TIMESTAMP)

simulation_configs
├── id (UUID, PK)
├── device_id (UUID, FK → device_instances)
├── register_def_id (UUID, FK → register_definitions)
├── data_mode (ENUM: static, random, daily_curve, computed, accumulator)
├── mode_params (JSONB)               # 各模式的參數
├── anomaly_type (ENUM: none, spike, drift, flatline, out_of_range, data_loss, NULLABLE)
├── anomaly_params (JSONB, NULLABLE)
├── fault_type (ENUM: none, delay, timeout, exception, intermittent, NULLABLE)
├── fault_params (JSONB, NULLABLE)
└── updated_at (TIMESTAMP)

operation_logs
├── id (UUID, PK)
├── action (VARCHAR)
├── target_type (VARCHAR)
├── target_id (UUID)
├── detail (JSONB)
└── created_at (TIMESTAMP)
```

---

## 7. 未來迭代路線圖

### Phase 2: 多協議擴展
- MQTT publisher（JSON payload to configurable topics）
- SNMP agent（模擬 OID tree）
- BACnet/IP device（模擬 BACnet objects）

### Phase 3: 進階功能
- Modbus RTU over TCP（serial gateway 模擬）
- 設備群組和場景編排（一鍵切換「正常」→「故障模式」）
- 歷史數據錄製回放（錄真實設備數據後回放）
- REST API 外部控制（CI/CD 整合自動化測試）

### Phase 4: 生態整合
- 多語系（中/英）
- Plugin 機制（社群自定義協議）
- Grafana Dashboard 模板
- Prometheus metrics exporter

---

## 8. 非功能需求

- **效能**：單節點支援同時模擬 100+ 台設備
- **延遲**：Modbus 回應延遲 < 50ms（不含刻意注入的延遲）
- **部署**：Docker Compose 一鍵部署，5 分鐘內完成
- **瀏覽器**：支援 Chrome / Edge / Firefox 最新版
- **授權**：MIT License
