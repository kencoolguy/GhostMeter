# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Device edit UI: edit modal accessible from both device list (edit icon) and device detail page (Edit button)
- Editable fields: name, description, slave ID, port
- Slave ID and port fields are disabled when device is running (with tooltip explanation)
- Built-in template read-only view: View button (eye icon) on template list, read-only form with "Built-in" tag
- Template import error feedback: import failure now shows detailed error with expected JSON format reference
- Demo startup script (`scripts/start-demo.sh`): one-command setup with auto device creation, simulation config, and Modbus verification

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
