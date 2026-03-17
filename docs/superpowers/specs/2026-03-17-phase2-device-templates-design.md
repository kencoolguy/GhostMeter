# Phase 2: Device Template Module — Design Spec

## Overview

Phase 2 為 GhostMeter 加入設備模板（Device Template）模組，提供 CRUD、匯入匯出、內建模板 seed data、以及前端管理介面。

實作順序：Milestone 2.1（後端 CRUD + 測試）→ Milestone 2.2（前端頁面）。

---

## Data Model

### device_templates

| Column | Type | Constraint | 說明 |
|--------|------|-----------|------|
| id | UUID | PK, default uuid4 | |
| name | VARCHAR(100) | NOT NULL, UNIQUE | 模板名稱 |
| protocol | VARCHAR(50) | NOT NULL, default "modbus_tcp" | 協議類型，為未來擴展預留 |
| description | TEXT | nullable | 說明 |
| is_builtin | BOOLEAN | NOT NULL, default false | 內建模板不可刪改 |
| created_at | TIMESTAMP(TZ) | NOT NULL, default now | |
| updated_at | TIMESTAMP(TZ) | NOT NULL, auto-update | |

### register_definitions

| Column | Type | Constraint | 說明 |
|--------|------|-----------|------|
| id | UUID | PK, default uuid4 | |
| template_id | UUID | FK → device_templates.id, ON DELETE CASCADE | |
| name | VARCHAR(100) | NOT NULL | register 名稱（如 voltage_l1） |
| address | INTEGER | NOT NULL | Modbus register 起始位址 |
| function_code | SMALLINT | NOT NULL, default 3 | FC03=Holding, FC04=Input |
| data_type | VARCHAR(20) | NOT NULL | int16/uint16/int32/uint32/float32/float64 |
| byte_order | VARCHAR(30) | NOT NULL, default "big_endian" | big_endian/little_endian/big_endian_word_swap/little_endian_word_swap |
| scale_factor | FLOAT | NOT NULL, default 1.0 | 原始值 × scale = 顯示值 |
| unit | VARCHAR(20) | nullable | V, A, W, kWh 等 |
| description | TEXT | nullable | |
| sort_order | INTEGER | NOT NULL, default 0 | 前端排序用 |

### Constraints

- `(template_id, name)` UNIQUE — 同模板內 register 名稱不可重複
- `(template_id, address, function_code)` UNIQUE — 同 function_code 下 address 不可重複

### Design Decisions

- **Register count 由 data_type 推算**：不另存 register_count 欄位。float32 → 2 registers, int16/uint16 → 1 register, int32/uint32/float32 → 2 registers, float64 → 4 registers。
- **All IDs use UUID**：遵循 CLAUDE.md 規範。

---

## API Endpoints

所有端點在 `/api/v1/templates` 下。

### Template CRUD

| Method | Path | 說明 | Status | Response |
|--------|------|------|--------|----------|
| GET | `/templates` | 列出所有模板（含 register_count） | 200 | `{data: TemplateSummary[], success: true}` |
| GET | `/templates/{id}` | 取得單一模板（含完整 registers） | 200 | `{data: TemplateDetail, success: true}` |
| POST | `/templates` | 建立新模板（含 registers） | 201 | `{data: TemplateDetail, success: true}` |
| PUT | `/templates/{id}` | 更新模板（含 registers 整批替換） | 200 | `{data: TemplateDetail, success: true}` |
| DELETE | `/templates/{id}` | 刪除模板 | 200 | `{success: true, message: "..."}` |
| POST | `/templates/{id}/clone` | 複製模板 | 201 | `{data: TemplateDetail, success: true}` |

### Import / Export

| Method | Path | 說明 | Status | Response |
|--------|------|------|--------|----------|
| GET | `/templates/{id}/export` | 匯出為 JSON | 200 | JSON file download |
| POST | `/templates/import` | 從 JSON 匯入 | 201 | `{data: TemplateDetail, success: true}` |

### Error Responses

- 404: 模板不存在 → `{detail: "Template not found", error_code: "TEMPLATE_NOT_FOUND"}`
- 403: 修改/刪除內建模板 → `{detail: "Built-in templates cannot be modified", error_code: "BUILTIN_TEMPLATE_IMMUTABLE"}`
- 422: 驗證失敗（address 重疊、名稱重複等）→ `{detail: "...", error_code: "VALIDATION_ERROR"}`

### Design Decisions

- **PUT 整批替換 registers**：更新時先刪除舊 registers 再建立新的，前端一次送完整列表。避免複雜的 diff 邏輯。
- **GET 列表回傳 register_count**：不含完整 registers，減少資料量。
- **Address 重疊驗證**：建立/更新時根據 data_type 計算佔用範圍，確保同 function_code 下不重疊。

