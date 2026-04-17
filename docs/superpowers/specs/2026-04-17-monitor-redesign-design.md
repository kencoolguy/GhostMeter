# Monitor 首頁重做 — Design Spec

**Issue:** #29 (UI #2: Monitor 頁重做並設為首頁)
**Date:** 2026-04-17
**Status:** Approved (pending implementation)

---

## 1. Goal

把 `/monitor` 升級為 GhostMeter 的視覺焦點頁面與全站首頁，取代目前的 `/templates`。

頁面定位：**glance dashboard**。使用者進來一眼掌握「整個系統現在健不健康」，看到異常才點進細節頁深查。

---

## 2. Scope

### In scope
- `/` route 改導向 `/monitor`
- 側邊欄 Monitor 移到第一個位置
- KPI 頂部區（4 主 + 條件式 pills）
- 設備卡片網格（mid 密度，主指標大字 + sparkline + 副指標）
- 卡片點擊行為改為跳轉 `/devices/{id}`（**移除目前同頁展開的 detail panel**）
- Stopped 設備也顯示在網格（淡化 + Start 快捷）
- 完全沒設備時的引導空狀態（內建模板捷徑 + CTA）
- 即時值更新動畫（cyan glow flash）
- 狀態燈動畫（running 呼吸 / error 閃爍）
- 卡片 hover 動效（上浮 + 邊框光暈）
- Event Log 改為右上角 toast + 抽屜（取代目前的底部 collapse）
- 後端 monitor service：擴充推送 stopped 設備（保留 status 欄位區分）

### Out of scope
- 不改 WebSocket 協定（沿用現有 message shape，僅擴充欄位）
- 不改 Device Detail 頁
- 不引入新的圖表/UI library
- `is_primary` register 機制不做（先寫死：`total_power` → `total_energy` → 第一個 register）
- 不做卡片過濾/排序（後續 issue）

---

## 3. Architecture

### Routing
- `App.tsx`: `/` route 由 `Navigate to="/templates"` 改成 `Navigate to="/monitor"`
- `MainLayout.tsx`: `menuItems` 把 Monitor 移到陣列第一個

### Frontend page structure (`pages/Monitor/`)

```
pages/Monitor/
├── index.tsx              # 主頁，組裝以下子元件 + WebSocket
├── KpiPanel.tsx           # 頂部 4 主 KPI + 條件式 pills（NEW）
├── DeviceCardGrid.tsx     # 卡片網格（已存在，需改寫）
├── DeviceCard.tsx         # 單張卡片（已存在，需改寫）
├── EmptyState.tsx         # 完全沒設備時的引導畫面（NEW）
├── EventToast.tsx         # 新事件浮窗（NEW）
├── EventDrawer.tsx        # 抽屜事件歷史（NEW）
└── Sparkline.tsx          # 卡片內小折線圖（NEW，包 recharts ResponsiveContainer）

# 移除：
# - DeviceDetailPanel.tsx  (跳頁取代同頁展開)
# - RegisterChart.tsx       (Detail panel 用，移除)
# - StatsPanel.tsx          (Detail panel 用，移除)
```

### Frontend state (`stores/monitorStore.ts`)
- 沿用現有 `devices` / `events` / `registerHistory`
- 新增 `eventDrawerOpen: boolean`、`toggleEventDrawer()`
- 新增 `recentToastEvent: MonitorEvent | null`、`dismissToast()`
- **移除** `selectedDeviceId`、`selectDevice` (不再需要選中)

### Backend changes
- `monitor_service.py`：移除 `where(DeviceInstance.status != "stopped")` filter，stopped 設備也納入推送
- `MonitorService` 計算與推送新欄位：
  - `mqtt_broker_connected: bool`（從 mqtt_service 取連線狀態）
- `WebSocket monitor_update` payload 結構不變，僅每個 device 多一個 `mqtt_stats`（已存在）；新增 top-level `mqtt_broker_connected`

### Type changes (`types/monitor.ts`)
```ts
// 擴充
export interface DeviceMonitorData {
  // ...existing fields
  mqtt_stats: CommunicationStats | null;  // 已存在後端，前端型別補上
}

export interface MonitorUpdate {
  // ...existing fields
  mqtt_broker_connected: boolean;  // NEW
}
```

---

## 4. Component Specs

### 4.1 KpiPanel
**Props:** `devices: DeviceMonitorData[]`, `mqttBrokerConnected: boolean`

**Computed:**
- `running = devices.filter(d => d.status === 'running').length`
- `stopped = devices.filter(d => d.status === 'stopped').length`
- `errors = devices.filter(d => d.status === 'error').length`
- `dps = running 設備的 register 數總和`（公式：`sum(d.registers.length for d if d.status === 'running') × push_freq_hz`，目前 push_freq_hz=1，所以等同 register 總數）
- `activeAnomalies = sum(devices.map(d => d.active_anomalies.length))`
- `activeFaults = devices.filter(d => d.active_fault !== null).length`

