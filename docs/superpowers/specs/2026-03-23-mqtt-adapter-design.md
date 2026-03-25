# MQTT Adapter — Design Spec

**Date**: 2026-03-23
**Status**: Approved
**Scope**: Add MQTT publish capability to GhostMeter as the second protocol adapter

## Goal

Allow GhostMeter to publish simulated device data to an MQTT broker with user-configurable topics and payload formats. Users configure everything first, then press "Start Publishing" to begin.

## Architecture Overview

```
Settings page → MQTT Broker connection (global, one broker for all devices)
Device Detail page → MQTT Publish Config (per device)
    - topic template with variables
    - payload mode (batch / per-register)
    - publish interval
    - Start/Stop Publishing button
```

MQTT is push-based (adapter publishes at intervals), complementing Modbus's pull-based model (client polls). A device can run both protocols simultaneously.

## Design Decisions

### 1. MQTT Broker — Global Settings

**Why**: One broker for all devices. Simpler to configure, covers the common case.

**Storage**: Dedicated `mqtt_broker_settings` table (single row). Requires Alembic migration.

**Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| id | UUID | auto | Primary key (single row) |
| host | string | "localhost" | Broker hostname/IP |
| port | int | 1883 | Broker port |
| username | string | "" | Auth username (empty = no auth) |
| password | string | "" | Auth password (stored plain, masked in API response) |
| client_id | string | "ghostmeter" | MQTT client identifier |
| use_tls | bool | false | Enable TLS connection |

**Password handling**: Stored as plain text in DB (same security level as Modbus — local dev tool). GET response masks password as `"****"` if non-empty. PUT accepts new password or `"****"` to keep existing.

**API** (under `/api/v1/system/mqtt` to match existing `/api/v1/system/*` pattern):
- `GET /api/v1/system/mqtt` — get current broker config (password masked)
- `PUT /api/v1/system/mqtt` — update broker config
- `POST /api/v1/system/mqtt/test` — test connection using **request body** config (so user can test before saving)

### 2. MQTT Publish Config — Per Device

**Why**: Each device can have different topic/payload/interval settings. Independent of Simulation Config (what data to generate vs where to publish are separate concerns).

**Storage**: New `mqtt_publish_configs` table. Requires Alembic migration.

**Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| id | UUID | auto | Primary key |
| device_id | UUID | — | FK to device_instances (unique, one config per device) |
| topic_template | string | "telemetry/{device_name}" | Topic with variable placeholders |
| payload_mode | enum | "batch" | "batch" or "per_register" |
| publish_interval_seconds | int | 5 | Seconds between publishes |
| qos | int | 0 | MQTT QoS level (0, 1, 2) |
| retain | bool | false | MQTT retain flag |
| enabled | bool | false | Publishing active or not |

**Topic template variables**: `{device_name}`, `{slave_id}`, `{register_name}`, `{template_name}`

- `{register_name}` is only meaningful in `per_register` mode
- If `per_register` mode is selected but topic_template doesn't contain `{register_name}`, validation error

**`enabled` field semantics**: Only modified via start/stop endpoints. `PUT .../mqtt` saves config but does NOT change `enabled` state. This separates "configure" from "activate".

**Auto-resume on device start**: When a device is started and its MQTT config has `enabled=true`, publishing auto-resumes. When a device is stopped, publishing stops (but `enabled` stays true so it resumes on next start).

**API**:
- `GET /api/v1/devices/{id}/mqtt` — get MQTT config for device
- `PUT /api/v1/devices/{id}/mqtt` — create or update MQTT config (does not change enabled)
- `DELETE /api/v1/devices/{id}/mqtt` — remove MQTT config
- `POST /api/v1/devices/{id}/mqtt/start` — set enabled=true, start publishing
- `POST /api/v1/devices/{id}/mqtt/stop` — set enabled=false, stop publishing

### 3. Payload Formats

**Batch mode** (one message per device, all registers):
```json
{
  "device": "PM-01",
  "timestamp": "2026-03-23T10:00:00Z",
  "values": {
    "voltage": 220.5,
    "current": 1.2,
    "active_power": 264.6
  }
}
```

**Per-register mode** (one message per register):
```json
{
  "value": 220.5,
  "timestamp": "2026-03-23T10:00:00Z"
}
```

### 4. MqttAdapter (implements ProtocolAdapter)

