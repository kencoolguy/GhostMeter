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
| `oid` | VARCHAR(200) | NULL | — | SNMP OID string (e.g. `1.3.6.1.2.1.33.1.2.1.0`). Null for Modbus registers. |

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

### `simulation_profiles`

Reusable sets of simulation parameters bound to a device template. Built-in profiles are loaded from seed data at startup.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | `uuid_generate_v4()` | Primary key |
| `template_id` | UUID | NOT NULL | — | FK → `device_templates.id` (CASCADE DELETE) |
| `name` | VARCHAR(200) | NOT NULL | — | Profile name (unique per template) |
| `description` | TEXT | NULL | — | Human-readable description |
| `is_builtin` | BOOLEAN | NOT NULL | `false` | `true` for seed-loaded profiles; configs are immutable |
| `is_default` | BOOLEAN | NOT NULL | `false` | Auto-applied on device creation |
| `configs` | JSONB | NOT NULL | — | Array of register simulation config entries |
| `created_at` | TIMESTAMPTZ | NOT NULL | `now()` | Creation time (UTC) |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `now()` | Last update time (UTC) |

**Constraints:**
- `UNIQUE (template_id, name)` — profile names must be unique within a template
- `UNIQUE (template_id) WHERE is_default = true` — at most one default profile per template (partial unique index)

**Relations:**
- Belongs to `device_templates` (CASCADE — deleting a template deletes its profiles)

---

### `mqtt_broker_settings`

Global MQTT broker connection settings. At most one row exists.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | `uuid_generate_v4()` | Primary key |
| `host` | VARCHAR(255) | NOT NULL | `'localhost'` | Broker hostname |
| `port` | INTEGER | NOT NULL | `1883` | Broker port |
| `username` | VARCHAR(255) | NOT NULL | `''` | Auth username |
| `password` | VARCHAR(255) | NOT NULL | `''` | Auth password |
| `client_id` | VARCHAR(255) | NOT NULL | `'ghostmeter'` | MQTT client identifier |
| `use_tls` | BOOLEAN | NOT NULL | `false` | Use TLS connection |

---

### `mqtt_publish_configs`

Per-device MQTT publish configuration. One config per device.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | `uuid_generate_v4()` | Primary key |
| `device_id` | UUID | NOT NULL | — | FK → `device_instances.id` (CASCADE DELETE) |
| `topic_template` | VARCHAR(500) | NOT NULL | `'telemetry/{device_name}'` | MQTT topic template with variables |
| `payload_mode` | VARCHAR(20) | NOT NULL | `'batch'` | `batch` or `per_register` |
| `publish_interval_seconds` | INTEGER | NOT NULL | `5` | Publish interval in seconds |
| `qos` | INTEGER | NOT NULL | `0` | MQTT QoS level (0, 1, or 2) |
| `retain` | BOOLEAN | NOT NULL | `false` | MQTT retain flag |
| `enabled` | BOOLEAN | NOT NULL | `false` | Whether publishing is active |

**Constraints:**
- `UNIQUE (device_id)` — one publish config per device
- `FK device_id → device_instances.id ON DELETE CASCADE` — config is deleted when device is deleted

---

### `scenarios`

Reusable anomaly injection timelines bound to a device template. Built-in scenarios are loaded from seed data at startup.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | `uuid_generate_v4()` | Primary key |
| `template_id` | UUID | NOT NULL | — | FK → `device_templates.id` (CASCADE DELETE) |
| `name` | VARCHAR(255) | NOT NULL | — | Scenario name (unique per template) |
| `description` | TEXT | NULL | — | Human-readable description |
| `is_builtin` | BOOLEAN | NOT NULL | `false` | `true` for seed-loaded scenarios; these cannot be deleted |
| `total_duration_seconds` | INTEGER | NOT NULL | — | Total scenario duration in seconds |
| `created_at` | TIMESTAMPTZ | NOT NULL | `now()` | Creation time (UTC) |
| `updated_at` | TIMESTAMPTZ | NOT NULL | `now()` | Last update time (UTC) |

**Constraints:**
- `UNIQUE (template_id, name)` — scenario names must be unique within a template

**Relations:**
- Belongs to `device_templates` (CASCADE — deleting a template deletes its scenarios)
- Has many `scenario_steps` (cascade delete)

---

### `scenario_steps`

A single anomaly injection step within a scenario. Defines which register gets what anomaly, when it triggers, and how long it lasts.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `id` | UUID | NOT NULL | `uuid_generate_v4()` | Primary key |
| `scenario_id` | UUID | NOT NULL | — | FK → `scenarios.id` (CASCADE DELETE) |
| `register_name` | VARCHAR(100) | NOT NULL | — | Target register name (must match template register) |
| `anomaly_type` | VARCHAR(50) | NOT NULL | — | One of: `spike`, `drift`, `flatline`, `out_of_range`, `data_loss` |
| `anomaly_params` | JSONB | NOT NULL | `{}` | Anomaly-specific parameters |
| `trigger_at_seconds` | INTEGER | NOT NULL | — | Seconds from scenario start when this step triggers |
| `duration_seconds` | INTEGER | NOT NULL | — | How long the anomaly lasts (seconds) |
| `sort_order` | INTEGER | NOT NULL | `0` | Display/iteration order |

**Constraints:**
- `FK scenario_id → scenarios.id ON DELETE CASCADE`

**Relations:**
- Belongs to `scenarios`

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
| `4e3e82ebbef8` | Add simulation_configs table |
| `d3e65808cf1d` | Add anomaly_schedules table |
| `8c0da865d279` | Add simulation_profiles table |
| `eda1e6420ebd` | Add mqtt_broker_settings and mqtt_publish_configs tables |
| `b2a1062d8287` | Merge simulation_profiles and mqtt migrations |
| `884c7934de25` | Add oid column to register_definitions |
| `6e6c8a4265de` | Add scenarios and scenario_steps tables |
