# Simulation Profiles — Design Spec

**Date**: 2026-03-24
**Status**: Approved
**Related Issue**: #13 (frontend profile selector — future iteration)

## Problem

When a device is created from a template, all register values default to 0. Users must manually configure simulation parameters for every register via API before the device produces meaningful data. This is a poor out-of-box experience.

## Solution

Introduce a `simulation_profiles` table that stores reusable sets of simulation parameters. Built-in profiles ship with physically consistent, time-aware default data for each template. Profiles are automatically applied when creating devices.

## Requirements Summary

- Independent `simulation_profiles` DB table (not embedded in template)
- Auto-apply default profile on device creation; allow override or opt-out
- Profile is copied into `simulation_configs` at apply time (no ongoing link)
- Data must be physically consistent (e.g., `power = voltage × current`) and include daily curves
- MVP: one "Normal Operation" profile per built-in template (3 total)

---

## DB Schema

### New Table: `simulation_profiles`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | |
| `template_id` | UUID | FK → device_templates, NOT NULL | Bound template |
| `name` | VARCHAR(200) | NOT NULL | e.g., "Normal Operation" |
| `description` | TEXT | | |
| `is_builtin` | BOOLEAN | DEFAULT false | Built-in profiles cannot be deleted |
| `is_default` | BOOLEAN | DEFAULT false | Auto-applied on device creation |
| `configs` | JSONB | NOT NULL | Array of register simulation configs |
| `created_at` | TIMESTAMP | DEFAULT now() | |
| `updated_at` | TIMESTAMP | DEFAULT now(), on update | |

**Constraints**:
- At most one `is_default=true` per `template_id`. Enforced via PostgreSQL partial unique index: `CREATE UNIQUE INDEX uq_simulation_profiles_default ON simulation_profiles (template_id) WHERE is_default = true`.
- `(template_id, name)` should be unique. Enforced via unique constraint to prevent duplicate profile names within a template.

### `configs` JSONB Structure

Each element matches the existing `SimulationConfigCreate` schema:

```json
[
  {
    "register_name": "voltage_l1",
    "data_mode": "random",
    "mode_params": {"base": 220, "amplitude": 3, "distribution": "gaussian"},
    "update_interval_ms": 1000,
    "is_enabled": true
  }
]
```

---

## API Endpoints

### New: Simulation Profile CRUD

All under `/api/v1/simulation-profiles`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/simulation-profiles?template_id=uuid` | List profiles for a template |
| `GET` | `/simulation-profiles/{id}` | Get single profile |
| `POST` | `/simulation-profiles` | Create custom profile |
| `PUT` | `/simulation-profiles/{id}` | Update profile (builtin: name/description only) |
| `DELETE` | `/simulation-profiles/{id}` | Delete (builtin cannot be deleted) |

### Modified: Device Creation

`POST /api/v1/devices` — add optional `profile_id` field:

```json
{
  "template_id": "...",
  "name": "...",
  "slave_id": 1,
  "port": 502,
  "profile_id": "uuid-or-null"
}
```

Behavior:
- `profile_id` present with UUID → apply that profile (404 if not found)
- `profile_id` absent → auto-apply template's `is_default=true` profile
- `profile_id` explicitly `null` → skip, no profile applied (all registers = 0)

**Pydantic modeling note**: To distinguish "absent" from "explicitly null", use a sentinel pattern. Define `profile_id` with a `UNSET` sentinel default, then check `"profile_id" in data.model_fields_set` to detect explicit presence. Example:

```python
_UNSET = object()

class DeviceCreate(BaseModel):
    # ... existing fields ...
    profile_id: UUID | None = None  # None = auto-apply default

    # Use model_fields_set to detect explicit null:
    # "profile_id" not in model_fields_set → absent → auto-apply default
    # "profile_id" in model_fields_set and value is None → explicit null → skip
    # "profile_id" in model_fields_set and value is UUID → apply that profile
```

`POST /api/v1/devices/batch` — same `profile_id` field added.

---

## Apply Mechanism

```
create_device(data)
  ├─ Create DeviceInstance (existing logic)
  ├─ Resolve profile:
  │   ├─ data.profile_id is UUID → load profile (404 if missing)
  │   ├─ data.profile_id absent  → query is_default for template
  │   └─ data.profile_id is null → skip
  ├─ Validate profile.template_id == device.template_id
  ├─ Expand profile.configs → write each as SimulationConfig row
  └─ Return device (unchanged response shape)