**Layout:**
- Row 1：4 KPI tile（grid-cols-4）— 永遠顯示
- Row 2：pills 列 — `activeAnomalies > 0` 顯示橘 pill；`activeFaults > 0` 顯示紅 pill；MQTT 連線狀態永遠顯示一個 pill（綠/灰）

### 4.2 DeviceCard
**Props:** `device: DeviceMonitorData`

**Behavior:**
- `onClick` → `navigate('/devices/' + device.device_id)`
- 滑鼠右上角 `→` arrow 提示
- `device.status === 'stopped'` → opacity 0.45 + 顯示 `▶ Start` link（點擊呼叫 `POST /api/v1/devices/{id}/start`，**event 阻擋冒泡避免觸發跳頁**）
- `device.status === 'error'` → 紅色邊框

**Layout (mid density):**
- Header: 狀態燈 + name + slave_id
- Sub: template name (如 "SDM630")
- Primary register: name (uppercase) + 大字數值（18px JetBrains Mono）+ unit
- Sparkline: 36px 高，主 register 的 history（取 monitorStore.registerHistory）
- Secondary register: 小字 row（10–11px）
- Tags: MQTT 狀態（依 `device.mqtt_stats`：null=不顯示、有資料且 error_count=0=綠色 "MQTT"、有 error=橘色 "MQTT err"）、active anomalies（橘 tag, anomaly type 名稱）、active fault（紅 tag, fault_type 名稱）

**Primary/secondary register 選擇（寫死）:**
```ts
const PREFERRED = ['total_power', 'ac_power', 'total_energy'];
const primary = PREFERRED.find(n => regs.has(n)) ?? regs[0];
const secondary = PREFERRED.find(n => regs.has(n) && n !== primary) ?? regs[1];
```

**Animations:**
- `.dot.run` — 2s ease-in-out infinite breath（opacity 0.4 ↔ 1 + box-shadow glow）
- `.dot.err` — 0.8s ease-in-out infinite blink
- `.dot.stopped` — 無動畫
- 數值更新：偵測 value 變動 → 套用 `valueFlash` class 0.5s（cyan glow + light cyan color → fade 回 cyan）
- Card hover：`translateY(-2px)` + cyan border + box-shadow

### 4.3 Sparkline
**Props:** `data: RegisterHistoryPoint[]`, `color?: string`

**Data source（DeviceCard 內取用）:** `monitorStore.registerHistory[`${device_id}:${primaryRegisterName}`]`（key 已存在於現有 store）

- 用 recharts `LineChart`，無 axis、無 grid、無 tooltip
- `isAnimationActive={false}`（避免 1Hz 更新時 jitter）
- height 36px，stroke `#22d3ee`，strokeWidth 1.5

### 4.4 EmptyState
**Render condition:** `devices.length === 0`

**Layout:**
- 大圖示 ⚡
- "還沒有設備"
- 內建模板捷徑（最多 3 個）— 點擊跳到 `/devices/new?template={id}` 或開建立 modal（依現有流程）
- "+ 建立設備" 主按鈕 → `/devices`

**Data:** 用 `templateService.list({ is_builtin: true })` 取前 3 個

### 4.5 EventToast
**Props:** `event: MonitorEvent | null`, `onDismiss: () => void`

- 條件：`event` 非 null 時顯示
- 位置：固定右上（`position: absolute; top: 60px; right: 20px`）
- 顏色依 event_type：
  - `anomaly_inject` → 橘
  - `fault_set` → 紅
  - `device_start` → 綠
  - 其他 → cyan
- 3 秒自動 dismiss（`setTimeout` in useEffect）
- 點擊本體 → 開 EventDrawer
- 動畫：`slideIn 0.3s ease-out`

**觸發機制:**
- monitorStore 收到 monitor_update 時，比對 `events` 陣列差集；若有新事件，將最新一個寫入 `recentToastEvent`
- 同類型事件連發時只顯示最新一個（避免 toast 堆疊）

### 4.6 EventDrawer
**Props:** `open: boolean`, `events: MonitorEvent[]`, `onClose: () => void`

- 用 antd `Drawer`，placement="right"，width 360
- 列出所有 events，最新在上
- 每筆：時間 + event_type tag + device name + detail
- 標題列右側 "Clear" 按鈕（清空 store events）

**觸發:**
- 頁面右上 📋 Events 按鈕，badge 顯示 `events.length`（當前 session 累積總數；Drawer 內 "Clear" 按鈕清空）

