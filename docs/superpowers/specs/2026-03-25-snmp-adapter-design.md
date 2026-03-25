# SNMP Agent Adapter — Design Spec

**Date:** 2026-03-25
**Status:** Reviewed
**Phase:** Post-MVP

## Goal

Add an SNMP agent to GhostMeter so external SNMP managers (Zabbix, Nagios, etc.) can query simulated device data via SNMPv2c GET/GETNEXT/WALK.

## Context

GhostMeter already supports Modbus TCP (pull-based) and MQTT (push-based). SNMP is the third most common protocol in energy monitoring, used by UPS, PDU, and environmental sensors. The `ProtocolAdapter` base class and protocol manager are already in place.

## Design Decisions

- **Role:** SNMP Agent only (passive, responds to queries). Trap support is deferred.
- **Version:** SNMPv2c only. v3 (USM auth) is deferred.
- **Template approach:** Dedicated SNMP templates (`protocol: "snmp"`), not mixed Modbus+SNMP templates. Cleaner UX, no user confusion.
- **OID storage:** New `oid` VARCHAR(200) nullable column on `register_definitions`. SNMP templates use `oid`, Modbus templates use `address`.
- **Network:** Single SNMP agent on one UDP port (default 10161), shared by all SNMP devices. Matches Modbus TCP pattern.
- **OID conflict:** MVP uses template OIDs directly (no per-device prefix). Same-template SNMP devices cannot run simultaneously — second start is rejected with error.

## Future Items (Deferred)

- SNMPv3 (USM authentication: username/authKey/privKey)
- SNMP Trap/Inform sending (push-based notifications)
- Per-device OID prefix for running multiple same-template devices

## DB Schema Change

Add to `register_definitions`:

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `oid` | VARCHAR(200) | NULL | — | Full SNMP OID string (e.g. `1.3.6.1.2.1.33.1.3.3.1.3.1`) |

Alembic migration required. Modbus registers leave `oid` as null.

**SNMP registers use `sort_order` value as `address`** (0, 1, 2, ...) to satisfy the existing `uq_register_template_addr_fc` unique constraint. All SNMP registers use `function_code=4` (matches Input Registers, semantically "read-only" which is correct for SNMP). The `address` field is repurposed as a unique index for SNMP templates.

**Schema changes required:**
- `RegisterDefinition` ORM model: add `oid: Mapped[str | None]` column
- `RegisterDefinitionCreate` Pydantic schema: add `oid: str | None = None`
- `RegisterDefinitionResponse` Pydantic schema: add `oid: str | None`
- `RegisterValue` (device detail): add `oid: str | None = None`

## Configuration

Add to `app/config.py`:

```python
SNMP_PORT: int = 10161  # High port to avoid root requirement; map to 161 in Docker
SNMP_COMMUNITY: str = "public"
```

## Backend Architecture

### RegisterInfo Extension

Add optional `oid` field to `RegisterInfo` dataclass in `protocols/base.py`:

```python
@dataclass
class RegisterInfo:
    address: int
    function_code: int
    data_type: str
    byte_order: str
    oid: str | None = None  # SNMP OID, null for Modbus
```

### SnmpAdapter (`protocols/snmp_agent.py`)

Extends `ProtocolAdapter`. Manages a pysnmp SNMPv2c command responder.

**Lifecycle:**
- `start()`: Bind UDP socket on configured port, start SNMP engine
- `stop()`: Shutdown SNMP engine, release port
- `_do_add_device()`: Register device's OID→register mappings in agent. Check for OID conflicts first.
- `_do_remove_device()`: Unregister device's OIDs from agent.
- `update_register()`: No-op (reads from SimulationEngine at query time, same as MQTT).

**Query handling:**
1. SNMP manager sends GET/GETNEXT to agent
2. Agent receives OID, looks up in registered OID→(device_id, register_name) map
3. Reads current value from SimulationEngine
4. Converts to appropriate SNMP type (Integer32, OctetString, Gauge32, etc.) based on register `data_type`
5. Returns response

**OID conflict detection:**
- When adding a device, check if any of its register OIDs are already registered by another running device
- If conflict found, raise `ConflictException` with message listing the conflicting OIDs
- This prevents silent data corruption from two devices claiming the same OID

**Data type mapping:**

| Register data_type | SNMP type |
|-------------------|-----------|
| `int16`, `int32` | Integer32 |
| `uint16`, `uint32` | Gauge32 |
| `float32`, `float64` | OctetString (string repr) |

Note: SNMP has no native float type. Float values are returned as string representations, which is common practice for SNMP-based energy devices (many real devices do this).