---

## Service Layer

### template_service.py

負責所有業務邏輯，route handler 只做參數接收和回傳：

- `list_templates(session)` → 查詢所有模板，附帶 register_count
- `get_template(session, id)` → 查詢單一模板 + 所有 registers（按 sort_order 排序）
- `create_template(session, data)` → 建立模板 + registers，驗證 address 不重疊
- `update_template(session, id, data)` → 檢查 is_builtin，整批替換 registers
- `delete_template(session, id)` → 檢查 is_builtin，CASCADE 刪除 registers
- `clone_template(session, id, new_name?)` → 複製模板 + registers，`is_builtin=false`
- `export_template(session, id)` → 組成匯出 JSON
- `import_template(session, json_data)` → 解析 JSON，呼叫 create_template

---

## Seed Data

### 檔案結構

```
backend/app/seed/
├── loader.py              # 通用載入邏輯
├── three_phase_meter.json # Eastron SDM630 參考
├── single_phase_meter.json # Eastron SDM120 參考
└── solar_inverter.json    # Fronius Symo (SunSpec) 參考
```

### JSON 格式

與匯入 API 共用同一套 Pydantic schema：

```json
{
  "name": "SDM630 Three-Phase Meter",
  "protocol": "modbus_tcp",
  "description": "Three-phase power meter based on Eastron SDM630 register map",
  "registers": [
    {
      "name": "voltage_l1",
      "address": 30001,
      "function_code": 4,
      "data_type": "float32",
      "byte_order": "big_endian",
      "scale_factor": 1.0,
      "unit": "V",
      "description": "Phase L1 voltage"
    }
  ]
}
```

### 載入邏輯

1. App 啟動時（FastAPI lifespan）呼叫 `seed_builtin_templates()`
2. 掃描 `seed/` 目錄下所有 `.json` 檔案
3. 對每個 JSON，檢查 DB 中是否已存在同名的 builtin 模板
4. 不存在 → 建立（`is_builtin=true`）；已存在 → 跳過
5. 未來新增內建模板只需放一個 JSON 檔案，不改程式碼

---

## Frontend Architecture

### Store（templateStore.ts）

```typescript
interface TemplateSummary {
  id: string
  name: string
  protocol: string
  description: string | null
  is_builtin: boolean
  register_count: number
  created_at: string
  updated_at: string
}

interface RegisterDefinition {
  id?: string
  name: string
  address: number
  function_code: number
  data_type: string
  byte_order: string
  scale_factor: number
  unit: string | null
  description: string | null
  sort_order: number
}

interface TemplateDetail extends Omit<TemplateSummary, 'register_count'> {
  registers: RegisterDefinition[]
}

interface TemplateStore {
  templates: TemplateSummary[]
  currentTemplate: TemplateDetail | null
  loading: boolean

  fetchTemplates: () => Promise<void>
  fetchTemplate: (id: string) => Promise<void>
  createTemplate: (data: CreateTemplate) => Promise<void>
  updateTemplate: (id: string, data: UpdateTemplate) => Promise<void>
  deleteTemplate: (id: string) => Promise<void>
  cloneTemplate: (id: string) => Promise<void>
}
```

### Page Structure

```
pages/Templates/
├── index.tsx              # 模板列表頁（主路由）
├── TemplateList.tsx        # 表格元件
├── TemplateForm.tsx        # 新增/編輯頁面
├── RegisterTable.tsx       # Register map 可編輯表格
└── ImportExportButtons.tsx # 匯入匯出按鈕
```

### Routes

- `/templates` → 列表頁
- `/templates/new` → 新增頁
- `/templates/:id` → 編輯頁

使用獨立頁面而非 Modal，因為 register map 表格內容較多。

### 列表頁行為

- Ant Design Table 顯示：名稱、協議、register 數量、內建 badge、建立時間
- 操作欄：編輯、複製、刪除、匯出
- 內建模板：隱藏刪除/編輯按鈕，只有複製和匯出
- 右上角：「新增模板」按鈕 + 「匯入」按鈕

### 編輯頁行為

- 上方：模板基本資訊表單（name, protocol, description）
- 下方：Register map 可編輯表格
  - 欄位：name, address, function_code, data_type, byte_order, scale_factor, unit, description
  - 支援新增/刪除 row
  - sort_order 由前端 row 順序決定，儲存時帶入

---

## Implementation Order

1. **Milestone 2.1（後端）**：Models → Schemas → Service → Routes → Seed Data → Migration → Tests
2. **Milestone 2.2（前端）**：Types → Store → API Service → 列表頁 → 編輯頁 → 匯入匯出