### 4.7 MonitorPage (index.tsx)
- 維持 WebSocket connection
- 拿掉 `selectedDevice` 相關 logic
- 拿掉底部 `Collapse` event log
- 結構：
  ```
  <PageHeader>Monitor + Live indicator + EventsButton</PageHeader>
  {devices.length === 0 ? <EmptyState/> : (
    <>
      <KpiPanel ... />
      <DeviceCardGrid devices={devices} />
    </>
  )}
  <EventToast ... />
  <EventDrawer ... />
  ```

---

## 5. Data Flow

### Initial load
1. 元件 mount → connect `ws://host:8000/ws/monitor`
2. 後端推送首個 `monitor_update`（含所有設備：running/stopped/error）
3. monitorStore 寫入 `devices`、`events`、`registerHistory`、`mqtt_broker_connected`

### Live update (1Hz)
1. 後端推送新 `monitor_update`
2. monitorStore：
   - 比對 events 差集 → 若有新事件，最新一筆 → `recentToastEvent`
   - registerHistory append（trim 至 300 點）
   - devices 直接覆寫
3. KpiPanel / DeviceCardGrid 重 render（純 props-driven）
4. DeviceCard 內偵測 register value 變動 → 加 flash class 0.5s

### Card click → navigate
1. 使用者點卡片 → `navigate('/devices/' + id)`
2. Stopped 卡片內 Start link 點擊 → `e.stopPropagation()` + 呼叫 device API

### Event toast
1. `recentToastEvent` 變動 → EventToast 顯示
2. 3 秒後自動 dismiss（清空 `recentToastEvent`）
3. 點 toast → 開 drawer

---

## 6. Error Handling

- WebSocket 斷線：頁面標題 Live 燈變灰，標題顯示 "Disconnected"，重連後自動恢復（沿用現有 `useWebSocket` hook 的 reconnect logic）
- Stopped 設備 Start API 失敗：antd `message.error('Start failed: ...')`
- EmptyState 模板 API 失敗：fallback 到只顯示 "+ 建立設備" 按鈕（不顯示模板捷徑）
- KPI Row 2 MQTT pill：取自 top-level `mqtt_broker_connected`。`true` → 綠 "MQTT broker connected"；`false` → 灰 "MQTT broker not connected"
- 卡片內 MQTT tag：取自 per-device `mqtt_stats`。`null` → 不顯示 tag；有資料 → 依錯誤率著色（見 4.2 Tags）

---

## 7. Testing

### Frontend
- `MonitorPage`: render 測試 — empty state / with devices / with stopped only
- `KpiPanel`: 計算邏輯（running/stopped/errors/dps）
- `DeviceCard`: 點擊跳頁、stopped 顯示 Start、value flash class 注入時機
- `EventToast`: 新事件出現 / 3 秒消失 / 點擊開 drawer

### Backend
- `monitor_service`: 推送包含 stopped 設備的測試
- `monitor_service`: `mqtt_broker_connected` 欄位正確計算

### 手動驗收
- 完全空狀態 → 顯示 EmptyState 含模板捷徑
- 啟動 1 台設備 → 卡片出現、即時值更新有 flash、sparkline 累積
- 停止設備 → 卡片淡化但仍顯示，Start 按鈕可用
- 觸發 anomaly → toast 出現 3 秒消失，drawer 累積
- 觸發 fault → toast 紅色，KPI Row 2 出現紅 pill
- 拔 MQTT broker → MQTT pill 變灰
- Mobile 寬度 → grid 自動 reflow（responsive grid）
- 點任一卡片 → 正確跳到 `/devices/{id}`

### Lighthouse
- Contrast 合格（dark theme 文字對比 ≥ 4.5:1）

---

## 8. Implementation Order (建議)

1. Backend: 移除 stopped filter、加 `mqtt_broker_connected`、補測試
2. Frontend types: 補 `mqtt_stats` / `mqtt_broker_connected`
3. Routing: `/` → `/monitor`、Sidebar 重排
4. Sparkline 元件
5. KpiPanel
6. 改寫 DeviceCard（mid 密度 + 動畫 + stopped 樣式）
7. 改寫 DeviceCardGrid（整合 EmptyState）
8. EventToast + EventDrawer + monitorStore 擴充
9. 移除 DeviceDetailPanel / RegisterChart / StatsPanel
10. 整合測試 + 手動驗收

---

## 9. Open Questions / Future

- `is_primary` register 機制：留待後續 issue（template schema 加欄位 + UI）
- 卡片過濾、搜尋、分組：後續 issue
- 大量設備（>50）效能：先觀察，必要時加 virtual scroll
- Toast 多事件聚合（如「3 個 anomaly 在 5 秒內」）：v2 再考慮
