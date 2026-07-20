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
| `protocol` | string | no | `"modbus_tcp"` | Protocol identifier. Accepted values: `"modbus_tcp"`, `"mqtt"`, `"snmp"`, `"opcua"`, `"bacnet"` |
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
| `slave_id` | integer | yes | — | Slave ID, ≥1 (upper bound depends on the template's protocol — see below) |
| `description` | string\|null | no | `null` | Description |
| `profile_id` | UUID\|null | no | `null` | Simulation profile to apply. Absent = auto-apply default; explicit `null` = skip |

> `port` is not a request field — the server derives it from the template's protocol (see `DeviceSummary.port` below) and ignores any client-supplied value.

#### `DeviceBatchCreate` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `template_id` | UUID | yes | — | Template to use |
| `slave_id_start` | integer | yes | — | Start of Slave ID range, ≥1 |
| `slave_id_end` | integer | yes | — | End of Slave ID range (inclusive); upper bound depends on protocol |
| `name_prefix` | string\|null | no | `null` | Name prefix; defaults to template name |
| `description` | string\|null | no | `null` | Description for all created devices |
| `profile_id` | UUID\|null | no | `null` | Simulation profile to apply. Absent = auto-apply default; explicit `null` = skip |

> Batch limit: 50 devices per call. Naming: `"{prefix} {N}"` if prefix given, else `"{template_name} - Slave {N}"`. `port` is server-derived, same as `DeviceCreate`.

#### `DeviceUpdate` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | Device name |
| `slave_id` | integer | yes | — | Slave ID, ≥1 (upper bound depends on the device's protocol) |
| `description` | string\|null | no | `null` | Description |

> Full replacement — caller must re-send all fields. `template_id` and `status` are not updatable. `port` is server-derived, same as `DeviceCreate`.

#### Per-protocol Slave ID limits

| Protocol | Slave ID ceiling | Why |
|----------|-------------------|-----|
| `modbus_tcp` | 247 | Modbus unit identifier is a 1-byte field (1–247; 0 and 248–255 are broadcast/reserved) |
| `bacnet` | 247 | Devices sit on a virtual BACnet/IP network keyed by a 1-byte MAC (`slave_id`); MAC 254 is reserved for the router |
| `snmp` | none | Devices are keyed by OID, not slave_id — slave_id is a display label only |
| `opcua` | none | Devices are keyed by node, not slave_id — slave_id is a display label only |
| `mqtt` | none | Devices are keyed by topic, not slave_id — slave_id is a display label only |

Each protocol also gets its own `port` value (see `DeviceSummary.port`), so `(slave_id, port)` uniqueness is scoped per protocol — e.g. a Modbus device and a BACnet device can both use `slave_id=5`. For SNMP/OPC UA/MQTT the practical ceiling is host memory and per-adapter event-loop throughput, not a coded limit.

#### `DeviceSummary` (response — list items)

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Device ID |
| `template_id` | UUID | Template ID |
| `template_name` | string | Template name (joined) |
| `name` | string | Device name |
| `slave_id` | integer | Slave ID |
| `status` | string | `stopped`, `running`, or `error` |
| `port` | integer | Server-derived per protocol: Modbus 502, SNMP 10161, OPC UA 4840, BACnet 47808, MQTT 1883 (nominal — MQTT has no listening port; see Per-protocol Slave ID limits above) |
| `description` | string\|null | Description |
| `mqtt_publishing` | boolean | Whether MQTT publishing is enabled for this device |
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
| `oid` | string\|null | SNMP OID (populated for SNMP templates; `null` for Modbus) |
| `value` | float\|null | Current register value. `null` when the device is stopped or has not yet produced a tick. For live values, clients should subscribe to `/ws/monitor` rather than polling `GET /devices/{id}`. |

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

#### `POST /api/v1/devices/batch/start`

Batch start devices. Skips already-running devices.

**Request body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `device_ids` | UUID[] | no | `[]` | Device IDs to start. Empty = start all stopped devices |

**Response** `200 OK`
```json
{
  "success": true,
  "data": { "success_count": 5, "skipped_count": 2, "error_count": 0 },
  "message": "Started 5, skipped 2, errors 0"
}
```

---

#### `POST /api/v1/devices/batch/stop`

Batch stop devices. Skips already-stopped devices.

**Request body:** Same as batch start. Empty `device_ids` = stop all running devices.

**Response** `200 OK` — same `BatchActionResult` format.

---

#### `POST /api/v1/devices/batch/delete`

Batch delete devices. Skips running devices. `device_ids` is required (no "delete all").

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `device_ids` | UUID[] | yes | Device IDs to delete (must not be empty) |

**Response** `200 OK` — same `BatchActionResult` format.

**Error cases:**
- `422` — empty `device_ids`

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

#### `GET /api/v1/devices/{device_id}/write-events`

List recorded client write attempts for a device, newest first. The simulator is read-only: writes (Modbus FC05/06/15/16) are accepted-and-ignored, but each attempt is recorded in a per-device in-memory ring buffer (max 50). This is a **pure read** — it does not reset the unread count.

**Path param:** `device_id` (UUID)

**Response** `200 OK` — `ApiResponse[WriteEvent[]]`, where each `WriteEvent` is:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | datetime | When the write was received (UTC) |
| `operation` | string | Human-readable write operation label (e.g. `Write Register`, `Write Registers`, `Write Coil` for Modbus, `WriteProperty` for BACnet, `Write` for OPC UA) |
| `address` | int | Modbus register/coil address, or BACnet object instance |
| `values` | string[] | Stringified written values (Modbus words, coil `0`/`1`, or a BACnet float present-value) |
| `register_name` | string\|null | Matching register/object name, or `null` if the address maps to none |

**Error cases:**
- `404` — device not found

---

#### `POST /api/v1/devices/{device_id}/write-events/ack`

Reset the device's unread write count to 0. The event buffer itself is retained (the list endpoint still returns past events). Called by the UI when the write-events drawer is opened.

**Path param:** `device_id` (UUID)

**Response** `200 OK` — `ApiResponse[{ unread: 0 }]`

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

#### `GET /api/v1/simulation-profiles/template/{template_id}`

Download a blank profile JSON template for a given device template. Useful as a starting point for authoring a new profile offline before importing it back.

**Path param:** `template_id` (UUID)

**Response** `200 OK` — `application/json` file download

The response is a raw JSON body (not the standard `ApiResponse` envelope) served with `Content-Disposition: attachment; filename="<template_name>_blank_profile.json"`. The body contains `template_name` plus an empty/default `configs` array aligned with the template's register definitions.

**Error cases:**
- `404` — template not found

---

#### `GET /api/v1/simulation-profiles/{profile_id}/export`

Export an existing simulation profile as a downloadable JSON file.

**Path param:** `profile_id` (UUID)

**Response** `200 OK` — `application/json` file download

Raw JSON (not the `ApiResponse` envelope) served with `Content-Disposition: attachment; filename="<profile_name>.json"`. Same shape as the import format.

**Error cases:**
- `404` — profile not found

---

#### `POST /api/v1/simulation-profiles/import?template_id={uuid}`

Import a simulation profile from a JSON file upload.

**Query param:** `template_id` (UUID, required) — the template to attach the imported profile to. The template must already exist.

**Request body:** `multipart/form-data` with field `file` containing the profile JSON (format as produced by the export / blank template endpoints).

**Response** `201 Created` — `ApiResponse[SimulationProfileResponse]`

**Error cases:**
- `400` — invalid JSON file (`VALIDATION_ERROR`)
- `404` — template not found
- `409` — profile name already exists for this template
- `422` — profile JSON schema does not match the template

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

## Simulation Configuration

Base path: `/api/v1/devices/{device_id}`

Per-register simulation configuration and device-level communication fault control. "Simulation config" tells the engine how to generate values for each register; "fault" injects communication-layer problems into the Modbus protocol adapter without touching generated values.

For higher-level reusable parameter sets, see [Simulation Profiles](#simulation-profiles). Profiles are copied into these simulation configs at device-creation time.

### Schemas

#### `SimulationConfigCreate` (request — single register)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `register_name` | string | yes | — | Target register name (must exist in the device's template) |
| `data_mode` | string | yes | — | One of: `static`, `random`, `daily_curve`, `computed`, `accumulator` |
| `mode_params` | object | no | `{}` | Mode-specific parameters (shape depends on `data_mode`) |
| `is_enabled` | boolean | no | `true` | When `false`, the engine skips this register on each tick |
| `update_interval_ms` | integer | no | `1000` | Update interval per tick, must be between 100 and 60000 |

#### `SimulationConfigBatchSet` (request — whole device)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `configs` | `SimulationConfigCreate[]` | yes | Full replacement set for the device's simulation configs |

> `PUT` is a replace operation — any configs not in the request are deleted.

#### `SimulationConfigResponse` (response)

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Config ID |
| `device_id` | UUID | Owning device |
| `register_name` | string | Target register |
| `data_mode` | string | Active data mode |
| `mode_params` | object | Mode-specific parameters |
| `is_enabled` | boolean | Whether the engine processes this register |
| `update_interval_ms` | integer | Current update interval |
| `created_at` | datetime | ISO 8601 UTC |
| `updated_at` | datetime | ISO 8601 UTC |

#### `FaultConfigSet` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `fault_type` | string | yes | — | One of: `delay`, `timeout`, `exception`, `intermittent` |
| `params` | object | no | `{}` | Fault-specific parameters (see table below) |

**Fault params by type:**

| `fault_type` | Expected params |
|--------------|-----------------|
| `delay` | `delay_ms` (integer, default `500`, capped at `10000`) — extra latency added to each response |
| `timeout` | — (no params) — responses are suppressed so the client hits its own timeout |
| `exception` | `exception_code` (integer Modbus exception code, default `0x04` SLAVE_DEVICE_FAILURE) |
| `intermittent` | `failure_rate` (float between 0 and 1, default `0.5`) — probability of suppressing each request |

#### `FaultConfigResponse` (response)

| Field | Type | Description |
|-------|------|-------------|
| `fault_type` | string | Active fault type |
| `params` | object | Active fault parameters |

> Faults are held **in memory only** — they are cleared on backend restart.

### Endpoints

#### `GET /api/v1/devices/{device_id}/simulation`

List all simulation configs for a device.

**Path param:** `device_id` (UUID)

**Response** `200 OK` — `ApiResponse[SimulationConfigResponse[]]`

---

#### `PUT /api/v1/devices/{device_id}/simulation`

Replace the entire set of simulation configs for a device. Any existing config not present in the request body is deleted.

**Path param:** `device_id` (UUID)

**Request body:** `SimulationConfigBatchSet`

**Response** `200 OK` — `ApiResponse[SimulationConfigResponse[]]`

**Error cases:**
- `404` — device not found
- `422` — a `register_name` in the request does not exist in the device's template

---

#### `PATCH /api/v1/devices/{device_id}/simulation/{register_name}`

Upsert a single register's simulation config. Creates it if absent, updates otherwise.

**Path params:** `device_id` (UUID), `register_name` (string)

**Request body:** `SimulationConfigCreate` — the `register_name` in the body should match the path parameter.

**Response** `200 OK` — `ApiResponse[SimulationConfigResponse]`

**Error cases:**
- `404` — device not found
- `422` — register does not exist in the template

---

#### `DELETE /api/v1/devices/{device_id}/simulation`

Delete all simulation configs for a device.

**Path param:** `device_id` (UUID)

**Response** `200 OK`
```json
{ "success": true, "data": null, "message": "Simulation configs deleted successfully" }
```

**Error cases:**
- `404` — device not found

---

#### `PUT /api/v1/devices/{device_id}/fault`

Set (or replace) the active communication fault on a device.

**Path param:** `device_id` (UUID)

**Request body:** `FaultConfigSet`

**Response** `200 OK` — `ApiResponse[FaultConfigResponse]`

**Error cases:**
- `404` — device not found (`DEVICE_NOT_FOUND`)
- `422` — unknown `fault_type`, or a fault type the device's protocol does not
  support (`VALIDATION_ERROR`; each adapter declares its `supported_fault_types` —
  currently only MQTT excludes `exception`)

**Protocol-layer behavior:**

> **Protocol support:** all fault types apply to Modbus TCP, OPC UA, SNMP, and BACnet.
> MQTT supports `delay` / `timeout` / `intermittent` only — `exception` returns
> `422 VALIDATION_ERROR` because MQTT is publish-only (no request/response channel
> to return a protocol error on). For BACnet, `timeout` / `intermittent` also
> suppress Who-Is replies (the device disappears from discovery while faulted).

For **Modbus TCP** devices the fault is applied pull-based (no adapter action on this call; `trace_pdu` polls `fault_simulator` on every request).

For **OPC UA** devices the fault is applied push-based at the protocol layer immediately on this call by attaching a value callback to every Variable node of the device. Fault-type semantics:

| `fault_type` | OPC UA client observation |
|---|---|
| `exception` | Every read returns `BadDeviceFailure` status code; no value |
| `timeout` | Every read returns `BadTimeout` status code; no value |
| `delay` | Read succeeds with a Good status after a server-side wait of `delay_ms` ms (bounded to 10 000 ms); returns the latest cached register value. The wait is applied asynchronously per session (PreRead hook) and does not block other clients, protocols, or the REST/WS layers |
| `intermittent` | Each read randomly returns `BadCommunicationError` with probability `failure_rate`, or the latest cached value with Good status otherwise |

While a fault is active, the simulation engine continues updating the per-node value cache; the cached value is served as-is once the fault is cleared. OPC UA subscriptions are paused during a fault (the value callback bypasses subscription notifications) and automatically resume on fault clear.

For **SNMP** devices the fault is applied pull-based; the `_DynamicMibController` and fault-aware command responders poll `fault_simulator` on every GET/GETNEXT/GETBULK. `exception` returns a `genErr` response; `delay` defers the entire response via `loop.call_later` (non-blocking); `timeout`/`intermittent` drop the response entirely.

For **BACnet** devices the fault is applied pull-based; `_DeviceApplication` read handlers (`do_ReadPropertyRequest` / `do_ReadPropertyMultipleRequest`) poll `fault_simulator` on every inbound request. `exception` returns a BACnet Error `device/operationalProblem`; `timeout`/`intermittent` additionally suppress Who-Is replies, making the device fully invisible to discovery clients.

For **MQTT** devices the fault gate runs inside `_publish_loop`. `timeout` stops all publishes; `intermittent` randomly skips publishes with probability `failure_rate`; `delay` publishes after sleeping `delay_ms` ms (bounded to 10 000 ms). Skipped publishes (timeout/intermittent) are counted as request + error in per-device statistics; delayed publishes proceed normally and count as success.

---

#### `GET /api/v1/devices/{device_id}/fault`

Get the currently active fault for a device.

**Path param:** `device_id` (UUID)

**Response** `200 OK` — `ApiResponse[FaultConfigResponse | null]`

Returns `data: null` when no fault is active.

---

#### `DELETE /api/v1/devices/{device_id}/fault`

Clear the active fault for a device.

**Path param:** `device_id` (UUID)

**Response** `200 OK`
```json
{ "success": true, "data": null, "message": "Fault cleared successfully" }
```

**Error cases:**
- `404` — device not found (`DEVICE_NOT_FOUND`)

**Protocol-layer behavior:** For OPC UA devices, clearing the fault detaches the value callbacks by re-writing the cached value to each Variable node (atomically restores the stored value, clears the callback, and resumes subscriptions). For Modbus devices this is a no-op at the adapter level.

---

## Anomaly Injection

Base path: `/api/v1/devices/{device_id}`

Two mechanisms are offered on top of the simulation engine:

1. **Real-time injection** — mutate generated values immediately via in-memory state. Lost on backend restart. Use `POST /anomaly`, `GET /anomaly`, `DELETE /anomaly`.
2. **Schedules** — persist timeline entries in the database so anomalies trigger automatically at fixed offsets from device start. Use `.../anomaly/schedules`.

Both support the same five anomaly types: `spike`, `drift`, `flatline`, `out_of_range`, `data_loss`.

### Schemas

#### `AnomalyInjectRequest` (request — real-time)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `register_name` | string | yes | — | Target register |
| `anomaly_type` | string | yes | — | One of: `spike`, `drift`, `flatline`, `out_of_range`, `data_loss` |
| `anomaly_params` | object | no | `{}` | Type-specific params (see table below) |

**Anomaly params by type:**

| `anomaly_type` | Required params |
|----------------|-----------------|
| `spike` | `multiplier` (float > 0), `probability` (float 0–1) |
| `drift` | `drift_per_second` (float), `max_drift` (float > 0) |
| `flatline` | — |
| `out_of_range` | `value` (float — the value to return) |
| `data_loss` | — |

#### `AnomalyActiveResponse` (response — real-time state)

| Field | Type | Description |
|-------|------|-------------|
| `register_name` | string | Target register |
| `anomaly_type` | string | Active anomaly type |
| `anomaly_params` | object | Active parameters |

#### `AnomalyScheduleCreate` (request — schedule entry)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `register_name` | string | yes | — | Target register |
| `anomaly_type` | string | yes | — | One of the five types above |
| `anomaly_params` | object | no | `{}` | Same validation rules as real-time injection |
| `trigger_after_seconds` | integer | yes | — | Seconds after device start to fire the anomaly (≥ 0) |
| `duration_seconds` | integer | yes | — | How long the anomaly stays active once fired (> 0) |
| `is_enabled` | boolean | no | `true` | Disabled schedules are stored but not loaded |

#### `AnomalyScheduleBatchSet` (request — whole device)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schedules` | `AnomalyScheduleCreate[]` | yes | Full replacement set for this device's schedules |

#### `AnomalyScheduleResponse` (response)

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Schedule ID |
| `device_id` | UUID | Owning device |
| `register_name` | string | Target register |
| `anomaly_type` | string | Type |
| `anomaly_params` | object | Parameters |
| `trigger_after_seconds` | integer | Offset from start |
| `duration_seconds` | integer | How long the anomaly lasts |
| `is_enabled` | boolean | Whether loaded on device start |
| `created_at` | datetime | ISO 8601 UTC |
| `updated_at` | datetime | ISO 8601 UTC |

### Endpoints — Real-time Injection

#### `POST /api/v1/devices/{device_id}/anomaly`

Inject an anomaly on a register immediately (in-memory, lost on restart).

**Path param:** `device_id` (UUID)

**Request body:** `AnomalyInjectRequest`

**Response** `200 OK` — `ApiResponse[AnomalyActiveResponse]`

**Error cases:**
- `422` — unknown `anomaly_type`, missing required params, or param value out of range

---

#### `GET /api/v1/devices/{device_id}/anomaly`

List all currently active (real-time) anomalies on the device.

**Path param:** `device_id` (UUID)

**Response** `200 OK` — `ApiResponse[AnomalyActiveResponse[]]`

---

#### `DELETE /api/v1/devices/{device_id}/anomaly`

Clear all active anomalies on the device. Does not touch scheduled entries in the DB.

**Path param:** `device_id` (UUID)

**Response** `200 OK`
```json
{ "success": true, "data": null, "message": "All anomalies cleared" }
```

---

#### `DELETE /api/v1/devices/{device_id}/anomaly/{register_name}`

Remove the active anomaly from a specific register.

**Path params:** `device_id` (UUID), `register_name` (string)

**Response** `200 OK`
```json
{ "success": true, "data": null, "message": "Anomaly removed" }
```

> The route is registered after the `.../anomaly/schedules` routes so that `schedules` is never matched as a register name.

---

### Endpoints — Schedules (persisted)

#### `GET /api/v1/devices/{device_id}/anomaly/schedules`

List all scheduled anomalies for a device.

**Path param:** `device_id` (UUID)

**Response** `200 OK` — `ApiResponse[AnomalyScheduleResponse[]]`

---

#### `PUT /api/v1/devices/{device_id}/anomaly/schedules`

Replace the entire set of anomaly schedules for a device.

**Path param:** `device_id` (UUID)

**Request body:** `AnomalyScheduleBatchSet`

**Response** `200 OK` — `ApiResponse[AnomalyScheduleResponse[]]`

**Error cases:**
- `422` — unknown `anomaly_type`, invalid `trigger_after_seconds` / `duration_seconds`, or missing required anomaly params

---

#### `DELETE /api/v1/devices/{device_id}/anomaly/schedules`

Delete all anomaly schedules for a device.

**Path param:** `device_id` (UUID)

**Response** `200 OK`
```json
{ "success": true, "data": null, "message": "All schedules deleted" }
```

---

## MQTT

Base path: `/api/v1/system` (brokers) and `/api/v1/system/devices/{device_id}` (publish configs)

GhostMeter can publish simulated device data to multiple external MQTT brokers
simultaneously (issue #87). Brokers are named, multi-row configuration; each
device holds one publish config per broker it publishes to, with independent
topic / interval / QoS / enabled state. One broker's failure or reconnect never
affects publishing to other brokers.

> **Breaking change (multi-broker rework):** the former single-settings
> endpoints `GET /api/v1/system/mqtt` and `PUT /api/v1/system/mqtt` were
> removed, and the per-device endpoints now take a `broker_id`.

### Schemas

#### `MqttBrokerWrite` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | Unique broker name (≤ 100 chars) |
| `host` | string | no | `"localhost"` | Broker hostname |
| `port` | integer | no | `1883` | Broker port (1–65535) |
| `username` | string | no | `""` | Auth username |
| `password` | string | no | `""` | Auth password (`"****"` to keep existing) |
| `client_id` | string | no | `"ghostmeter"` | MQTT client identifier |
| `use_tls` | boolean | no | `false` | Use TLS connection |

#### `MqttBrokerRead` (response)

Same fields as write plus `id` (UUID string) and `connected` (boolean, live
adapter state); `password` is masked as `"****"` when non-empty.

#### `MqttPublishConfigWrite` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `topic_template` | string | no | `"telemetry/{device_name}"` | MQTT topic template |
| `payload_mode` | string | no | `"batch"` | `"batch"` or `"per_register"` |
| `publish_interval_seconds` | integer | no | `5` | Publish interval (≥ 1 second) |
| `qos` | integer | no | `0` | MQTT QoS level (0, 1, or 2) |
| `retain` | boolean | no | `false` | MQTT retain flag |

**Topic template variables:** `{device_name}`, `{slave_id}`, `{template_name}`, `{register_name}` (per_register mode only)

#### `MqttPublishConfigRead` (response)

Same fields as write plus `device_id`, `broker_id`, `broker_name` (strings) and `enabled` (boolean).

#### `MqttTestResult` (response)

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Whether connection succeeded |
| `message` | string | Success or error message |

### Endpoints

#### `GET /api/v1/system/mqtt/brokers`

List all MQTT brokers (ordered by name) with their live connection state.

**Response** `200 OK` — `ApiResponse[list[MqttBrokerRead]]`

---

#### `POST /api/v1/system/mqtt/brokers`

Create an MQTT broker. The running adapter connects to it immediately; a
failed connection still saves the broker (shown as `connected: false`).

**Request body:** `MqttBrokerWrite`

**Response** `201 Created` — `ApiResponse[MqttBrokerRead]`

**Error cases:**
- `409 DUPLICATE_NAME` — another broker already uses this name

---

#### `PUT /api/v1/system/mqtt/brokers/{broker_id}`

Update a broker. Only this broker's adapter client reconnects, and only its
publish tasks (enabled configs on running devices) are restarted — other
brokers keep publishing untouched. A failed reconnect still saves the settings.

**Path param:** `broker_id` (UUID)

**Request body:** `MqttBrokerWrite`

**Response** `200 OK` — `ApiResponse[MqttBrokerRead]`

**Error cases:**
- `404` — broker not found
- `409 DUPLICATE_NAME` — another broker already uses this name

---

#### `DELETE /api/v1/system/mqtt/brokers/{broker_id}`

Delete a broker and disconnect its client.

**Path param:** `broker_id` (UUID)

**Response** `200 OK`

**Error cases:**
- `404` — broker not found
- `409 BROKER_IN_USE` — device publish configs still reference this broker; delete those first

---

#### `POST /api/v1/system/mqtt/test`

Test MQTT broker connection with provided settings (does not save).

**Request body:** `MqttBrokerWrite`

**Response** `200 OK` — `ApiResponse[MqttTestResult]`

---

#### `GET /api/v1/system/devices/{device_id}/mqtt`

List MQTT publish configs for a device (one per broker, ordered by broker
name). Empty list if none configured.

**Path param:** `device_id` (UUID)

**Response** `200 OK` — `ApiResponse[list[MqttPublishConfigRead]]`

---

#### `PUT /api/v1/system/devices/{device_id}/mqtt/{broker_id}`

Create or update the publish config for one (device, broker) pair.

**Path params:** `device_id`, `broker_id` (UUID)

**Request body:** `MqttPublishConfigWrite`

**Response** `200 OK` — `ApiResponse[MqttPublishConfigRead]`

**Error cases:**
- `404` — broker not found

---

#### `DELETE /api/v1/system/devices/{device_id}/mqtt/{broker_id}`

Delete the publish config for one (device, broker) pair (its publish task is
stopped best-effort).

**Path params:** `device_id`, `broker_id` (UUID)

**Response** `200 OK`

**Error cases:**
- `404` — config not found

---

#### `POST /api/v1/system/devices/{device_id}/mqtt/start`

Start MQTT publishing for a device. With the optional `broker_id` query
parameter, only that (device, broker) pair starts; without it, **all** of the
device's configs start. Each started config is marked `enabled`; a pair that
fails to start (e.g. its broker is disconnected) gets its `enabled` flag
reverted and is reported in the response `message` — other pairs still start.
Device metadata (name / slave ID / template name) is handed to the adapter
before the publish loops start, so topic templates render correctly.

**Path param:** `device_id` (UUID)
**Query param:** `broker_id` (UUID, optional)

**Response** `200 OK` — `ApiResponse[list[MqttPublishConfigRead]]` (the started configs)

**Error cases:**
- `404` — no publish config found (for this broker, when given)
- `500 MQTT_ERROR` — adapter not registered, or every targeted pair failed to start

---

#### `POST /api/v1/system/devices/{device_id}/mqtt/stop`

Stop MQTT publishing for a device — one broker with the optional `broker_id`
query parameter, otherwise all of the device's configs.

**Path param:** `device_id` (UUID)
**Query param:** `broker_id` (UUID, optional)

**Response** `200 OK` — `ApiResponse[list[MqttPublishConfigRead]]` (the stopped configs)

**Error cases:**
- `404` — no publish config found (for this broker, when given)

---

## System

### Export Configuration

#### `GET /api/v1/system/export`

Exports the full system configuration (templates, devices, simulation configs, anomaly schedules, MQTT settings) as a JSON file download.

**Response** `200 OK` — JSON file with `Content-Disposition: attachment`

```json
{
  "version": "1.0",
  "exported_at": "2026-03-19T12:00:00+00:00",
  "templates": [ "..." ],
  "devices": [ "..." ],
  "simulation_configs": [ "..." ],
  "anomaly_schedules": [ "..." ],
  "mqtt_brokers": [
    {
      "name": "emqx-production",
      "host": "broker.example.com",
      "port": 1883,
      "username": "admin",
      "password": "secret",
      "client_id": "ghostmeter",
      "use_tls": false
    }
  ],
  "mqtt_publish_configs": [
    {
      "device_name": "Meter-01",
      "broker_name": "emqx-production",
      "topic_template": "telemetry/{device_name}",
      "payload_mode": "batch",
      "publish_interval_seconds": 5,
      "qos": 0,
      "retain": false,
      "enabled": false
    }
  ]
}
```

> `mqtt_brokers` and `mqtt_publish_configs` are `[]` when nothing is
> configured; both are optional in the import payload. **Legacy exports**
> (single `mqtt_broker_settings` object, configs without `broker_name`) still
> import: the settings become a broker named `default`, which is also where
> the legacy configs attach. Configs referencing an unknown `broker_name` are
> skipped.

---

### Import Configuration

#### `POST /api/v1/system/import`

Imports a system configuration snapshot. Upserts templates by name, devices by (slave_id, port), MQTT brokers by name. Built-in templates are skipped.

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
    "anomaly_schedules_set": 3,
    "mqtt_brokers_set": 1,
    "mqtt_publish_configs_set": 2
  },
  "message": "Import completed successfully"
}
```

**Errors:**
- `422` — unsupported version, device references unknown template, invalid data

---

## Scenarios

Base path: `/api/v1/scenarios`

Scenarios are reusable anomaly injection timelines bound to a device template. Each scenario contains a sequence of steps that trigger anomalies on specific registers at defined times.

### Schemas

#### `ScenarioStepCreate` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `register_name` | string | yes | — | Target register name (must match template register) |
| `anomaly_type` | string | yes | — | One of: `spike`, `drift`, `flatline`, `out_of_range`, `data_loss` |
| `anomaly_params` | object | no | `{}` | Anomaly-specific parameters |
| `trigger_at_seconds` | integer | yes | — | Seconds from scenario start when this step triggers (>= 0) |
| `duration_seconds` | integer | yes | — | How long the anomaly lasts in seconds (> 0) |
| `sort_order` | integer | no | `0` | Display order |

#### `ScenarioCreate` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `template_id` | UUID | yes | — | Template this scenario belongs to |
| `name` | string | yes | — | Scenario name (unique per template) |
| `description` | string\|null | no | `null` | Description |
| `steps` | ScenarioStepCreate[] | yes | — | Array of scenario steps |

> `total_duration_seconds` is computed from steps automatically.

#### `ScenarioUpdate` (request)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | Scenario name |
| `description` | string\|null | no | `null` | Description |
| `steps` | ScenarioStepCreate[] | yes | — | Full replacement of steps |

#### `ScenarioSummary` (response -- list items)

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Scenario ID |
| `template_id` | UUID | Template ID |
| `template_name` | string | Template name (joined) |
| `name` | string | Scenario name |
| `description` | string\|null | Description |
| `is_builtin` | boolean | `true` for seed-loaded scenarios |
| `total_duration_seconds` | integer | Total duration in seconds |
| `created_at` | datetime | ISO 8601 UTC |
| `updated_at` | datetime | ISO 8601 UTC |

#### `ScenarioDetail` (response -- single item)

Same as `ScenarioSummary` plus `steps: ScenarioStepResponse[]`.

#### `ScenarioStepResponse` (response)

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Step ID |
| `register_name` | string | Target register name |
| `anomaly_type` | string | Anomaly type |
| `anomaly_params` | object | Anomaly parameters |
| `trigger_at_seconds` | integer | Trigger time offset (seconds) |
| `duration_seconds` | integer | Duration (seconds) |
| `sort_order` | integer | Display order |

#### `ScenarioExport` (request/response)

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Scenario name |
| `description` | string\|null | Description |
| `template_name` | string | Template name (for matching on import) |
| `steps` | ScenarioStepCreate[] | Array of steps |

#### `ScenarioExecutionStatus` (response)

| Field | Type | Description |
|-------|------|-------------|
| `scenario_id` | UUID | Scenario ID |
| `scenario_name` | string | Scenario name |
| `status` | string | `running` or `completed` |
| `elapsed_seconds` | integer | Seconds elapsed since start |
| `total_duration_seconds` | integer | Total scenario duration |
| `active_steps` | ActiveStepStatus[] | Currently active anomaly steps |

#### `ActiveStepStatus`

| Field | Type | Description |
|-------|------|-------------|
| `register_name` | string | Register with active anomaly |
| `anomaly_type` | string | Anomaly type |
| `remaining_seconds` | integer | Seconds until anomaly ends |

---

### Endpoints

#### `GET /api/v1/scenarios`

List all scenarios, optionally filtered by template.

**Query param:** `template_id` (UUID, optional)

**Response** `200 OK` -- `ApiResponse[ScenarioSummary[]]`

---

#### `POST /api/v1/scenarios`

Create a new scenario with steps.

**Request body:** `ScenarioCreate`

**Response** `201 Created` -- `ApiResponse[ScenarioDetail]`

**Error cases:**
- `404` -- template not found
- `409` -- duplicate name for this template
- `422` -- invalid step anomaly params: steps enforce the same rules as
  real-time injection and schedules (required params per anomaly type;
  spike `multiplier > 0`, `probability` in [0,1]; drift `max_drift > 0` —
  `max_drift` is a magnitude, drift direction comes from
  `drift_per_second`'s sign). Applies to create, update, and import.

---

#### `GET /api/v1/scenarios/{scenario_id}`

Get a scenario with all steps.

**Path param:** `scenario_id` (UUID)

**Response** `200 OK` -- `ApiResponse[ScenarioDetail]`

**Error cases:**
- `404` -- scenario not found

---

#### `PUT /api/v1/scenarios/{scenario_id}`

Update a scenario (full replace of steps). Built-in scenarios cannot be updated.

**Path param:** `scenario_id` (UUID)

**Request body:** `ScenarioUpdate`

**Response** `200 OK` -- `ApiResponse[ScenarioDetail]`

**Error cases:**
- `404` -- scenario not found
- `403` -- cannot modify a built-in scenario

---

#### `DELETE /api/v1/scenarios/{scenario_id}`

Delete a scenario. Built-in scenarios cannot be deleted.

**Path param:** `scenario_id` (UUID)

**Response** `200 OK`
```json
{ "success": true, "data": null, "message": "Scenario deleted" }
```

**Error cases:**
- `404` -- scenario not found
- `409` -- cannot delete a built-in scenario

---

#### `POST /api/v1/scenarios/{scenario_id}/export`

Export a scenario as portable JSON (template referenced by name, not ID).

**Path param:** `scenario_id` (UUID)

**Response** `200 OK` -- `ApiResponse[ScenarioExport]`

**Error cases:**
- `404` -- scenario not found

---

#### `POST /api/v1/scenarios/import`

Import a scenario from JSON. Template is matched by name.

**Request body:** `ScenarioExport`

**Response** `201 Created` -- `ApiResponse[ScenarioDetail]`

**Error cases:**
- `404` -- template not found by name
- `409` -- duplicate scenario name for the template

---

### Scenario Execution

Execution endpoints are mounted under `/api/v1/devices`.

#### `POST /api/v1/devices/{device_id}/scenario/{scenario_id}/start`

Start executing a scenario on a running device. The scenario template must match the device template.

**Path params:** `device_id` (UUID), `scenario_id` (UUID)

**Response** `200 OK`
```json
{ "success": true, "data": null, "message": "Scenario started" }
```

**Error cases:**
- `409` -- device not running (`DEVICE_NOT_RUNNING`)
- `409` -- scenario already running on device (`SCENARIO_ALREADY_RUNNING`)
- `409` -- scenario template does not match device template (`TEMPLATE_MISMATCH`)

---

#### `POST /api/v1/devices/{device_id}/scenario/stop`

Stop a running scenario on a device.

**Path param:** `device_id` (UUID)

**Response** `200 OK`
```json
{ "success": true, "data": null, "message": "Scenario stopped" }
```

---

#### `GET /api/v1/devices/{device_id}/scenario/status`

Get real-time execution status of a running scenario.

**Path param:** `device_id` (UUID)

**Response** `200 OK` -- `ApiResponse[ScenarioExecutionStatus]`

**Error cases:**
- `404` -- no scenario running on this device (`NO_RUNNING_SCENARIO`)
