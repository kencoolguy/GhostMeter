# Modbus 寫入偵測 — 設計 (issue #71)

- **Date**: 2026-06-22
- **Issue**: #71 (follow-up #72 for other protocols)
- **Scope**: Modbus TCP only
- **Status**: Approved design, ready for implementation plan

## 1. 問題與目標

GhostMeter 目前是唯讀模擬器。EMS 開發者無法驗證自家系統「確實發出了正確的 Modbus 寫入」
（例如寫 setpoint），因為：

- Holding register 寫入（FC06/16）被 pymodbus 默默接受，但值在下一個 simulation tick
  就被模擬引擎覆蓋。
- 寫入完全沒有任何記錄 — log / API / WebSocket / UI 都看不到「誰在何時寫了什麼」。

**目標**：偵測並記錄 client 的 Modbus 寫入嘗試，在 UI 即時提示，讓使用者能檢視寫入清單以
驗證 EMS 行為。核心價值在「偵測 + 記錄」，不在「保留寫入值」。

**策略**：accept-and-ignore + record。接受寫入（client 收到成功回應），但不持久化寫入值
（模擬引擎下一 tick 照常覆蓋）。前提已確認：EMS 不做 write-then-read-back 驗證。

## 2. 架構總覽

唯讀模擬器在 `trace_pdu` 攔截到 write function code 時，記錄一筆事件到 per-device
in-memory ring buffer。事件摘要（未讀數 + 最新一筆）搭現有 1Hz monitor snapshot 推到前端
顯示 badge；完整清單走新 REST endpoint 拉取。

```
EMS 寫入 → pymodbus → trace_pdu(record) → ring buffer + unread++
        → 下個 1Hz monitor snapshot 帶 unread → UI badge 亮
        → 使用者點開抽屜 → GET /write-events (清單) + POST /write-events/ack (unread 歸零)
```

## 3. 元件

### 3.1 `app/simulation/write_tracker.py`（新增）

仿 `fault_simulator` 的 module-level singleton，protocol-agnostic（#72 擴展時直接重用）。

```python
@dataclass(frozen=True)
class WriteEvent:
    timestamp: datetime          # UTC
    function_code: int           # 5 / 6 / 15 / 16
    address: int                 # starting address
    values: list[int]            # raw 16-bit words；coil 用 0|1
    register_name: str | None    # 反查 template register；查無則 None

# module state
_buffers: dict[UUID, deque[WriteEvent]]   # maxlen=50 per device
_unread: dict[UUID, int]

# interface
def record(device_id, function_code, address, values, register_name) -> None
def get_events(device_id) -> list[WriteEvent]        # 新→舊
def get_unread_count(device_id) -> int
def mark_read(device_id) -> None                      # unread 歸零
def latest(device_id) -> WriteEvent | None
def clear(device_id) -> None                          # device stop 時清空
```

- Ring buffer 大小 **N=50**/device。
- 全 in-memory；device stop / server restart 即清空（符合「不進 DB」）。

### 3.2 `modbus_tcp.py` — trace_pdu incoming 分支

- `pdu.function_code in {5, 6, 15, 16}` → 解析 address 與 values，用現有
  `_device_registers` 反查 register name（依 function_code + address 對應）→
  `write_tracker.record(...)`。
- **防禦性**：整段包 try/except，記錄失敗只 `logger.warning(...)`，**絕不影響 Modbus 回應**。
- 與 fault simulation 並存：fault 行為照舊；寫入「嘗試」一律記錄，**含被 fault 抑制
  （timeout/intermittent）的請求** — 因為使用者要驗證的是 client 是否發出寫入。
- `_do_remove_device` 與 `stop()` 時呼叫 `write_tracker.clear(device_id)`。

pymodbus 各 write request PDU 的屬性名（`address` / `registers` / `values` / `count`）
在實作時以實測為準（TDD red test pin 住）。

### 3.3 `monitor_service.get_snapshot`

每個 device payload 新增：

```json
"write_events": {
  "unread": 3,
  "latest": { "timestamp": "...", "function_code": 6, "address": 40001,
              "values": [1234], "register_name": "active_power_setpoint" }
}
```

無寫入時 `unread: 0, latest: null`。

### 3.4 REST API

| Method | Path | 行為 |
|--------|------|------|
| `GET`  | `/api/v1/devices/{id}/write-events` | 回事件清單（新→舊）+ 當前 unread 數。**純讀，無 side effect** |
| `POST` | `/api/v1/devices/{id}/write-events/ack` | 將該 device 的 unread 歸零（`mark_read`），回 `{ success, unread: 0 }` |

- Response schema 走專案慣例 `{ data, message, success }`。
- 新增 Pydantic schema：`WriteEventResponse`、`WriteEventsListResponse`。
- 路由放在 device 子資源既有的 route 模組。

### 3.5 Frontend

- `monitorStore` 從 snapshot 讀每個 device 的 `write_events.unread`。
- Device 卡片 / DeviceDetail 上用 antd `<Badge count={unread}>` 提示。
- 點 badge → 開 antd `<Drawer>`：用 `GET /write-events` 拉清單顯示（timestamp、FC、
  address、register 名稱、raw values）。
- Drawer 開啟（成功載入清單後）→ 呼叫 `POST /write-events/ack` → 下個 snapshot unread 歸零。
- `services/` 新增對應 API client 函式（components 不直接 fetch）。

## 4. 邊界與錯誤處理

- **未知 address**：`register_name = None`，照記。
- **Coil 寫入（FC05/15）**：datastore 目前無 coil block，pymodbus 會回 ILLEGAL_ADDRESS，
  但 incoming 分支在回應前就記錄，故仍能記到「寫入嘗試」。
- **FC16 多 register**：記 starting address + words list（一筆事件）。
- **非本 server 管理的 slave**（`_slave_to_device` 查無）：忽略不記。
- **記錄絕不拋例外進 trace_pdu**：任何解析/反查失敗都降級為記錄部分資訊或跳過 + log。

## 5. 測試

### Backend
- **Unit（`write_tracker`）**：record / ring buffer `maxlen` 截斷 / unread 累加 /
  mark_read 歸零 / clear。
- **Integration**：起 modbus server + 用 pymodbus client 實際寫入
  - FC06 → 斷言事件 address/value/register_name 正確
  - FC16 → 斷言多 register words 正確記成一筆
  - FC05（coil）→ 斷言記成寫入嘗試（即使回 ILLEGAL_ADDRESS）
  - 斷言 `get_snapshot` 帶 `write_events.unread`
  - 斷言 `GET /write-events` 回清單且 **不** 改 unread；`POST /ack` 後 unread 歸零
  - 寫入被 timeout fault 抑制時，仍記錄到事件

### Frontend
- Type check 通過；badge 綁定 unread；drawer 載入 + ack 流程。
- E2E（Playwright）視情況補：寫入 → badge 亮 → 開 drawer → 歸零。

## 6. 不做（YAGNI / 未來）

- register 層級 `writable` flag 與寫入值持久化（write-then-read-back 情境）。
- OPC UA / BACnet / SNMP / MQTT 寫入支援（#72，等實際需求）。
- 寫入 setpoint 影響 computed register 的行為模擬。
- 寫入事件持久化到 DB / 跨 restart 保留。
