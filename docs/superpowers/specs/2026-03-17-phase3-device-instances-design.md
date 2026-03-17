# Phase 3: Device Instance Module — Design Spec

## Overview

Phase 3 為 GhostMeter 加入設備實例（Device Instance）模組。用戶可從模板建立虛擬設備、分配 Slave ID、控制啟停狀態，並查看 register 定義列表。

實作順序：Milestone 3.1（後端 CRUD + 測試）→ Milestone 3.2（前端頁面）。

---

## Data Model

### device_instances

| Column | Type | Constraint | 說明 |
|--------|------|-----------|------|
| id | UUID | PK, default uuid4 | |
| template_id | UUID | FK → device_templates.id (RESTRICT), NOT NULL | 使用的模板 |
| name | VARCHAR(200) | NOT NULL | 設備名稱 |
| slave_id | INTEGER | NOT NULL | Modbus Slave ID (1-247) |
| status | VARCHAR(20) | NOT NULL, default "stopped" | stopped / running / error |
| port | INTEGER | NOT NULL, default 502 | Modbus TCP port |
| description | TEXT | nullable | |
| created_at | TIMESTAMP(TZ) | NOT NULL, default now | |
| updated_at | TIMESTAMP(TZ) | NOT NULL, auto-update | |

### Constraints

- `(slave_id, port)` UNIQUE — 同 port 下 Slave ID 不可重複
- `template_id` FK 設為 `RESTRICT` — 有設備引用的模板不可刪除

### Design Decisions

- **slave_id 範圍 1-247**：Modbus 標準定義的合法 Unit ID 範圍。
- **port 欄位**：MVP 只用 502，但欄位先加上，未來可支援多 TCP port。
- **status 是純狀態欄位**：Phase 3 的 start/stop 只切換 DB status，不啟動實際服務。Phase 4 才會根據 status 啟動 Modbus server。
- **FK RESTRICT**：刪除模板前必須先刪除關聯設備。Service 層先檢查給出友善錯誤，DB FK RESTRICT 兜底。

---

## Pydantic Schemas (Backend)

### Request Schemas

```python
class DeviceCreate(BaseModel):
    template_id: UUID
    name: str
    slave_id: int              # 1-247
    port: int = 502
    description: str | None = None

class DeviceBatchCreate(BaseModel):
    template_id: UUID
    slave_id_start: int        # 起始 Slave ID
    slave_id_end: int          # 結束 Slave ID（inclusive）
    port: int = 502
    name_prefix: str | None = None  # 沒填就用模板名
    description: str | None = None

class DeviceUpdate(BaseModel):
    name: str
    slave_id: int              # 1-247
    port: int = 502
    description: str | None = None
```

### Response Schemas

```python
class DeviceSummary(BaseModel):
    id: UUID
    template_id: UUID
    template_name: str         # JOIN from device_templates
    name: str
    slave_id: int
    status: str
    port: int
    description: str | None
    created_at: datetime
    updated_at: datetime

class RegisterValue(BaseModel):
    name: str
    address: int
    function_code: int
    data_type: str
    unit: str | None
    description: str | None
    value: float | None = None  # Phase 3: always null; Phase 5: real-time value

class DeviceDetail(BaseModel):
    id: UUID
    template_id: UUID
    template_name: str
    name: str
    slave_id: int
    status: str
    port: int
    description: str | None
    registers: list[RegisterValue]
    created_at: datetime
    updated_at: datetime
```

---

## API Endpoints

所有端點在 `/api/v1/devices` 下。

### Device CRUD

| Method | Path | 說明 | Status | Response |
|--------|------|------|--------|----------|
| GET | `/devices` | 列出所有設備（含模板名稱） | 200 | `ApiResponse[list[DeviceSummary]]` |
| GET | `/devices/{id}` | 取得設備詳情（含 register 定義列表，值為 null） | 200 | `ApiResponse[DeviceDetail]` |
| POST | `/devices` | 建立單一設備 | 201 | `ApiResponse[DeviceSummary]` |
| POST | `/devices/batch` | 批量建立設備（指定 slave_id 範圍） | 201 | `ApiResponse[list[DeviceSummary]]` |
| PUT | `/devices/{id}` | 更新設備（name, description, slave_id, port） | 200 | `ApiResponse[DeviceSummary]` |
| DELETE | `/devices/{id}` | 刪除設備（running 狀態不可刪除） | 200 | `ApiResponse[None]` with message |

### Start / Stop

| Method | Path | 說明 | Status | Response |
|--------|------|------|--------|----------|
| POST | `/devices/{id}/start` | 啟動設備（stopped → running） | 200 | `ApiResponse[DeviceSummary]` |
| POST | `/devices/{id}/stop` | 停止設備（running → stopped） | 200 | `ApiResponse[DeviceSummary]` |

### Register Values

| Method | Path | 說明 | Status | Response |
|--------|------|------|--------|----------|
| GET | `/devices/{id}/registers` | 取得 register 列表（定義 + 值，Phase 3 值為 null） | 200 | `ApiResponse[list[RegisterValue]]` |

### Error Responses

- 404: 設備不存在 → `{detail: "Device not found", error_code: "DEVICE_NOT_FOUND"}`
- 404: 模板不存在 → `{detail: "Template not found", error_code: "TEMPLATE_NOT_FOUND"}`
- 422: Slave ID 超出範圍 (1-247) → `{detail: "...", error_code: "VALIDATION_ERROR"}`
- 422: Slave ID 同 port 重複 → `{detail: "Slave ID N is already in use on port P", error_code: "VALIDATION_ERROR"}`
- 422: 批量範圍無效 (start > end) → `{detail: "...", error_code: "VALIDATION_ERROR"}`
- 409: 刪除 running 設備 → `{detail: "Cannot delete a running device", error_code: "DEVICE_RUNNING"}`
- 409: 無效狀態轉換 → `{detail: "Device is already running/stopped", error_code: "INVALID_STATE_TRANSITION"}`

