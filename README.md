# GhostMeter

> Multi-protocol device simulator for energy management systems.

[![Version](https://img.shields.io/badge/version-0.4.0-blue)]()
[![Python](https://img.shields.io/badge/python-3.12+-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

## Features

- **Modbus TCP** protocol simulation (FC03 + FC04, multi slave ID)
- **MQTT publish** to external broker (batch or per-register, configurable topic/QoS)
- **SNMP agent** (SNMPv2c GET/GETNEXT/WALK) with OID mapping for UPS and other devices
- **OPC UA server** (Anonymous/None security; browsable Variable nodes, Read + Subscribe)
- **BACnet/IP** (UDP 47808; Who-Is/I-Am discovery, ReadProperty / ReadPropertyMultiple; each device is an independent BACnet device instance)
- **Built-in templates**: Three-Phase Meter, Single-Phase Meter, Solar Inverter, UPS (SNMP), Energy Meter (OPC UA), Energy Meter (BACnet)
- **Simulation profiles**: Reusable parameter sets with per-register config, auto-applied on device creation
- **Profile management**: Export, import, and blank template download for easy sharing
- **5 data generation modes**: static, random, daily curve, computed, accumulator
- **Anomaly injection**: spike, drift, flatline, out-of-range, data loss (real-time + scheduled)
- **Scenario mode**: reusable anomaly timelines per template with a drag-and-drop editor, built-in scenario presets, and per-device execution with live progress
- **Fault simulation**: delay, timeout, exception, intermittent communication — supported across all five protocols
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
- **OPC UA**: opc.tcp://localhost:4840/ghostmeter/server/
- **BACnet/IP**: UDP localhost:47808
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

# 只重建前端（改了 frontend/ 時）
docker compose up -d --build frontend
# 或分兩步：先 build 再重啟
docker compose build frontend
docker compose up -d frontend

# 只重建後端（改了 backend/ 時）
docker compose up -d --build backend

# 完全清掉快取重建（依賴有改、或 build 結果怪怪的時候）
docker compose build --no-cache frontend
docker compose up -d frontend
```

> **注意**：`docker compose up -d` 不會重啟已在運行的 container。若需重啟請用 `docker compose restart`。
>
> **前端改完沒反應？** Nginx container 是 serve build 後的靜態檔，單純 `restart` 不會帶入新程式碼，必須 `--build`。

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

## Deployment

On a server (e.g. a Linode VM running Docker), deploy with the prod overlay so
service ports bind to a private interface (set `BIND_IP` in `.env`) instead of
the public network:

```bash
# First deploy
cp .env.example .env          # then set POSTGRES_PASSWORD + BIND_IP
./deploy.sh                   # prod overlay + migrations + start

# Update to the latest dev and redeploy (one shot)
cd ~/ghostmeter && ./update.sh
```

`update.sh` pulls the latest `dev`, checks `.env`, then runs `deploy.sh`. See
[`docs/deployment.md`](docs/deployment.md) for the full guide (Tailscale +
Cloudflare Tunnel).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12+ / FastAPI / pymodbus / aiomqtt / asyncua / bacpypes3 / SQLAlchemy 2.0 / PostgreSQL 16 |
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

OPC UA → opc.tcp://localhost:4840/ghostmeter/server/
  └── Browsable Variable nodes (Read + Subscribe, Anonymous/None)

BACnet/IP → UDP localhost:47808
  ├── Device 100001: Energy Meter (instance = 100000 + slave_id)
  └── Registers → read-only analog-input objects with engineering units
```

- Supports FC03 (Holding Registers) and FC04 (Input Registers)
- Each device has a unique slave ID (1–247)
- Register values updated by simulation engine at configurable intervals
- MQTT publish with configurable topic templates, QoS, and retain flag
- Anomaly injection and fault simulation for testing edge cases

### BACnet/IP discovery note

BACnet Who-Is discovery uses UDP broadcast and **does not traverse docker bridge networks or routed subnets** (e.g. Tailscale). If your EMS client is on a different L2 segment from the simulator:

- Configure the simulator's IP as a static BACnet device address in your client — **unicast ReadProperty and directed Who-Is work fine** without broadcast reachability.
- Alternatively, run the client on the same docker network or host network as the simulator.

BBMD (BACnet Broadcast Management Device) / Foreign Device registration is deferred. I-Am announcements are skipped on /31 and /32 binds (no broadcast address).

With the default `BACNET_ADDRESS=0.0.0.0/0` the adapter serves **unicast only** and logs a warning at startup; set a concrete interface CIDR (e.g. `192.168.1.10/24`) to enable broadcast Who-Is discovery on that subnet.

## Project Structure

```
ghostmeter/
├── backend/             # FastAPI application
│   ├── app/
│   │   ├── api/         # Route handlers + WebSocket
│   │   ├── models/      # SQLAlchemy ORM models
│   │   ├── schemas/     # Pydantic schemas
│   │   ├── services/    # Business logic
│   │   ├── protocols/   # Protocol adapters (Modbus TCP, MQTT, SNMP, OPC UA, BACnet/IP)
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