```

Key behaviors:
- After apply, `simulation_configs` rows are independent of the profile
- Device does not store a `profile_id` FK — no ongoing reference
- Users modify configs via existing simulation config API
- Re-applying a profile = use existing batch-set API to overwrite configs

---

## Built-in Profile Data

### Key Names Reference

All `mode_params` keys must match exactly what `DataGenerator` expects:

| Mode | Required Keys | Optional Keys |
|------|--------------|---------------|
| `random` | `base`, `amplitude` | `distribution` ("uniform" or "gaussian", default "uniform") |
| `daily_curve` | `base`, `amplitude` | `peak_hour` (default 14) |
| `computed` | `expression` | |
| `accumulator` | `increment_per_second` | `start_value` (default 0.0) |
| `static` | `value` | |

### Value Resolution in Expressions

`computed` expressions reference values via `{register_name}`. These resolve to the **generated** value (before scale_factor division). This matters for `efficiency` (scale_factor=0.1): the generated value is ~960, representing 96.0%. Expressions must account for this.

### Three-Phase Meter (SDM630) — Normal Operation

| Register | Mode | `mode_params` | Rationale |
|----------|------|---------------|-----------|
| `voltage_l1` | random | `{"base": 220, "amplitude": 3, "distribution": "gaussian"}` | 220V ± 3V |
| `voltage_l2` | random | `{"base": 220, "amplitude": 3, "distribution": "gaussian"}` | 220V ± 3V |
| `voltage_l3` | random | `{"base": 220, "amplitude": 3, "distribution": "gaussian"}` | 220V ± 3V |
| `current_l1` | daily_curve | `{"base": 15, "amplitude": 12, "peak_hour": 14}` | 3A–27A daily |
| `current_l2` | daily_curve | `{"base": 15, "amplitude": 12, "peak_hour": 14}` | 3A–27A daily |
| `current_l3` | daily_curve | `{"base": 15, "amplitude": 12, "peak_hour": 14}` | 3A–27A daily |
| `power_l1` | computed | `{"expression": "{voltage_l1} * {current_l1}"}` | P = V × I |
| `power_l2` | computed | `{"expression": "{voltage_l2} * {current_l2}"}` | P = V × I |
| `power_l3` | computed | `{"expression": "{voltage_l3} * {current_l3}"}` | P = V × I |
| `total_power` | computed | `{"expression": "{power_l1} + {power_l2} + {power_l3}"}` | Sum |
| `frequency` | random | `{"base": 60, "amplitude": 0.05, "distribution": "gaussian"}` | Taiwan 60Hz |
| `power_factor_total` | random | `{"base": 0.95, "amplitude": 0.03, "distribution": "gaussian"}` | Typical commercial |
| `total_energy` | accumulator | `{"start_value": 1000, "increment_per_second": 0.00275}` | kWh counter |

**Note on total_energy**: `increment_per_second` is a fixed estimate. The `accumulator` mode does not support expressions, so we use a constant: avg total_power ≈ 220×15×3 = 9900W → 9900/3600000 ≈ 0.00275 kWh/s.

**Note on accumulator restart**: `elapsed_seconds` resets to 0 when a device is stopped and restarted (existing engine behavior). The counter resumes from `start_value`, not from the last accumulated value. This is acceptable for MVP.

### Single-Phase Meter (SDM120) — Normal Operation

| Register | Mode | `mode_params` | Rationale |
|----------|------|---------------|-----------|
| `voltage` | random | `{"base": 220, "amplitude": 3, "distribution": "gaussian"}` | 220V ± 3V |
| `current` | daily_curve | `{"base": 8, "amplitude": 6, "peak_hour": 14}` | 2A–14A daily |
| `active_power` | computed | `{"expression": "{voltage} * {current} * {power_factor}"}` | P = V × I × PF |
| `power_factor` | random | `{"base": 0.95, "amplitude": 0.03, "distribution": "gaussian"}` | |
| `apparent_power` | computed | `{"expression": "{voltage} * {current}"}` | S = V × I |
| `reactive_power` | computed | `{"expression": "{apparent_power} * 0.31"}` | Approx for PF≈0.95 |
| `frequency` | random | `{"base": 60, "amplitude": 0.05, "distribution": "gaussian"}` | Taiwan 60Hz |
| `total_energy` | accumulator | `{"start_value": 500, "increment_per_second": 0.00046}` | ~1660W avg → kWh/s |

**Note on reactive_power**: Exact formula is `√(S²-P²)`. Expression parser does not support `sqrt`. Using approximation `S × 0.31` (valid when PF ≈ 0.95: sin(acos(0.95)) ≈ 0.312).

### Solar Inverter (SunSpec) — Normal Operation

| Register | Mode | `mode_params` | Rationale |
|----------|------|---------------|-----------|
| `dc_voltage` | daily_curve | `{"base": 350, "amplitude": 100, "peak_hour": 12}` | 250V–450V solar |
| `dc_current` | daily_curve | `{"base": 8, "amplitude": 7.5, "peak_hour": 12}` | ~0.5A–15.5A |
| `dc_power` | computed | `{"expression": "{dc_voltage} * {dc_current}"}` | |
| `ac_voltage` | random | `{"base": 220, "amplitude": 3, "distribution": "gaussian"}` | Grid voltage |
| `ac_power` | computed | `{"expression": "{dc_power} * {efficiency} * 0.001"}` | eff ~960 × 0.001 = 0.96 |
| `ac_current` | computed | `{"expression": "{ac_power} / {ac_voltage}"}` | |
| `ac_frequency` | random | `{"base": 60, "amplitude": 0.05, "distribution": "gaussian"}` | |
| `efficiency` | random | `{"base": 960, "amplitude": 10, "distribution": "gaussian"}` | 96% ± 1% (raw value ~960, scale_factor=0.1) |
| `inverter_status` | static | `{"value": 3}` | 3 = Running |
| `total_energy` | accumulator | `{"start_value": 5000, "increment_per_second": 0.00069}` | ~2500W avg → kWh/s |

**Note on efficiency**: The `efficiency` register has `scale_factor=0.1` in the template. The generated value (~960) is stored in `current_values` (pre-scale). The `ac_power` expression uses `{efficiency} * 0.001` to convert: 960 × 0.001 = 0.96 (i.e., 96% efficiency).

**Known limitation**: `daily_curve` uses sin curve, so nighttime values go below base-amplitude rather than clamping to zero. DC current at night ≈ 0.5A instead of 0A. Acceptable for simulator purposes.

---

## Seed Loading

### File Structure

```
backend/app/seed/
├── three_phase_meter.json
├── single_phase_meter.json
├── solar_inverter.json
└── profiles/
    ├── three_phase_meter_normal.json
    ├── single_phase_meter_normal.json
    └── solar_inverter_normal.json
