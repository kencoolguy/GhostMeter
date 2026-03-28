# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Auto-resume: backend now automatically resumes running devices on startup (registers in protocol adapters + restarts simulation engine)

### Changed
- Monitor DeviceCard preview: defaults to total_power + total_energy instead of voltage_l1/l2
- Monitor chart selector: changed to multi-select, defaults to total_power + total_energy
- Batch device name prefix: removed extra space between prefix and slave ID (e.g. "Meter1" instead of "Meter 1")

### Fixed
- Devices with status=running showed no register values after backend restart (simulation engine was not resumed)

### Previously Added
- Scenario mode: reusable anomaly injection timelines bound to device templates
- Scenario CRUD API (`/api/v1/scenarios`) with list, get, create, update, delete, export, import
- Scenario execution API: start/stop/status per device (`/api/v1/devices/{id}/scenario/...`)
- ScenarioRunner: async executor that triggers anomaly injections on a timeline
- Built-in scenario seeds: Power Outage Recovery, Voltage Instability, Inverter Fault Sequence
- `scenarios` and `scenario_steps` DB tables with Alembic migration
- Frontend Scenarios page: list view with template filter, create/edit/delete/clone/export/import
- Frontend timeline editor: drag-and-drop anomaly blocks on a register×time grid
- Frontend scenario execution card on Device Detail page with start/stop and real-time progress
- 19 integration tests for scenario CRUD, seed loading, built-in protection, and export/import

### Changed
- MQTT publish config card: edit/publish mode separation — fields locked during publishing, "Stop publishing to edit settings" hint
- MQTT publishing status indicator (green `MQTT` tag) in device list and device detail pages
- `mqtt_publishing` boolean field added to device list API response
- Unified button styles: Start Publishing uses green primary, Stop Publishing uses danger

## [0.3.0] - 2026-03-27

### Added
- Simulation profiles: reusable sets of simulation parameters for device templates
- Built-in "Normal Operation" profiles for all three templates (three-phase meter, single-phase meter, solar inverter)
- Automatic profile apply on device creation (default profile auto-applied unless explicitly skipped)
- CRUD API for simulation profiles (`/api/v1/simulation-profiles`)
- `profile_id` field on device creation to control which profile is applied
- Device edit UI: edit modal accessible from both device list (edit icon) and device detail page (Edit button)
- Editable fields: name, description, slave ID, port
- Slave ID and port fields are disabled when device is running (with tooltip explanation)
- Built-in template read-only view: View button (eye icon) on template list, read-only form with "Built-in" tag
- Template import error feedback: import failure now shows detailed error with expected JSON format reference
- Demo startup script (`scripts/start-demo.sh`): one-command setup with auto device creation, simulation config, and Modbus verification
- MQTT protocol adapter: publish simulated device data to external MQTT broker via `aiomqtt`
- MQTT broker settings API (`GET/PUT /api/v1/system/mqtt`) with connection test endpoint
- Per-device MQTT publish config (`GET/PUT/DELETE /api/v1/system/devices/{id}/mqtt`) with start/stop control
- MQTT topic templates with variable substitution (`{device_name}`, `{slave_id}`, `{template_name}`, `{register_name}`)
- Two payload modes: `batch` (all registers in one message) and `per_register` (one message per register)
- MQTT settings included in system export/import for cross-machine portability
- Frontend MQTT broker settings form in Settings page
- Frontend per-device MQTT publish config card in Device Detail page
- Optional mosquitto service in Docker Compose (dev-only, `docker compose --profile mqtt up`)
- Profile management UI: Profiles tab in template detail with full CRUD
- Profile config editor: per-register data mode, params, interval, enabled toggle
- Profile selector dropdown in device creation (single + batch), auto-selects default profile
- Batch device operations: Start All, Stop All, Start/Stop/Delete Selected with checkbox row selection
- Batch API endpoints: `POST /devices/batch/start`, `POST /devices/batch/stop`, `POST /devices/batch/delete`
- Profile export: download individual profiles as standalone JSON files
- Profile import: upload JSON file to create a new profile on a template
- Blank profile template download: pre-populated with all template registers as static defaults
- SNMP agent adapter: SNMPv2c command responder for simulated devices (GET/GETNEXT/WALK)
- Built-in UPS (SNMP) template with RFC 1628 UPS-MIB OIDs (10 registers)
- Built-in UPS simulation profile (Normal Operation)
- OID field on register definitions for SNMP templates
- OID column in frontend register table for SNMP protocol templates
- SNMP protocol option in template creation

### Changed
- Frontend Docker port changed from 3000 to 3002 (avoid port conflicts)
- Backend CORS updated to allow port 3002

### Fixed
- Removed unused imports in Simulation pages (AnomalyTab, index)

## [0.1.0] - 2026-03-20

First MVP release — full Modbus TCP device simulation with web UI.

### Features

#### Device Templates (Phase 2)
- Template CRUD API (`/api/v1/templates`) with register definition management
- Address overlap validation and data type constraints
- Template clone, export (JSON download), and import (JSON upload)
- 3 built-in templates: Three-Phase Meter, Single-Phase Meter, Solar Inverter
- Built-in template protection (cannot update/delete)
- Frontend: template list, create/edit form, register map table

#### Device Instances (Phase 3)
- Device CRUD API (`/api/v1/devices`) with start/stop state control
- Batch creation (up to 50 devices), slave ID uniqueness per port (1–247)
- Template deletion protection when devices reference it
- Frontend: device list with status badges, create modal (single + batch), detail page

#### Modbus TCP Protocol (Phase 4)
- Async Modbus TCP server via pymodbus (FC03 + FC04)
- Multi slave ID on single TCP port
- Datastore synced with simulation engine

#### Simulation Engine (Phase 5)
- DataGenerator: 5 modes (static, random, daily_curve, computed, accumulator)
- Safe AST-based expression parser for computed mode
- AnomalyInjector: spike, drift, flatline, out_of_range, data_loss (real-time + scheduled)
- FaultSimulator: delay, timeout, exception, intermittent communication faults
- Per-register simulation config with JSONB mode params
- Frontend: simulation config page, anomaly injection panel, fault control panel, schedule UI

#### Monitor Dashboard (Phase 6)
- WebSocket `/ws/monitor` broadcasting device state at 1Hz
- MonitorService with in-memory event log (100 events) and data aggregation
- Per-device communication statistics (request/success/error count, avg response time)
- Frontend: device card grid, register table, Recharts line chart (5-min window), stats panel, event log

#### System Finalization (Phase 7)
- System config export/import API (`/api/v1/system/export`, `/api/v1/system/import`)
- Full snapshot: templates + devices + simulation configs + anomaly schedules as portable JSON
- Import upserts by name (templates) and slave_id+port (devices), skips built-in templates
- Frontend: Settings page with export/import buttons
- CONTRIBUTING.md, Playwright smoke tests, `.dockerignore` files

### Infrastructure
- Docker Compose: PostgreSQL 16 + FastAPI backend + Nginx frontend
- Health check endpoint (`GET /health`) with DB connectivity verification
- FastAPI with async lifespan, CORS, structured logging
- SQLAlchemy 2.0 async + asyncpg + Alembic migrations
- Custom exception hierarchy (AppException, NotFoundException, ValidationException, ConflictException, ForbiddenException)
- `ApiResponse[T]` generic envelope for all API responses
- React 18 + TypeScript + Vite + Ant Design + Zustand + Recharts
- Axios API client with error interceptor
- `.env.example` with all configuration variables