```python
class MqttAdapter(ProtocolAdapter):
    """MQTT publish adapter using aiomqtt (asyncio MQTT client)."""

    async def start(self) -> None:
        """Load broker settings from DB and connect.
        If no broker settings exist, set self._available = False and return
        (no-op). This prevents blocking Modbus from starting via
        ProtocolManager.start_all().
        """

    async def stop(self) -> None:
        """Stop all publish tasks, disconnect from broker."""

    async def _do_add_device(self, device_id, slave_id, registers) -> None:
        """Store register map in memory for payload building."""

    async def _do_remove_device(self, device_id) -> None:
        """Stop publish task for this device, clean up."""

    async def update_register(self, device_id, address, fc, value, dt, bo) -> None:
        """Update in-memory register value. Does NOT publish immediately."""

    def get_status(self) -> dict:
        """Return adapter status: broker connected, active publishers count."""
        return {
            "broker_host": self._host,
            "broker_port": self._port,
            "connected": self._connected,
            "publishing_devices": len(self._publish_tasks),
        }

    # --- MQTT-specific (not in base interface) ---

    async def start_publishing(self, device_id, config) -> None:
        """Start a per-device async task that publishes at config.interval."""

    async def stop_publishing(self, device_id) -> None:
        """Cancel the device's publish task."""

    async def reconnect(self, broker_settings) -> None:
        """Reconnect with new broker settings (called when user updates settings)."""
```

**Key difference from Modbus**: `update_register` only updates in-memory values. Publishing happens in a separate async task loop per device, controlled by `start_publishing` / `stop_publishing`.

**Publish loop** (per device):
1. Sleep for `publish_interval_seconds`
2. Read current in-memory register values
3. Render topic template with variables
4. Format payload based on payload_mode
5. Publish to broker
6. Update stats (request_count, success_count, error_count)
7. Repeat

**Broker disconnection handling**:
- On `MqttError`, log error, increment `error_count` in stats
- Publish loop continues retrying each interval (aiomqtt reconnects automatically)
- If broker is unreachable for extended period, errors are visible in Monitor Dashboard stats

**`aiomqtt` context manager pattern**: MqttAdapter manages a persistent `aiomqtt.Client` instance using manual connect/disconnect (not the `async with` context manager) to support long-lived connections across the adapter lifecycle.

### 5. Dual-Protocol Support (SimulationEngine changes)