### Design Decisions

- **不做分頁**：MVP 階段設備數量有限（預估 < 100），暫不需分頁。
- **批量建立**：一次 API call 建立多台設備，回傳所有建立的設備列表。任一 slave_id 衝突則整個 batch 失敗（atomic）。
- **批量命名**：有 name_prefix 用 `"{prefix} {N}"`，沒有用 `"{template_name} - Slave {N}"`。
- **不可更新 template_id**：設備建立後不可換模板（register map 不同會有問題）。
- **不可更新 status**：只能透過 /start 和 /stop 端點控制。
- **running 狀態不可刪除**：需先 stop 再刪除，避免意外。

---

## Service Layer

### device_service.py

- `list_devices(session)` → 查詢所有設備，JOIN template 取 template_name
- `get_device(session, id)` → 查詢單一設備 + template_name
- `get_device_detail(session, id)` → 設備 + 模板的 register 定義列表（value=None）
- `create_device(session, data)` → 驗證 template 存在、slave_id 1-247、同 port 不重複
- `batch_create_devices(session, data)` → 驗證範圍、檢查所有 slave_id 可用、批量建立（atomic）
- `update_device(session, id, data)` → 不可更新 template_id 和 status，驗證 slave_id 唯一
- `delete_device(session, id)` → running 狀態回傳 409
- `start_device(session, id)` → stopped → running（已 running → 409）
- `stop_device(session, id)` → running → stopped（已 stopped → 409）
- `get_device_registers(session, id)` → 從模板取 register 定義，value=None

### 模板刪除保護（修改 template_service.py）

在 `delete_template` 中加入檢查：刪除前查詢是否有 device_instances 引用此模板。

```python
# 在刪除前加入：
device_count = await session.scalar(
    select(func.count(DeviceInstance.id))
    .where(DeviceInstance.template_id == template_id)
)
if device_count > 0:
    raise ConflictException(
        detail=f"Template is in use by {device_count} device(s)",
        error_code="TEMPLATE_IN_USE",
    )
```

需要新增 `ConflictException`（HTTP 409）到 exceptions.py。

---

## Frontend Architecture

### Types（types/device.ts）

```typescript
export interface DeviceSummary {
  id: string;
  template_id: string;
  template_name: string;
  name: string;
  slave_id: number;
  status: "stopped" | "running" | "error";
  port: number;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface RegisterValue {
  name: string;
  address: number;
  function_code: number;
  data_type: string;
  unit: string | null;
  description: string | null;
  value: number | null;
}

export interface DeviceDetail extends DeviceSummary {
  registers: RegisterValue[];
}

export interface CreateDevice {
  template_id: string;
  name: string;
  slave_id: number;
  port?: number;
  description?: string | null;
}

export interface BatchCreateDevice {
  template_id: string;
  slave_id_start: number;
  slave_id_end: number;
  port?: number;
  name_prefix?: string | null;
  description?: string | null;
}

export interface UpdateDevice {
  name: string;
  slave_id: number;
  port?: number;
  description?: string | null;
}
```

### Store（stores/deviceStore.ts）

```typescript
interface DeviceState {
  devices: DeviceSummary[];
  currentDevice: DeviceDetail | null;
  loading: boolean;
  fetchDevices: () => Promise<void>;
  fetchDevice: (id: string) => Promise<void>;
  createDevice: (data: CreateDevice) => Promise<DeviceSummary | null>;
  batchCreateDevices: (data: BatchCreateDevice) => Promise<boolean>;
  updateDevice: (id: string, data: UpdateDevice) => Promise<DeviceSummary | null>;
  deleteDevice: (id: string) => Promise<boolean>;
  startDevice: (id: string) => Promise<boolean>;
  stopDevice: (id: string) => Promise<boolean>;
  clearCurrentDevice: () => void;
}
```

### Page Structure

```
pages/Devices/
├── index.tsx              # 設備列表頁
├── DeviceList.tsx          # 表格元件
├── CreateDeviceModal.tsx   # 建立設備 Modal（Tab: 單一 / 批量）
└── DeviceDetail.tsx        # 設備詳情頁
```

### Routes

- `/devices` → 列表頁
- `/devices/:id` → 詳情頁

### 列表頁行為

- Ant Design Table 顯示：名稱、Slave ID、模板名、Port、狀態 badge（running=綠、stopped=灰、error=紅）
- 操作欄：啟動/停止 toggle 按鈕、編輯（inline 或 modal）、刪除
- 右上角：「新增設備」按鈕（開啟 Modal）

### 建立設備 Modal

- 兩個 Tab：「單一建立」和「批量建立」
- 單一：選模板 dropdown → 填 name + slave_id
- 批量：選模板 → 填 slave_id 範圍 + 可選 name_prefix
- 建立後自動 refresh 列表

### 詳情頁行為

- 上方：設備基本資訊（name、slave_id、模板名、status badge、port）
- 下方：Register 列表表格（name、address、data_type、unit、value=`—`）
- Phase 5 時 value 會接上 WebSocket 即時值

---

## Implementation Order

1. **Milestone 3.1（後端）**：ConflictException → Model → Migration → Schemas → Tests → Service → Routes → Template protection → Tests pass
2. **Milestone 3.2（前端）**：Types → Store → API Service → 列表頁 → 建立 Modal → 詳情頁
