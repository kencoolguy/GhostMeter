# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Real-time Monitor Dashboard: WebSocket `/ws/monitor` endpoint broadcasting device state at 1Hz
- MonitorService with in-memory event log (circular buffer, 100 events) and data aggregation from simulation engine, anomaly injector, fault simulator, and protocol adapter
- Per-device communication statistics (request count, success/error count, avg response time) in ModbusTcpAdapter
- Event logging on device start/stop, anomaly inject/clear, fault set/clear
- Frontend Monitor page: device card grid, register table, Recharts line chart (5-min rolling window), stats panel, event log
- useWebSocket hook with exponential backoff reconnect
- monitorStore (Zustand) with rolling register history buffer (300 points per device/register)
- Monitor TypeScript types (DeviceMonitorData, MonitorEvent, MonitorUpdate, etc.)

### Fixed
- Added missing `pymodbus` to backend requirements.txt
- Added missing `MODBUS_HOST`/`MODBUS_PORT` to Settings config

### Previously Added
- Simulation engine: per-device async task loop generates register values and writes to Modbus adapter
- DataGenerator with 5 modes: static, random (uniform/gaussian), daily_curve (sinusoidal), computed (safe expression parser), accumulator
- Safe AST-based expression parser for computed mode — supports `{register_name}` variable references and four arithmetic operators
- SimulationConfig DB model (`simulation_configs` table) with per-register configuration and JSONB mode_params
- Simulation config CRUD API: GET/PUT/PATCH/DELETE `/api/v1/devices/{id}/simulation`
- FaultSimulator for in-memory per-device communication fault state (delay, timeout, exception, intermittent)
- Fault control API: PUT/GET/DELETE `/api/v1/devices/{id}/fault`
- Reverse slave-to-device mapping in ModbusTcpAdapter (`get_device_id_for_slave`)
- Simulation engine integrated into device start/stop lifecycle and FastAPI lifespan shutdown
- Pydantic schemas with validation for simulation config and fault control
- Device instance CRUD API (`/api/v1/devices`) — create, list, get, update, delete
- Batch device creation endpoint (`POST /api/v1/devices/batch`) — up to 50 devices at once
- Device start/stop state control (`POST /api/v1/devices/{id}/start`, `/stop`)
- Device register view endpoint (`GET /api/v1/devices/{id}/registers`) — returns template registers with null values (Phase 3)
- `ConflictException` custom exception class with HTTP 409 response
- Template deletion protection — cannot delete templates referenced by devices (`409 TEMPLATE_IN_USE`)
- Slave ID uniqueness validation per port (1–247 range)
- Frontend Devices page: list view with status badges, start/stop toggle, delete
- Frontend Create Device modal with single and batch creation tabs
- Frontend Device Detail page showing register map table
- Zustand `deviceStore` for device list and selection state
- `deviceApi` service for all `/api/v1/devices` Axios calls
- TypeScript interfaces for `DeviceSummary`, `DeviceDetail`, `RegisterValue`, `CreateDevice`, `BatchCreateDevice`, `UpdateDevice`
- React Router route for `/devices/:id`
- Alembic migration for `device_instances` table with FK RESTRICT to `device_templates`
- Device template CRUD API (`/api/v1/templates`) — create, list, get, update, delete
- Register definition management with address overlap validation and data type constraints
- Template clone endpoint (`POST /api/v1/templates/{id}/clone`) with auto-generated name
- Template export endpoint (`GET /api/v1/templates/{id}/export`) — JSON file download
- Template import endpoint (`POST /api/v1/templates/import`) — JSON file upload
- Alembic migration for `device_templates` and `register_definitions` tables
- Seed data loader: auto-creates 3 built-in templates on startup (Three-Phase Meter / Single-Phase Meter / Solar Inverter)
- Built-in template protection: update and delete blocked with `403 BUILTIN_TEMPLATE_IMMUTABLE`
- `ForbiddenException` custom exception class with HTTP 403 response
- `ApiResponse[T]` generic envelope schema shared across all API responses
- Frontend Templates page: list view with template table, register count, built-in badge
- Frontend TemplateForm page: create/edit form with register map table
- Frontend RegisterTable component: add, remove, inline-edit registers with sort order
- Frontend ImportExportButtons component: JSON file upload and download
- Zustand `templateStore` for template list and selection state
- `templateApi` service for all `/api/v1/templates` Axios calls
- TypeScript interfaces for `DeviceTemplate`, `RegisterDefinition`, `TemplateSummary`, `TemplateDetail`
- React Router routes for `/templates/new` and `/templates/:id`
- Docker Compose setup with PostgreSQL 16, healthcheck, and env parameterization
- FastAPI backend with async lifespan, CORS, and structured logging
- Health check endpoint (`GET /health`) with DB connectivity verification
- Pydantic-settings configuration (auto-constructs DATABASE_URL from individual env vars)
- Async SQLAlchemy 2.0 engine + session factory with asyncpg
- Custom exception classes (AppException, NotFoundException, ValidationException) with global handlers
- Alembic setup with async SQLAlchemy support (migrations infrastructure, no tables yet)
- Backend test suite with pytest-asyncio (health endpoint tests)
- React 18 + TypeScript frontend with Vite build tool
- Ant Design 5 layout with collapsible sidebar navigation
- 4 placeholder pages: Templates, Devices, Simulation, Monitor
- React Router with nested layout routing
- Zustand store for UI state (sidebar collapsed)
- Axios API client with error interceptor
- Backend Dockerfile (python:3.12-slim)
- Frontend Dockerfile (multi-stage: node:22-alpine build → nginx:alpine serve)
- Nginx config with SPA fallback and API/WebSocket proxy
- `.env.example` with all configuration variables
