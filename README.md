# GhostMeter

> Multi-protocol device simulator for energy management systems.

[![Version](https://img.shields.io/badge/version-0.1.0-blue)]()
[![Python](https://img.shields.io/badge/python-3.12+-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

## Features

- **Modbus TCP** protocol simulation (FC03 + FC04, multi slave ID)
- **Built-in templates**: Three-Phase Meter, Single-Phase Meter, Solar Inverter
- **5 data generation modes**: static, random, daily curve, computed, accumulator
- **Anomaly injection**: spike, drift, flatline, out-of-range, data loss (real-time + scheduled)
- **Fault simulation**: delay, timeout, exception, intermittent communication
- **Real-time monitoring**: WebSocket dashboard with charts and event log
- **Config export/import**: Full system snapshot for environment migration
- **Modern Web UI**: React + Ant Design management interface

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/kencoolguy/GhostMeter.git
cd GhostMeter
cp .env.example .env
docker compose up -d
```

- **Web UI**: http://localhost:3000
- **API**: http://localhost:8000/api/v1/
- **Modbus TCP**: localhost:502
- **Health**: http://localhost:8000/health

### Development Setup (without Docker)

```bash
# Start PostgreSQL only
docker compose up -d postgres

# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

### Running Tests

```bash
# Backend
cd backend
pytest -v

# Frontend type check
cd frontend
npx tsc --noEmit

# Frontend E2E (requires Playwright)
cd frontend
npm run build
npx playwright test
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+ / FastAPI / pymodbus / SQLAlchemy 2.0 / PostgreSQL 16 |
| Frontend | React 18 / TypeScript / Ant Design 5 / Zustand / Recharts |
| Infrastructure | Docker Compose / Alembic / Nginx |

## API Overview

| Endpoint | Description |
|----------|-------------|
| `GET /health` | System health + DB connectivity |
| `/api/v1/templates` | Device template CRUD + clone/export/import |
| `/api/v1/devices` | Device instance CRUD + start/stop + batch create |
| `/api/v1/devices/{id}/simulation` | Per-register simulation config |
| `/api/v1/devices/{id}/anomaly` | Anomaly injection + schedule management |
| `/api/v1/devices/{id}/fault` | Communication fault control |
| `/api/v1/system/export` | Full system config export (JSON download) |
| `/api/v1/system/import` | Full system config import (JSON upload) |
| `ws://localhost:8000/ws/monitor` | Real-time device state broadcast (1Hz) |

See [`docs/api-reference.md`](docs/api-reference.md) for full API documentation.

## For Data Collector Integration

GhostMeter simulates real energy devices over standard protocols:

```
Modbus TCP → localhost:502
  ├── Slave 1: Three-Phase Meter (SDM630 register map)
  ├── Slave 2: Single-Phase Meter
  └── Slave 3: Solar Inverter
```

- Supports FC03 (Holding Registers) and FC04 (Input Registers)
- Each device has a unique slave ID (1–247)
- Register values updated by simulation engine at configurable intervals
- Anomaly injection and fault simulation for testing edge cases

## Project Structure

```
ghostmeter/
├── backend/             # FastAPI application
│   ├── app/
│   │   ├── api/         # Route handlers + WebSocket
│   │   ├── models/      # SQLAlchemy ORM models
│   │   ├── schemas/     # Pydantic schemas
│   │   ├── services/    # Business logic
│   │   ├── protocols/   # Protocol adapters (Modbus TCP)
│   │   ├── simulation/  # Data generation + anomaly engine
│   │   └── seed/        # Built-in template data
│   ├── alembic/         # DB migrations
│   └── tests/           # pytest test suite (177 tests)
├── frontend/            # React application
│   ├── src/
│   │   ├── pages/       # Templates, Devices, Simulation, Monitor, Settings
│   │   ├── hooks/       # useWebSocket
│   │   ├── stores/      # Zustand state management
│   │   ├── services/    # API client layer
│   │   └── types/       # TypeScript interfaces
│   └── e2e/             # Playwright smoke tests
├── docs/                # API reference, dev log, design specs
├── CONTRIBUTING.md
├── CHANGELOG.md
└── docker-compose.yml
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, conventions, and PR process.

## License

MIT
