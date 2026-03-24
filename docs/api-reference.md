# API Reference

## Conventions

- Base path: `/api/v1/`
- All endpoints return a JSON envelope: `{ "success": bool, "data": <T> | null, "message": string | null }`
- Error responses: `{ "detail": string, "error_code": string }`
- HTTP status codes: `200` OK, `201` Created, `400` Bad Request, `404` Not Found, `409` Conflict, `422` Validation Error, `403` Forbidden, `500` Server Error
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

---

## Devices

Base path: `/api/v1/devices`

### Schemas

#### `DeviceCreate` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `template_id` | UUID | yes | — | Template to use |
| `name` | string | yes | — | Device name |
| `slave_id` | integer | yes | — | Modbus Slave ID (1–247) |
| `port` | integer | no | `502` | Modbus TCP port |
| `description` | string\|null | no | `null` | Description |
| `profile_id` | UUID\|null | no | `null` | Simulation profile to apply. Absent = auto-apply default; explicit `null` = skip |

#### `DeviceBatchCreate` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `template_id` | UUID | yes | — | Template to use |
| `slave_id_start` | integer | yes | — | Start of Slave ID range (1–247) |
| `slave_id_end` | integer | yes | — | End of Slave ID range (inclusive, 1–247) |
| `port` | integer | no | `502` | Modbus TCP port |
| `name_prefix` | string\|null | no | `null` | Name prefix; defaults to template name |
| `description` | string\|null | no | `null` | Description for all created devices |
| `profile_id` | UUID\|null | no | `null` | Simulation profile to apply. Absent = auto-apply default; explicit `null` = skip |

> Batch limit: 50 devices per call. Naming: `"{prefix} {N}"` if prefix given, else `"{template_name} - Slave {N}"`.

#### `DeviceUpdate` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | Device name |
| `slave_id` | integer | yes | — | Modbus Slave ID (1–247) |
| `port` | integer | no | `502` | Modbus TCP port |
| `description` | string\|null | no | `null` | Description |

> Full replacement — caller must re-send all fields. `template_id` and `status` are not updatable.

#### `DeviceSummary` (response — list items)

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Device ID |
| `template_id` | UUID | Template ID |
| `template_name` | string | Template name (joined) |
| `name` | string | Device name |
| `slave_id` | integer | Modbus Slave ID |
| `status` | string | `stopped`, `running`, or `error` |
| `port` | integer | Modbus TCP port |
| `description` | string\|null | Description |
| `created_at` | datetime | ISO 8601 UTC |
| `updated_at` | datetime | ISO 8601 UTC |

#### `DeviceDetail` (response — single item)

Same as `DeviceSummary` plus `registers: RegisterValue[]`.

#### `RegisterValue` (response)

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Register name |
| `address` | integer | 0-based address |
| `function_code` | integer | Modbus FC (3 or 4) |
| `data_type` | string | Data type |
| `byte_order` | string | Byte order |
| `scale_factor` | float | Scale multiplier |
| `unit` | string\|null | Physical unit |
| `description` | string\|null | Description |
| `value` | float\|null | Current value (Phase 3: always `null`) |

---

### Endpoints

#### `GET /api/v1/devices`

List all device instances.

**Response** `200 OK` — `ApiResponse[DeviceSummary[]]`

---

#### `POST /api/v1/devices`

Create a single device instance.

**Request body:** `DeviceCreate`

**Response** `201 Created` — `ApiResponse[DeviceSummary]`

**Error cases:**
- `404` — template not found (`TEMPLATE_NOT_FOUND`)
- `422` — Slave ID out of range or already in use on port

---

#### `POST /api/v1/devices/batch`

Batch create device instances. Atomic — all or nothing.

**Request body:** `DeviceBatchCreate`

**Response** `201 Created` — `ApiResponse[DeviceSummary[]]`

**Error cases:**
- `404` — template not found
- `422` — invalid range (start > end), exceeds 50 limit, or any Slave ID conflict

---

#### `GET /api/v1/devices/{device_id}`

Get device detail with register definitions.

**Path param:** `device_id` (UUID)

**Response** `200 OK` — `ApiResponse[DeviceDetail]`

**Error cases:**
- `404` — `{ "detail": "Device not found", "error_code": "DEVICE_NOT_FOUND" }`

---