```

### Profile JSON Format

```json
{
  "template_name": "SDM630 Three-Phase Meter",
  "name": "Normal Operation",
  "description": "...",
  "is_default": true,
  "configs": [...]
}
```

Uses `template_name` (not UUID) to resolve template, since UUIDs are generated dynamically.

### Complete Seed JSON Example (single_phase_meter_normal.json)

```json
{
  "template_name": "SDM120 Single-Phase Meter",
  "name": "Normal Operation",
  "description": "Physically consistent single-phase meter simulation with daily load curve and computed power values",
  "is_default": true,
  "configs": [
    {
      "register_name": "voltage",
      "data_mode": "random",
      "mode_params": {"base": 220, "amplitude": 3, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "current",
      "data_mode": "daily_curve",
      "mode_params": {"base": 8, "amplitude": 6, "peak_hour": 14},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "power_factor",
      "data_mode": "random",
      "mode_params": {"base": 0.95, "amplitude": 0.03, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "active_power",
      "data_mode": "computed",
      "mode_params": {"expression": "{voltage} * {current} * {power_factor}"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "apparent_power",
      "data_mode": "computed",
      "mode_params": {"expression": "{voltage} * {current}"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "reactive_power",
      "data_mode": "computed",
      "mode_params": {"expression": "{apparent_power} * 0.31"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "frequency",
      "data_mode": "random",
      "mode_params": {"base": 60, "amplitude": 0.05, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "total_energy",
      "data_mode": "accumulator",
      "mode_params": {"start_value": 500, "increment_per_second": 0.00046},
      "update_interval_ms": 1000,
      "is_enabled": true
    }
  ]
}
```

### Loading Behavior

- Runs at app startup, after template seed loading
- Checks by `(template_id, name)` — skips if already exists (no overwrite)
- Sets `is_builtin=true` for seed-loaded profiles

---

## Scope of Changes

| Layer | Action | Target |
|-------|--------|--------|
| Model | New | `app/models/simulation_profile.py` |
| Schema | New | `app/schemas/simulation_profile.py` |
| Schema | Modify | `app/schemas/device.py` — add `profile_id` to DeviceCreate |
| Migration | New | Alembic migration for `simulation_profiles` |
| Service | New | `app/services/simulation_profile_service.py` |
| Service | Modify | `app/services/device_service.py` — apply logic in create/batch |
| Route | New | `app/api/routes/simulation_profiles.py` |
| Seed | New | `app/seed/profiles/*.json` (3 files) |
| Seed | Modify | Seed loading logic — add profile loading step |
| Test | New | Profile CRUD, apply logic, seed loading |

### Not Changed

- `simulation_configs` table — unchanged
- `DataGenerator` / `SimulationEngine` — unchanged
- `expression_parser` — unchanged (use approximation for reactive_power)
- Frontend — unchanged (profile selector is issue #13)
