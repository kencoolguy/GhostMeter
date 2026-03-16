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
- **Frontend**: React 18 / TypeScript / Ant Design 5 / Zustand
- **Infrastructure**: Docker Compose

## Quick Start

```bash
# Start PostgreSQL
docker compose up -d postgres

# Backend
cd backend
pip install -r requirements.txt
alembic upgrade head
python -m app.main

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

## Project Structure

```
ghostmeter/
├── backend/         # FastAPI application
│   ├── app/
│   │   ├── api/         # Route handlers
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
│       ├── pages/
│       ├── components/
│       ├── stores/
│       ├── services/
│       └── types/
└── docs/
```

## License

MIT
