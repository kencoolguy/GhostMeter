# API Reference

## Conventions

- Base path: `/api/v1/`
- All endpoints return a JSON envelope: `{ "success": bool, "data": <T> | null, "message": string | null }`
- Error responses: `{ "detail": string, "error_code": string }`
- HTTP status codes: `200` OK, `201` Created, `400` Bad Request, `404` Not Found, `422` Validation Error, `403` Forbidden, `500` Server Error
- All IDs are UUID v4

---

## Health Check

### `GET /health`

Returns system health status including database connectivity.

**Response** `200 OK`
```json
{
  "status": "ok",
  "database": "connected",
  "version": "0.1.0"
}
```

> Note: This endpoint is NOT under `/api/v1/` and does NOT use the standard `ApiResponse` envelope.

---

## Templates

Base path: `/api/v1/templates`

### Schemas

#### `RegisterDefinitionCreate` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | Register name (unique per template) |
| `address` | integer | yes | — | 0-based Modbus register address (≥ 0) |
| `function_code` | integer | no | `3` | Modbus FC: `3` (Holding) or `4` (Input) |
| `data_type` | string | yes | — | `int16`, `uint16`, `int32`, `uint32`, `float32`, `float64` |
| `byte_order` | string | no | `"big_endian"` | `big_endian`, `little_endian`, `big_endian_word_swap`, `little_endian_word_swap` |
| `scale_factor` | float | no | `1.0` | Multiplier applied to raw value |
| `unit` | string\|null | no | `null` | Physical unit (e.g. `V`, `A`, `kWh`) |
| `description` | string\|null | no | `null` | Human-readable description |
| `sort_order` | integer | no | `0` | Display order |

#### `TemplateCreate` / `TemplateUpdate` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | Template name (must be unique) |
| `protocol` | string | no | `"modbus_tcp"` | Protocol identifier |
| `description` | string\|null | no | `null` | Human-readable description |
| `registers` | array | yes | — | At least one `RegisterDefinitionCreate` required |

> `TemplateUpdate` replaces all registers wholesale (not a partial update).

#### `TemplateClone` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `new_name` | string\|null | no | `null` | Name for the clone; defaults to `"Copy of {source.name}"` |

#### `TemplateSummary` (response — list items)

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Template ID |
| `name` | string | Template name |
| `protocol` | string | Protocol identifier |
| `description` | string\|null | Description |
| `is_builtin` | boolean | `true` for seed-loaded built-in templates |
| `register_count` | integer | Number of registers in this template |
| `created_at` | datetime | ISO 8601 UTC |
| `updated_at` | datetime | ISO 8601 UTC |

#### `TemplateDetail` (response — single item)

Same as `TemplateSummary` but with `registers: RegisterDefinitionResponse[]` instead of `register_count`.

#### `RegisterDefinitionResponse` (response)

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Register ID |
| `name` | string | Register name |
| `address` | integer | 0-based address |
| `function_code` | integer | Modbus FC (3 or 4) |
| `data_type` | string | Data type |
| `byte_order` | string | Byte order |
| `scale_factor` | float | Scale multiplier |
| `unit` | string\|null | Physical unit |
| `description` | string\|null | Description |
| `sort_order` | integer | Display order |

---

### Endpoints

#### `GET /api/v1/templates`

List all device templates (without full register details).

**Response** `200 OK`
```json
{
  "success": true,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Three-Phase Energy Meter",
      "protocol": "modbus_tcp",
      "description": "Based on Eastron SDM630",
      "is_builtin": true,
      "register_count": 42,
      "created_at": "2026-03-17T00:00:00Z",
      "updated_at": "2026-03-17T00:00:00Z"
    }
  ],
  "message": null
}
```

---

#### `POST /api/v1/templates`

Create a new device template with registers.

**Request body:** `TemplateCreate`

**Response** `201 Created` — `ApiResponse[TemplateDetail]`

**Error cases:**
- `422` — empty registers list, invalid data type/byte order/function code, negative address, address overlap
- `422` — template name already exists (`detail: "Template with name '...' already exists"`)

---

#### `GET /api/v1/templates/{template_id}`

Get a single template with all register definitions.

**Path param:** `template_id` (UUID)

**Response** `200 OK` — `ApiResponse[TemplateDetail]`

**Error cases:**
- `404` — `{ "detail": "Template not found", "error_code": "TEMPLATE_NOT_FOUND" }`

---

#### `PUT /api/v1/templates/{template_id}`

Update a template. Replaces all registers wholesale.

**Path param:** `template_id` (UUID)

**Request body:** `TemplateUpdate`

**Response** `200 OK` — `ApiResponse[TemplateDetail]`

**Error cases:**
- `403` — `{ "detail": "Built-in templates cannot be modified", "error_code": "BUILTIN_TEMPLATE_IMMUTABLE" }`
- `404` — template not found
- `422` — same as create validation

---

#### `DELETE /api/v1/templates/{template_id}`

Delete a template and all its register definitions.

**Path param:** `template_id` (UUID)

**Response** `200 OK`
```json
{ "success": true, "data": null, "message": "Template deleted successfully" }
```

**Error cases:**
- `403` — `{ "detail": "Built-in templates cannot be deleted", "error_code": "BUILTIN_TEMPLATE_IMMUTABLE" }`
- `404` — template not found

---

#### `POST /api/v1/templates/{template_id}/clone`

Clone a template, creating a new user-owned copy.

**Path param:** `template_id` (UUID)

**Request body:** `TemplateClone` (optional; defaults to `{}`)

**Response** `201 Created` — `ApiResponse[TemplateDetail]`

The clone always has `is_builtin: false`. If `new_name` is omitted, the clone name is `"Copy of {source.name}"`.

**Error cases:**
- `404` — source template not found
- `422` — `new_name` already exists

---

#### `GET /api/v1/templates/{template_id}/export`

Export a template as a JSON file download. IDs are stripped from the export (suitable for re-import).

**Path param:** `template_id` (UUID)

**Response** `200 OK` — `application/json` with header:
```
Content-Disposition: attachment; filename="three_phase_energy_meter.json"
```

The response body is a raw JSON object (not wrapped in `ApiResponse`):
```json
{
  "name": "Three-Phase Energy Meter",
  "protocol": "modbus_tcp",
  "description": "Based on Eastron SDM630",
  "registers": [
    {
      "name": "voltage_l1",
      "address": 0,
      "function_code": 4,
      "data_type": "float32",
      "byte_order": "big_endian",
      "scale_factor": 1.0,
      "unit": "V",
      "description": "L1 Phase Voltage",
      "sort_order": 0
    }
  ]
}
```

---

#### `POST /api/v1/templates/import`

Import a template from a JSON file upload.

**Request:** `multipart/form-data` with field `file` (JSON file matching `TemplateCreate` schema, without `id` fields)

**Response** `201 Created` — `ApiResponse[TemplateDetail]`

**Error cases:**
- `422` — invalid JSON, validation errors, or name already exists
