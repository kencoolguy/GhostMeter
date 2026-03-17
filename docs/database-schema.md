# Database Schema

## Overview

GhostMeter uses PostgreSQL 16 with SQLAlchemy 2.0 async ORM. All primary keys are UUID. Timestamps are stored in UTC with timezone info.

---

## Tables

### `device_templates`

Defines a type of device (e.g. "Three-Phase Energy Meter") including its protocol and register map.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | `uuid_generate_v4()` | Primary key |
| `name` | VARCHAR(100) | NOT NULL | — | Unique template name |
| `protocol` | VARCHAR(50) | NOT NULL | `'modbus_tcp'` | Protocol identifier (e.g. `modbus_tcp`) |
| `description` | TEXT | NULL | — | Human-readable description |
| `is_builtin` | BOOLEAN | NOT NULL | `false` | `true` for seed-loaded templates; these are immutable |
| `created_at` | TIMESTAMPTZ | NOT NULL | `now()` | Creation time (UTC) |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `now()` | Last update time (UTC) |

**Constraints:**
- `UNIQUE (name)` — template names must be globally unique

**Relations:**
- Has many `register_definitions` (cascade delete)

---

### `register_definitions`

A single Modbus register entry within a device template. Stores address, data type, scaling, and metadata.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | `uuid_generate_v4()` | Primary key |
| `template_id` | UUID | NOT NULL | — | FK → `device_templates.id` (CASCADE DELETE) |
| `name` | VARCHAR(100) | NOT NULL | — | Register name (unique per template) |
| `address` | INTEGER | NOT NULL | — | 0-based Modbus register address |
| `function_code` | SMALLINT | NOT NULL | `3` | Modbus function code: `3` (Holding) or `4` (Input) |
| `data_type` | VARCHAR(20) | NOT NULL | — | One of: `int16`, `uint16`, `int32`, `uint32`, `float32`, `float64` |
| `byte_order` | VARCHAR(30) | NOT NULL | `'big_endian'` | One of: `big_endian`, `little_endian`, `big_endian_word_swap`, `little_endian_word_swap` |
| `scale_factor` | FLOAT | NOT NULL | `1.0` | Multiplier applied to raw register value |
| `unit` | VARCHAR(20) | NULL | — | Physical unit (e.g. `V`, `A`, `kWh`) |
| `description` | TEXT | NULL | — | Human-readable description of the register |
| `sort_order` | INTEGER | NOT NULL | `0` | Display/iteration order |

**Constraints:**
- `UNIQUE (template_id, name)` — register names must be unique within a template
- `UNIQUE (template_id, address, function_code)` — no two registers with same address + FC in same template

**Relations:**
- Belongs to `device_templates`

---

### `device_instances`

A virtual device instance created from a template. Devices bind to a Modbus slave ID and port, and have a status state machine (stopped/running/error).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | `uuid_generate_v4()` | Primary key |
| `template_id` | UUID | NOT NULL | — | FK → `device_templates.id` (RESTRICT) |
| `name` | VARCHAR(200) | NOT NULL | — | Device name |
| `slave_id` | INTEGER | NOT NULL | — | Modbus Slave ID (1–247) |
| `status` | VARCHAR(20) | NOT NULL | `'stopped'` | `stopped`, `running`, or `error` |
| `port` | INTEGER | NOT NULL | `502` | Modbus TCP port |
| `description` | TEXT | NULL | — | Human-readable description |
| `created_at` | TIMESTAMPTZ | NOT NULL | `now()` | Creation time (UTC) |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `now()` | Last update time (UTC) |

**Constraints:**
- `UNIQUE (slave_id, port)` — same slave ID cannot be used twice on the same port
- `FK template_id → device_templates.id ON DELETE RESTRICT` — templates with devices cannot be deleted

**Relations:**
- Belongs to `device_templates` (RESTRICT — must delete devices before deleting template)

**Status State Machine:**
- `stopped` → `running` (via POST /start)
- `running` → `stopped` (via POST /stop)
- `error` → `stopped` (via POST /stop)
- `error` state cannot be started (only stopped)
- Running devices cannot be deleted or updated

---

## Register Address Notes

- Addresses are **0-based** (following the pymodbus convention, not the legacy 1-based Modbus PDU convention)
- `float32` and `int32`/`uint32` occupy **2 consecutive registers** (`address` and `address + 1`)
- `float64` occupies **4 consecutive registers**
- The service layer validates that no two registers within the same template and function code have overlapping address ranges

---

## Migrations

Managed by Alembic. Migration files are in `backend/alembic/versions/`.

| Revision | Description |
|----------|-------------|
| `448f2e5c6613` | Create device_templates and register_definitions tables |
| `d013e48e688a` | Add device_instances table with FK RESTRICT and unique (slave_id, port) |
