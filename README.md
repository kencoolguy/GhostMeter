# GhostMeter

> Multi-protocol device simulator for energy management systems.

[![Version](https://img.shields.io/badge/version-0.3.0-blue)]()
[![Python](https://img.shields.io/badge/python-3.12+-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

## Features

- **Modbus TCP** protocol simulation (FC03 + FC04, multi slave ID)
- **MQTT publish** to external broker (batch or per-register, configurable topic/QoS)
- **SNMP agent** (SNMPv2c GET/GETNEXT/WALK) with OID mapping for UPS and other devices
- **Built-in templates**: Three-Phase Meter, Single-Phase Meter, Solar Inverter, UPS (SNMP)
- **Simulation profiles**: Reusable parameter sets with per-register config, auto-applied on device creation
- **Profile management**: Export, import, and blank template download for easy sharing
- **5 data generation modes**: static, random, daily curve, computed, accumulator
- **Anomaly injection**: spike, drift, flatline, out-of-range, data loss (real-time + scheduled)
- **Fault simulation**: delay, timeout, exception, intermittent communication
- **Real-time monitoring**: WebSocket dashboard with charts and event log
- **Batch operations**: Start, stop, and delete multiple devices at once
- **Config export/import**: Full system snapshot including MQTT settings and simulation profiles
- **Modern Web UI**: React + Ant Design management interface

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/kencoolguy/GhostMeter.git
cd GhostMeter
cp .env.example .env
docker compose up -d
```

- **Web UI**: http://localhost:3002
- **API**: http://localhost:8000/api/v1/
- **Modbus TCP**: localhost:502
- **Health**: http://localhost:8000/health

To also start a local MQTT broker for development:

```bash
docker compose --profile mqtt up -d
# Broker available at localhost:1883
```

### Docker Operations

```bash
# 啟動所有服務
docker compose up -d

# 查看服務狀態
docker compose ps

# 查看 logs
docker compose logs backend        # 單一服務
docker compose logs -f              # 即時追蹤全部

# 重啟單一服務（會重新載入 seed data）
docker compose restart backend

# 停止並移除所有 container（保留 DB 資料）
docker compose down

# 停止並移除所有 container + 刪除 DB 資料（⚠️ 不可逆）
docker compose down -v

# 強制重建 image（程式碼有改動時）
docker compose up -d --build
```

> **注意**：`docker compose up -d` 不會重啟已在運行的 container。若需重啟請用 `docker compose restart`。

> **資料庫被清空後恢復**：如果不小心跑了 `docker compose down -v`，需要手動重建 DB schema 再重啟：
> ```bash
> docker compose up -d
> docker compose exec backend alembic upgrade head
> docker compose restart backend
> ```
> Backend 啟動時會自動載入內建的 seed data（templates、profiles、scenarios）。

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
| Backend | Python 3.12+ / FastAPI / pymodbus / aiomqtt / SQLAlchemy 2.0 / PostgreSQL 16 |
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
| `/api/v1/simulation-profiles` | Simulation profile CRUD (per template) |
| `/api/v1/system/mqtt` | MQTT broker settings + per-device publish config |
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

MQTT → configurable external broker
  └── Publishes device telemetry (batch or per-register)
```

- Supports FC03 (Holding Registers) and FC04 (Input Registers)
- Each device has a unique slave ID (1–247)
- Register values updated by simulation engine at configurable intervals
- MQTT publish with configurable topic templates, QoS, and retain flag
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
│   │   ├── protocols/   # Protocol adapters (Modbus TCP, MQTT)
│   │   ├── simulation/  # Data generation + anomaly engine
│   │   └── seed/        # Built-in templates + profiles
│   ├── alembic/         # DB migrations
│   └── tests/           # pytest test suite (229 tests)
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