### Slave ID for SNMP Devices

SNMP devices have no slave ID concept, but the `DeviceCreate` schema requires `slave_id` (1-247). For SNMP devices, `slave_id` serves as a unique device index — the user still picks a number, and the existing `(slave_id, port)` uniqueness constraint works as before. The frontend can label this as "Device ID" for SNMP templates in a future UX iteration.

### Registration in main.py

```python
snmp_adapter = SnmpAdapter(
    port=settings.SNMP_PORT,
    community=settings.SNMP_COMMUNITY,
)
protocol_manager.register_adapter("snmp", snmp_adapter)
```

### Seed Template

New built-in SNMP template: **"UPS (SNMP)"** based on common UPS-MIB OIDs (RFC 1628):

| Register | OID | Address | Data Type | Unit | Description |
|----------|-----|---------|-----------|------|-------------|
| input_voltage | 1.3.6.1.2.1.33.1.3.3.1.3.1 | 0 | float32 | V | Input Voltage |
| input_frequency | 1.3.6.1.2.1.33.1.3.3.1.2.1 | 1 | float32 | Hz | Input Frequency |
| output_voltage | 1.3.6.1.2.1.33.1.4.4.1.2.1 | 2 | float32 | V | Output Voltage |
| output_current | 1.3.6.1.2.1.33.1.4.4.1.3.1 | 3 | float32 | A | Output Current |
| output_power | 1.3.6.1.2.1.33.1.4.4.1.4.1 | 4 | uint32 | W | Output Power |
| battery_status | 1.3.6.1.2.1.33.1.2.1.0 | 5 | int16 | — | Battery Status (1-4) |
| battery_voltage | 1.3.6.1.2.1.33.1.2.5.0 | 6 | float32 | V | Battery Voltage |
| battery_temperature | 1.3.6.1.2.1.33.1.2.7.0 | 7 | float32 | °C | Battery Temperature |
| estimated_minutes_remaining | 1.3.6.1.2.1.33.1.2.3.0 | 8 | int32 | min | Est. Minutes Remaining |
| estimated_charge_remaining | 1.3.6.1.2.1.33.1.2.4.0 | 9 | int32 | % | Est. Charge Remaining |

All registers use `function_code=4`, `byte_order="big_endian"`, `scale_factor=1.0`. `address` is sequential (0-9) for unique constraint.

Seed JSON file: `backend/app/seed/snmp_ups.json`

### Built-in Simulation Profile

"Normal Operation" profile for UPS template (`backend/app/seed/profiles/snmp_ups_normal.json`):

- input_voltage: random, base=220, amplitude=5
- input_frequency: random, base=60, amplitude=0.5
- output_voltage: random, base=220, amplitude=2
- output_current: random, base=5, amplitude=1
- output_power: computed, `output_voltage * output_current`
- battery_status: static, value=2 (normal)
- battery_voltage: random, base=54, amplitude=1
- battery_temperature: random, base=25, amplitude=2
- estimated_minutes_remaining: static, value=120
- estimated_charge_remaining: static, value=100

## Frontend Changes

### RegisterTable

When `protocol === "snmp"`, show an "OID" column in addition to "Address". The OID column renders a text input for the full OID string. Address is auto-incremented (read-only for SNMP).

### TemplateForm

Add `"snmp"` to `PROTOCOL_OPTIONS`:
```typescript
const PROTOCOL_OPTIONS = [
  { value: "modbus_tcp", label: "Modbus TCP" },
  { value: "snmp", label: "SNMP" },
];
```

### Template/Device Types

Add `oid?: string | null` to `RegisterDefinition` and `RegisterValue` TypeScript interfaces.

### CreateDevice / DeviceDetail

No changes needed — devices reference templates, protocol is handled by template.

## Docker Compose

Add SNMP port mapping to backend service:
```yaml
ports:
  - "8000:8000"
  - "502:502"
  - "161:10161/udp"  # Map host 161 to container 10161
```

## Dependencies

- `pysnmplib>=6.0` — maintained fork of pysnmp for Python 3.12+

## Testing

- SnmpAdapter unit tests: start/stop, add/remove device, OID conflict detection, get_status
- OID→value resolution: register lookup, data type conversion
- Integration test: use pysnmp client to GET/WALK values from running agent
- OID conflict test: start two same-template devices, second rejected
- Seed template test: UPS template loaded with correct OIDs
- Schema test: SNMP template create/read with OID field

## Out of Scope

- SNMPv3 authentication
- SNMP Trap/Inform sending
- Per-device OID prefix
- MIB file compilation/loading
- SET operations (agent is read-only)