#### `PUT /api/v1/devices/{device_id}`

Update a device instance. Running devices cannot be updated.

**Path param:** `device_id` (UUID)

**Request body:** `DeviceUpdate`

**Response** `200 OK` — `ApiResponse[DeviceSummary]`

**Error cases:**
- `404` — device not found
- `409` — `{ "detail": "Cannot update a running device", "error_code": "DEVICE_RUNNING" }`
- `422` — Slave ID conflict

---

#### `DELETE /api/v1/devices/{device_id}`

Delete a device instance. Running devices cannot be deleted.

**Path param:** `device_id` (UUID)

**Response** `200 OK`
```json
{ "success": true, "data": null, "message": "Device deleted successfully" }
```

**Error cases:**
- `404` — device not found
- `409` — `{ "detail": "Cannot delete a running device", "error_code": "DEVICE_RUNNING" }`

---

#### `POST /api/v1/devices/{device_id}/start`

Start a device (stopped → running).

**Path param:** `device_id` (UUID)

**Response** `200 OK` — `ApiResponse[DeviceSummary]`

**Error cases:**
- `404` — device not found
- `409` — `{ "detail": "Device is already running/error", "error_code": "INVALID_STATE_TRANSITION" }`

---

#### `POST /api/v1/devices/{device_id}/stop`

Stop a device (running/error → stopped).

**Path param:** `device_id` (UUID)

**Response** `200 OK` — `ApiResponse[DeviceSummary]`

**Error cases:**
- `404` — device not found
- `409` — `{ "detail": "Device is already stopped", "error_code": "INVALID_STATE_TRANSITION" }`

---

#### `GET /api/v1/devices/{device_id}/registers`

Get register definitions for a device. Phase 3: values are always `null`.

**Path param:** `device_id` (UUID)

**Response** `200 OK` — `ApiResponse[RegisterValue[]]`

**Error cases:**
- `404` — device not found

---

### Template Deletion Protection

When a template has associated devices, `DELETE /api/v1/templates/{template_id}` returns:

**`409 Conflict`**
```json
{ "detail": "Template is in use by 3 device(s)", "error_code": "TEMPLATE_IN_USE" }
```

Delete all associated devices first, then delete the template

---

## Simulation Profiles

Base path: `/api/v1/simulation-profiles`

Simulation profiles are reusable sets of simulation parameters bound to a device template. Built-in profiles are loaded from seed data and cannot have their configs modified or be deleted.

### Schemas

#### `SimulationProfileCreate` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `template_id` | UUID | yes | — | Template this profile belongs to |
| `name` | string | yes | — | Profile name (max 200 chars, unique per template) |
| `description` | string\|null | no | `null` | Description |
| `is_default` | boolean | no | `false` | Auto-apply on device creation (at most one default per template) |
| `configs` | ProfileConfigEntry[] | yes | — | Array of register simulation configs |

#### `SimulationProfileUpdate` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string\|null | no | `null` | New name |
| `description` | string\|null | no | `null` | New description |
| `is_default` | boolean\|null | no | `null` | Change default status |
| `configs` | ProfileConfigEntry[]\|null | no | `null` | Replace configs (rejected for built-in profiles) |

#### `ProfileConfigEntry`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `register_name` | string | yes | — | Target register name |
| `data_mode` | string | yes | — | One of: `static`, `random`, `daily_curve`, `computed`, `accumulator` |
| `mode_params` | object | no | `{}` | Mode-specific parameters |
| `is_enabled` | boolean | no | `true` | Whether this config is active |
| `update_interval_ms` | integer | no | `1000` | Update interval (100–60000 ms) |

#### `SimulationProfileResponse` (response)

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Profile ID |
| `template_id` | UUID | Template ID |
| `name` | string | Profile name |
| `description` | string\|null | Description |
| `is_builtin` | boolean | `true` for seed-loaded profiles |
| `is_default` | boolean | Auto-applied on device creation |
| `configs` | object[] | Array of register simulation configs |
| `created_at` | datetime | ISO 8601 UTC |
| `updated_at` | datetime | ISO 8601 UTC |

### Endpoints

#### `GET /api/v1/simulation-profiles?template_id={uuid}`

List all profiles for a template.

**Query param:** `template_id` (UUID, required)

