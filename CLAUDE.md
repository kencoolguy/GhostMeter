# CLAUDE.md — GhostMeter (GhostMeter)

## Project Overview

GhostMeter (GhostMeter) 是一個專為能源管理系統開發者打造的多協議設備模擬器。
核心價值：內建能源設備模板（電表、逆變器）+ 智能異常注入引擎 + 現代 Web UI。

MVP 聚焦 Modbus TCP 協議，架構設計支援未來擴展 MQTT / SNMP / BACnet。

## Tech Stack

### Backend
- **Language**: Python 3.12+
- **Framework**: FastAPI (async)
- **Protocol**: pymodbus (async mode)
- **ORM**: SQLAlchemy 2.0 + asyncpg
- **Validation**: Pydantic v2
- **Database**: PostgreSQL 16
- **Migration**: Alembic
- **Testing**: pytest + pytest-asyncio + httpx

### Frontend
- **Framework**: React 18 + TypeScript
- **Build**: Vite
- **UI Library**: Ant Design 5
- **State**: Zustand
- **HTTP Client**: Axios
- **WebSocket**: native WebSocket API
- **Charts**: @ant-design/charts or Recharts

### Infrastructure
- Docker Compose (frontend + backend + postgres)
- GitHub Actions CI

## Project Structure

```
ghostmeter/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry
│   │   ├── config.py            # Settings (pydantic-settings)
│   │   ├── database.py          # Async engine + session
│   │   ├── api/
│   │   │   ├── routes/          # API route modules
│   │   │   └── websocket.py     # WS handler
│   │   ├── models/              # SQLAlchemy ORM models
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   ├── services/            # Business logic layer
│   │   ├── protocols/           # Protocol adapters (pluggable)
│   │   │   ├── base.py          # Abstract protocol interface
│   │   │   └── modbus_tcp.py    # Modbus TCP implementation
│   │   ├── simulation/          # Data generation + anomaly + fault
│   │   └── seed/                # Built-in template JSON files
│   ├── alembic/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/               # Route pages
│   │   ├── components/          # Shared components
│   │   ├── stores/              # Zustand stores
│   │   ├── services/            # API client functions
│   │   └── types/               # TypeScript interfaces
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── docs/
├── CLAUDE.md
└── README.md
```

## Architecture Decisions

### Backend Patterns
- **Layered architecture**: routes → services → models (不要在 route 裡直接操作 DB)
- **Async everywhere**: FastAPI + asyncpg + pymodbus async server
- **Protocol adapter pattern**: `protocols/base.py` 定義抽象介面，每個協議實作自己的 adapter
- **All IDs use UUID**: 不使用自增 ID
- **JSONB for flexible params**: simulation_configs 的 mode_params / anomaly_params / fault_params 用 JSONB

### Frontend Patterns
- **Page-level components**: 每個頁面一個資料夾，含自己的 sub-components
- **Zustand stores**: 按 domain 分 store（templateStore, deviceStore, simulationStore）
- **API client layer**: `services/` 封裝所有 API calls，components 不直接 fetch
- **TypeScript strict mode**: 開啟 strict，所有 props 和 state 都要有型別

### Database
- PostgreSQL 16, 使用 JSONB 欄位存放彈性參數
- Alembic 管理 migration，每次 schema 變更都要建 migration
- Seed data 在應用啟動時檢查並自動載入內建模板

### Docker Compose Services
- `backend`: FastAPI app on port 8000
- `frontend`: Nginx serving React build on port 3000
- `postgres`: PostgreSQL 16 on port 5432
- Modbus TCP server: 由 backend 服務內部啟動，監聽 port 502

## Coding Conventions

### Python (Backend)
- Follow PEP 8, line length 100
- Use `async def` for all route handlers and service methods
- Type hints on all function signatures
- Docstrings on all public functions (Google style)
- Import order: stdlib → third-party → local (use isort)
- Use `logging` module, not print()
- Exception handling: 自訂 exception classes in `app/exceptions.py`

### TypeScript (Frontend)
- Strict mode enabled
- Functional components only (no class components)
- Use named exports (not default exports) except for pages
- Interface over type for object shapes
- Destructure props in function signature
- Use `const` by default, `let` only when mutation needed

### API Conventions
- All endpoints under `/api/v1/`
- Use plural nouns for resources: `/templates`, `/devices`
- Action endpoints use POST: `/devices/{id}/start`
- Return consistent response shape: `{ data, message, success }`
- Error responses: `{ detail: string, error_code: string }`
- HTTP status codes: 200 success, 201 created, 400 bad request, 404 not found, 422 validation error, 500 server error

### Git Conventions
- Branch naming: `feature/xxx`, `fix/xxx`, `refactor/xxx`
- Commit messages: conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`)
- PR required for merge to main

## Key Domain Concepts

### Device Template
定義一種設備的 register map。包含 register 的 address、data type、byte order、scale、unit。
內建模板（is_builtin=true）不可刪除。

### Device Instance
從 template 建立的虛擬設備，綁定一個 Modbus slave ID。
有獨立的運行狀態 (stopped/running/error) 和 register 值。

### Simulation Profile
控制每個 register 的數據產生方式。分三層：
1. **Data Mode**: 正常數據的產生方式 (static/random/daily_curve/computed/accumulator)
2. **Anomaly Injection**: 異常數據注入 (spike/drift/flatline/out_of_range/data_loss)
3. **Fault Simulation**: 通訊層故障 (delay/timeout/exception/intermittent)

### Protocol Adapter
可插拔的協議層。MVP 只有 Modbus TCP。
每個 adapter 實作 `start()`, `stop()`, `get_register_value()` 等介面。

## Common Tasks

### Start Development Environment
```bash
docker compose up -d postgres
cd backend && pip install -r requirements.txt
alembic upgrade head
python -m app.main

# In another terminal
cd frontend && npm install && npm run dev
```

### Run Tests
```bash
cd backend && pytest
cd frontend && npm test
```

### Create DB Migration
```bash
cd backend && alembic revision --autogenerate -m "description"
alembic upgrade head
```

### Add New Protocol (Future)
1. Create `backend/app/protocols/new_protocol.py`
2. Implement the `ProtocolAdapter` interface from `base.py`
3. Register in protocol factory
4. Add corresponding API routes if needed

## Important Notes

- Modbus TCP server 要在獨立的 asyncio task 中運行，不能 block FastAPI event loop
- pymodbus server 的 datastore 要跟 simulation engine 同步更新
- WebSocket 推送頻率預設 1 秒一次，可調整
- 所有時間用 UTC 存儲，前端轉換為 local time 顯示
- 內建模板的 register address 參考常見的 Eastron SDM630 / Fronius Symo 等真實設備
