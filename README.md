# GhostMeter

Multi-protocol device simulator for energy management systems.

## Features (MVP)

- **Modbus TCP** protocol simulation
- Built-in energy device templates (smart meters, inverters)
- Anomaly injection engine (spike, drift, flatline, etc.)
- Fault simulation (delay, timeout, exception)
- Modern Web UI for device management and monitoring
- Real-time register value visualization via WebSocket

## Tech Stack

- **Backend**: Python 3.12+ / FastAPI / pymodbus / SQLAlchemy 2.0 / PostgreSQL 16
- **Frontend**: React 18 / TypeScript / Ant Design 5 / Zustand / Recharts
- **Infrastructure**: Docker Compose

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/kencoolguy/GhostMeter.git
cd GhostMeter

# 2. Copy .env.example and adjust if needed
cp .env.example .env

# 3. Start all services
docker compose up -d

# 4. Open browser
# Web UI:  http://localhost:3000
# API:     http://localhost:8000/api/v1/
# Health:  http://localhost:8000/health
```

### Development Setup (without Docker)

```bash
# Start PostgreSQL only
docker compose up -d postgres

# Backend
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

## For Data Collector Integration

GhostMeter simulates real energy devices over standard protocols:

- **Modbus TCP**: Connect to `localhost:502` (default)
  - Supports FC03 (Holding Registers) and FC04 (Input Registers)
  - Each device has a unique slave ID (1–247)
- **REST API**: `http://localhost:8000/api/v1/`
  - `/templates` — manage device register maps
  - `/devices` — create/start/stop device instances
  - `/devices/{id}/simulation` — configure data generation
  - `/devices/{id}/anomaly` — inject anomalies
  - `/devices/{id}/fault` — simulate communication faults
- **WebSocket**: `ws://localhost:8000/ws/monitor`
  - Real-time device state broadcast at 1Hz

See `docs/api-reference.md` for full API documentation.

## Project Structure

```
ghostmeter/
├── backend/         # FastAPI application
│   ├── app/
│   │   ├── api/         # Route handlers + WebSocket
│   │   ├── models/      # SQLAlchemy ORM models
│   │   ├── schemas/     # Pydantic schemas
│   │   ├── services/    # Business logic
│   │   ├── protocols/   # Protocol adapters (Modbus TCP, ...)
│   │   ├── simulation/  # Data generation + anomaly engine
│   │   └── seed/        # Built-in template data
│   ├── alembic/         # DB migrations
│   └── tests/
├── frontend/        # React application
│   └── src/
│       ├── pages/       # Templates, Devices, Simulation, Monitor
│       ├── hooks/       # useWebSocket
│       ├── stores/      # Zustand state management
│       ├── services/    # API client layer
│       └── types/       # TypeScript interfaces
└── docs/
```

## License

MIT