**Problem**: The simulation engine currently calls `update_register` on only ONE adapter (the device template's `protocol` field). To support Modbus + MQTT simultaneously, the engine must notify both adapters.

**Solution**: Instead of changing the simulation engine's core loop, the **MqttAdapter reads values from SimulationEngine's in-memory store** (`simulation_engine.get_current_values(device_id)`). This is the same approach MonitorService already uses.

```
SimulationEngine loop → update_register(Modbus adapter) → Modbus datastore updated
                      ↘ _device_values[device_id] updated in memory

MqttAdapter publish loop → read simulation_engine.get_current_values(device_id) → publish to broker
```

**Why this approach**:
- Zero changes to SimulationEngine or device_service — Modbus path untouched
- MqttAdapter's publish loop is already independent (interval-based), so it naturally reads the latest values at publish time
- `update_register` on MqttAdapter becomes unnecessary (it has no datastore) — but we still implement it as a no-op to satisfy the abstract interface

**Revised MqttAdapter.update_register**:
```python
async def update_register(self, device_id, address, fc, value, dt, bo) -> None:
    """No-op. MQTT reads values from SimulationEngine at publish time."""
    pass
```

**device_service.start_device changes**: After starting the Modbus device + simulation, check if the device has an MQTT publish config with `enabled=true`. If so, call `mqtt_adapter.start_publishing(device_id, config)`.

**device_service.stop_device changes**: Call `mqtt_adapter.stop_publishing(device_id)` if publishing was active.

### 6. Frontend UI

**Settings page — MQTT Broker section**:
- Form: host, port, username, password, client_id, use_tls
- "Test Connection" button → calls POST /api/v1/system/mqtt/test with **current form values** (not saved values)
- Connection status indicator (connected / disconnected / error)

**Device Detail page — MQTT Publishing section** (new Card below Register Map):
- Topic template input with variable hint text
- Payload mode radio: Batch / Per-register
- Interval input (seconds)
- QoS selector (0 / 1 / 2)
- Retain toggle
- "Save Config" button (saves without starting)
- **"Start Publishing" / "Stop Publishing" button** — prominent, green/red
- Publishing status badge (Publishing / Stopped)

### 7. Dependencies

- Python: `aiomqtt` (async MQTT client, wraps paho-mqtt)
- For development/testing: `mosquitto` Docker container as test broker

**docker-compose.yml** — add mosquitto service (via Docker Compose profiles, optional):
```yaml
mosquitto:
  image: eclipse-mosquitto:2
  profiles: ["mqtt"]
  ports:
    - "1883:1883"
  volumes:
    - ./mosquitto.conf:/mosquitto/config/mosquitto.conf
```

**mosquitto.conf** (new file in project root):
```
listener 1883
allow_anonymous true
```

Start with: `docker compose --profile mqtt up -d mosquitto`

Users can also point to an external broker instead of running mosquitto locally.

### 8. Integration with Existing Systems

- **SimulationEngine**: NOT modified. MqttAdapter reads values from `simulation_engine.get_current_values()` at publish time.
- **device_service**: Modified to start/stop MQTT publishing alongside Modbus device lifecycle.
- **ProtocolManager**: Register MqttAdapter as `"mqtt"` alongside existing `"modbus_tcp"`. `start_all()` — MqttAdapter.start() is resilient (no-op if unconfigured), so it won't block Modbus from starting.
- **MonitorService**: Add `protocol_manager.get_stats("mqtt", device_id)` query alongside existing Modbus stats. Aggregate both into the device's stats.
- **System Export/Import**: Include mqtt_broker_settings and mqtt_publish_configs in export JSON. Requires schema + service changes.

### 9. Not In Scope (v1)

- MQTT subscribe (GhostMeter is a simulator, only publishes)
- Custom payload JSON template (batch/per_register covers common cases)
- Per-device broker connection (global broker only)
- MQTT v5 features (will-message, user properties)
- Sparkplug B format
- Environment variable defaults for MQTT broker (all config via DB/UI)

### 10. Known Risks / Limitations

- **Single MQTT client**: All devices share one broker connection. At very high scale (50+ devices, 1s interval), may need client pooling. Acceptable for simulator use case.
- **No TLS certificate management**: `use_tls` only enables TLS with default CA bundle. Custom certs are out of scope for v1.

## Files to Create/Modify

### New files
| File | Description |
|------|-------------|
| `backend/app/protocols/mqtt_adapter.py` | MqttAdapter implementation |
| `backend/app/models/mqtt.py` | ORM models: MqttBrokerSettings, MqttPublishConfig |
| `backend/app/schemas/mqtt.py` | Pydantic schemas for MQTT config |
| `backend/app/services/mqtt_service.py` | MQTT broker + publish config CRUD service |
| `backend/app/api/routes/mqtt.py` | API routes for MQTT settings + per-device config |
| `backend/alembic/versions/xxx_add_mqtt_tables.py` | Migration for mqtt_broker_settings + mqtt_publish_configs |
| `backend/tests/test_mqtt.py` | Unit tests for MqttAdapter |
| `backend/tests/test_mqtt_api.py` | API integration tests |
| `frontend/src/types/mqtt.ts` | TypeScript interfaces |
| `frontend/src/services/mqttApi.ts` | API client functions |
| `frontend/src/pages/Devices/MqttPublishConfig.tsx` | MQTT config + publish control component |
| `frontend/src/pages/Settings/MqttBrokerSettings.tsx` | Broker connection settings component |
| `mosquitto.conf` | Minimal mosquitto config for dev |

### Modified files
| File | Change |
|------|--------|
| `backend/app/main.py` | Register MQTT routes, init MqttAdapter in ProtocolManager |
| `backend/app/protocols/__init__.py` | Register MqttAdapter |
| `backend/app/services/device_service.py` | Start/stop MQTT publishing in device lifecycle |
| `backend/app/services/monitor_service.py` | Query MQTT stats alongside Modbus stats |
| `backend/app/schemas/system.py` | Add MQTT data to export/import schemas |
| `backend/app/services/system_service.py` | Include MQTT data in export/import logic |
| `backend/requirements.txt` | Add aiomqtt |
| `frontend/src/pages/Devices/DeviceDetail.tsx` | Add MQTT Publishing card |
| `frontend/src/pages/Settings/index.tsx` | Add MQTT Broker settings section |
| `docker-compose.yml` | Add optional mosquitto service (profiles) |

## Success Criteria

- MQTT broker settings can be configured and tested from Settings page
- Per-device MQTT publish config (topic, payload mode, interval) can be set
- Start Publishing → data flows to broker at configured interval
- Stop Publishing → data stops
- Batch and per-register payload modes work correctly
- Stats visible in Monitor Dashboard via ProtocolManager
- Existing Modbus functionality unaffected
- Device can run Modbus + MQTT simultaneously
- Device start auto-resumes MQTT publishing if enabled
- System export/import includes MQTT configs