**Response** `200 OK` — `ApiResponse[SimulationProfileResponse[]]`

---

#### `GET /api/v1/simulation-profiles/{profile_id}`

Get a single profile.

**Path param:** `profile_id` (UUID)

**Response** `200 OK` — `ApiResponse[SimulationProfileResponse]`

**Error cases:**
- `404` — profile not found

---

#### `POST /api/v1/simulation-profiles`

Create a new simulation profile.

**Request body:** `SimulationProfileCreate`

**Response** `201 Created` — `ApiResponse[SimulationProfileResponse]`

**Error cases:**
- `404` — template not found
- `409` — duplicate name for this template

---

#### `PUT /api/v1/simulation-profiles/{profile_id}`

Update a simulation profile.

**Path param:** `profile_id` (UUID)

**Request body:** `SimulationProfileUpdate`

**Response** `200 OK` — `ApiResponse[SimulationProfileResponse]`

**Error cases:**
- `404` — profile not found
- `403` — cannot modify configs of a built-in profile
- `409` — duplicate name

---

#### `DELETE /api/v1/simulation-profiles/{profile_id}`

Delete a simulation profile.

**Path param:** `profile_id` (UUID)

**Response** `200 OK`
```json
{ "success": true, "data": null, "message": "Profile deleted successfully" }
```

**Error cases:**
- `404` — profile not found
- `403` — cannot delete a built-in profile

---

### Profile Apply Behavior on Device Creation

When creating a device (`POST /devices` or `POST /devices/batch`), the `profile_id` field controls which profile is applied:

| `profile_id` in request | Behavior |
|------------------------|----------|
| Absent (not in JSON) | Auto-apply the template's default profile (if one exists) |
| Explicit UUID | Apply that specific profile (404 if not found) |
| Explicit `null` | Skip — no profile applied, all registers start at 0 |

Profile configs are **copied** into `simulation_configs` at apply time. There is no ongoing link — subsequent changes to the profile do not affect already-created devices.

---

## System

### Export Configuration

#### `GET /api/v1/system/export`

Exports the full system configuration (templates, devices, simulation configs, anomaly schedules) as a JSON file download.

**Response** `200 OK` — JSON file with `Content-Disposition: attachment`

```json
{
  "version": "1.0",
  "exported_at": "2026-03-19T12:00:00+00:00",
  "templates": [
    {
      "name": "SDM630 Three-Phase Meter",
      "protocol": "modbus_tcp",
      "description": "...",
      "is_builtin": true,
      "registers": [
        {
          "name": "voltage_l1",
          "address": 0,
          "function_code": 4,
          "data_type": "float32",
          "byte_order": "big_endian",
          "scale_factor": 1.0,
          "unit": "V",
          "description": "Phase 1 Voltage",
          "sort_order": 0
        }
      ]
    }
  ],
  "devices": [
    {
      "name": "Meter-01",
      "template_name": "SDM630 Three-Phase Meter",
      "slave_id": 1,
      "port": 502,
      "description": "..."
    }
  ],
  "simulation_configs": [
    {
      "device_name": "Meter-01",
      "register_name": "voltage_l1",
      "data_mode": "daily_curve",
      "mode_params": {"base": 230, "amplitude": 10, "peak_hour": 14},
      "is_enabled": true,
      "update_interval_ms": 1000
    }
  ],
  "anomaly_schedules": [
    {
      "device_name": "Meter-01",
      "register_name": "voltage_l1",
      "anomaly_type": "spike",
      "anomaly_params": {"multiplier": 3.0, "probability": 0.1},
      "trigger_after_seconds": 300,
      "duration_seconds": 60,
      "is_enabled": true
    }
  ]
}
```

---

### Import Configuration

#### `POST /api/v1/system/import`

Imports a system configuration snapshot. Upserts templates by name, devices by (slave_id, port). Built-in templates are skipped.

**Request Body** — Same JSON format as export

**Response** `200 OK`
```json
{
  "success": true,
  "data": {
    "templates_created": 2,
    "templates_updated": 1,
    "templates_skipped": 3,
    "devices_created": 5,
    "devices_updated": 0,
    "simulation_configs_set": 15,
    "anomaly_schedules_set": 3
  },
  "message": "Import completed successfully"
}
```

**Errors:**
- `422` — unsupported version, device references unknown template, invalid data
