# MQTT Multi-Broker Support — Design (Issue #87)

Date: 2026-07-18
Branch: `feature/claude-mqtt-multi-broker-20260718`

## Goal

Allow GhostMeter to publish to multiple MQTT brokers simultaneously:
- Multiple named broker configurations instead of one global setting.
- A device can publish to any subset of brokers, each with its own
  topic/interval/qos/enabled config.
- Reconnecting or losing one broker must not affect publishing to other brokers.

Motivation (from issue #87): switching the Linode instance from the test broker
(`.125`) to the EnOL production broker (`.49`) forced *all* devices to move at
once, breaking the old pipeline. Parallel pipelines (staging + production
collectors) need per-device broker targeting.

## Approved decisions

1. **Adapter architecture**: single `MqttAdapter` managing
   `dict[broker_id, aiomqtt.Client]`. `ProtocolManager` is untouched.
2. **API compatibility**: clean break — `GET/PUT /api/v1/system/mqtt` is
   removed and replaced by broker-list CRUD. Frontend updated in the same PR.
3. **Scope**: backend + frontend together in one PR.

## Data model

### `mqtt_broker_settings` (modified)

Becomes a multi-row table:

| column | change |
|---|---|
| `id` | unchanged (UUID PK) |
| `name` | **new** — `String(100)`, unique, not null. Human-readable label. |
| `host`, `port`, `username`, `password`, `client_id`, `use_tls` | unchanged |

Note: `client_id` stays per-broker; the actual MQTT client identifier used on
connect is the stored `client_id` (brokers are separate servers, collisions
are not a concern; a user pointing two broker rows at the same server can
differentiate the ids themselves).

### `mqtt_publish_configs` (modified)

| column | change |
|---|---|
| `device_id` | **drop `unique=True`** |
| `broker_id` | **new** — FK → `mqtt_broker_settings.id`, `ondelete="CASCADE"`, not null |
| unique constraint | **new** — `UniqueConstraint(device_id, broker_id)` |
| everything else | unchanged |

### Migration

1. Add `name` to `mqtt_broker_settings` (backfill existing row to `'default'`),
   then set not-null + unique.
2. Add nullable `broker_id` to `mqtt_publish_configs`, backfill all rows to the
   existing broker's id, then set not-null + FK + composite unique; drop the
   old `device_id` unique constraint.
3. Edge case: publish configs existing while no broker row exists cannot happen
   in practice (configs are only useful with a broker), but the migration
   guards it: if configs exist and no broker row does, create a `default`
   broker row (localhost:1883) to attach them to.

Downgrade: keep only the first publish config per device, drop `broker_id`,
restore `device_id` unique, drop `name`.

## API changes (`/api/v1/system`)

Removed:
- `GET /mqtt`, `PUT /mqtt` (single global settings)

Added (broker CRUD):
- `GET /mqtt/brokers` → list of `MqttBrokerRead` (password masked as `****`)
- `POST /mqtt/brokers` → create (201), connects the adapter to the new broker
- `PUT /mqtt/brokers/{broker_id}` → update; `****` password keeps stored one;
  reconnects only this broker and resumes only its publish tasks
- `DELETE /mqtt/brokers/{broker_id}` → 400 if publish configs reference it
  (client must delete/move device configs first — explicit over cascade
  surprise), otherwise disconnects and deletes
- `POST /mqtt/test` — unchanged semantics (ad-hoc settings test, no broker_id)

Per-device endpoints (reshaped to per-(device, broker)):
- `GET /devices/{id}/mqtt` → `list[MqttPublishConfigRead]` (now includes
  `broker_id`, `broker_name`; empty list when none)
- `PUT /devices/{id}/mqtt/{broker_id}` → upsert config for that broker pair
- `DELETE /devices/{id}/mqtt/{broker_id}` → delete that pair's config
- `POST /devices/{id}/mqtt/start` — body/query `broker_id` optional:
  with it → start that pair; without → start **all** of the device's configs
  (marks them enabled). Partial failure returns per-broker results.
- `POST /devices/{id}/mqtt/stop` — same optional `broker_id` semantics.

`MqttPublishConfigRead` gains `broker_id: str` and `broker_name: str`.
Start/stop responses return the affected config list.

## Adapter (`protocols/mqtt_adapter.py`)

State keyed by broker and (device, broker):

```python
self._clients: dict[UUID, aiomqtt.Client]          # broker_id -> client
self._broker_meta: dict[UUID, dict]                # broker_id -> {host, port, connected}
self._publish_tasks: dict[tuple[UUID, UUID], asyncio.Task]   # (device_id, broker_id)
self._publish_configs: dict[tuple[UUID, UUID], dict]
```

- `start()`: load **all** broker rows, connect each independently; one broker
  failing to connect must not block others. `_available` = any broker row
  exists; adapter remains usable if ≥0 connect (failed ones retried on
  explicit reconnect/update).
- `connect_broker(broker_id, settings)` / `disconnect_broker(broker_id)`:
  per-broker lifecycle used by broker CRUD routes.
- `reconnect_broker(broker_id, ...)`: cancels **only that broker's** publish
  tasks, reconnects, and the route resumes only that broker's enabled configs.
  (Fixes the current global-cancel behavior.)
- `start_publishing(device_id, broker_id, config)` /
  `stop_publishing(device_id, broker_id=None)` — `None` stops all brokers'
  tasks for that device (used by device stop / remove).
- `_publish_loop` unchanged in logic, but publishes via the pair's client.
  Fault simulation stays per-device (fault state is device-scoped): a device
  fault affects its publishing to every broker — matches "the device is
  faulty" semantics.
- Per-device stats (`_device_stats`) stay device-scoped, aggregated across
  brokers (Monitor UI shows one stats row per device, unchanged).
- `get_status()` returns
  `{available, brokers: [{id, name, host, port, connected}], publishing_devices}`
  where `publishing_devices` counts distinct devices with ≥1 task.

## Service layer (`services/mqtt_service.py`)

- Broker CRUD: `list_brokers`, `get_broker`, `create_broker`, `update_broker`
  (mask-aware), `delete_broker` (guarded by config refcount).
- Publish config: all getters/upserts take `(device_id, broker_id)`;
  `list_publish_configs(device_id)` returns all pairs joined with broker name.
- `resume_enabled_publishing(session, broker_id=None)` — optional broker
  filter so a single-broker reconnect only resumes its own tasks.

## Call-site updates

- `services/device_service.py`: device start → start all enabled configs of
  that device (each pair independently, log-and-continue on per-pair failure);
  device stop → `stop_publishing(device_id)` (all brokers). Device list
  `mqtt_publishing` flag = any enabled config exists (EXISTS subquery instead
  of the current 1:1 join).
- `services/monitor_service.py`: `mqtt_broker_connected: bool` becomes
  "any broker connected"; add `mqtt_brokers` list to system status payload.
- `services/system_service.py` (export/import): export
  `mqtt_brokers: [...]` (multi) and publish configs with `broker_name`
  reference (name, not UUID, so imports into another instance can match or
  create brokers by name). Import: upsert brokers by name, remap configs.
  Old export files (single `mqtt_broker_settings` object) are still accepted:
  treated as one broker named `default`.

## Frontend

- `types/mqtt.ts` + `services/mqttApi.ts`: broker list types + CRUD calls;
  publish config gains `broker_id`/`broker_name`; start/stop take optional
  broker.
- `Settings/MqttBrokerSettings.tsx` → broker **table** (name/host/port/status)
  with add/edit modal (reusing current form fields + test button) and delete
  (disabled-with-tooltip when referenced by configs → backend 400 surfaced).
- `Devices/MqttPublishConfig.tsx` → list of per-broker config rows for the
  device: each row shows broker name, topic, interval, enabled switch,
  start/stop; "Add broker config" picker for brokers without a config yet.
  Keeps the existing form fields per row (modal or expandable row).
- `DeviceList`/`DeviceDetail`/Monitor badges: `mqtt_publishing` boolean
  semantics unchanged (any enabled config).

## Testing

- Rework `tests/test_mqtt.py`: broker CRUD (create/list/update mask/delete
  guard), per-(device, broker) config CRUD, start/stop with and without
  broker_id, resume filtered by broker.
- `tests/test_mqtt_export_import.py`: multi-broker export round-trip + legacy
  single-broker import compatibility.
- `tests/test_mqtt_fault.py`: unchanged behavior expectations (device-scoped
  faults) against the new task keying.
- Adapter unit tests use fake clients per broker: one broker down does not
  stop the other's publishing; reconnect of broker A leaves broker B's tasks
  running.
- Frontend: update existing vitest suites touched by mqttApi/type changes.

## Out of scope

- Per-broker TLS cert management (use_tls flag passthrough only, as today).
- Broker health auto-reconnect/backoff loops (manual reconnect via update, as
  today).
- SNMP SET / MQTT command-topic write detection (tracked separately).
