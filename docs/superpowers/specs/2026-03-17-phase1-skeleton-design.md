# Phase 1: Project Skeleton & Foundation — Design Spec

**Date**: 2026-03-17
**Branch**: `feature/claude-phase1-skeleton-20260317` (created from `dev`)
**Approach**: Bottom-up (Docker+DB → Backend → Frontend)

> **Note on `dev` branch**: The `dev` branch already exists and is the base for all feature branches per CLAUDE.md git workflow rules.

---

## Overview

Build the foundational infrastructure for GhostMeter: a working Docker + PostgreSQL setup, a FastAPI backend with DB connectivity and health check, and a React frontend with routing and layout. Each milestone is independently verifiable.

---

## Milestone 1.1: Docker + PostgreSQL

### Goal
`docker compose up postgres` starts a healthy PostgreSQL 16 instance that the backend can connect to.

### Changes
- **`docker-compose.yml`**: Add healthcheck for postgres, parameterize with env vars, comment out backend/frontend services (no Dockerfile yet)
- **`.env.example`**: Template for DB credentials, ports
- **`.env`**: Local copy (already in .gitignore)

### docker-compose.yml Design
```yaml
services:
  postgres:
    image: postgres:16
    container_name: ghostmeter-postgres
    env_file: .env
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-ghostmeter}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-ghostmeter}
      POSTGRES_DB: ${POSTGRES_DB:-ghostmeter}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-ghostmeter}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  pgdata:
```

### Acceptance Criteria
- `docker compose up -d postgres` starts successfully
- `docker compose ps` shows postgres as healthy
- Can connect from host: `psql -h localhost -U ghostmeter -d ghostmeter`

---

## Milestone 1.2: Backend Foundation

### Goal
FastAPI app starts, connects to PostgreSQL, runs Alembic migrations, and serves a health check endpoint.

### File Structure
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI entry with lifespan
│   ├── config.py            # pydantic-settings
│   ├── database.py          # async engine + session
│   ├── exceptions.py        # custom exceptions + global handler
│   └── api/
│       ├── __init__.py
│       └── routes/
│           ├── __init__.py
│           └── health.py    # GET /health
├── alembic.ini
├── alembic/
│   ├── env.py               # async migration support
│   ├── script.py.mako
│   └── versions/
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # async fixtures
│   └── test_health.py
├── requirements.txt
└── Dockerfile
```

### Key Components

**config.py** — `pydantic-settings` based:
- `DATABASE_URL`: Auto-constructed from individual env vars (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`) using a `@computed_field`. This allows `.env` to be shared with docker-compose without duplication. A direct `DATABASE_URL` override is also supported.
- `APP_NAME`, `APP_VERSION`, `DEBUG`, `LOG_LEVEL`
- Reads from environment variables / `.env` file

**database.py**:
- `create_async_engine` with `asyncpg`
- `async_sessionmaker` for request-scoped sessions
- `get_session` async generator for FastAPI dependency injection

**main.py**:
- `lifespan` context manager: test DB connection on startup, dispose engine on shutdown
- Mount API router under `/api/v1`
- Register exception handlers
- Configure CORS (allow frontend origin)
- Configure `logging` with structured format

**exceptions.py**:
- `AppException(status_code, error_code, detail)` — base custom exception
- `NotFoundException(AppException)` — 404
- `ValidationException(AppException)` — 422
- Global `app_exception_handler` returning `{ detail, error_code }`
- Generic 500 handler with logging

**health.py**:
- `GET /health` — returns `{ status: "ok"|"error", database: "connected"|"disconnected", version: "0.1.0" }`
- Executes `SELECT 1` to verify DB connectivity
- Note: `/health` is a system-level endpoint (not under `/api/v1/`) and is exempt from the standard `{ data, message, success }` response wrapper convention, as it serves infrastructure monitoring (load balancers, Docker healthcheck) which expect a simple shape.

**Alembic**:
- `alembic.ini` at `backend/` root, `sqlalchemy.url` overridden in `env.py` from config
- `env.py` uses `run_async` for async engine compatibility
- Empty initial `versions/` directory (no models yet)
- Note: `development-phases.md` Milestone 1.2 mentions "第一版 migration（所有表）", but since no ORM models exist yet, the actual table migrations will be created in Phase 2 when models are defined. Phase 1 only sets up Alembic infrastructure.

**Dockerfile**:
```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Tests**:
- `conftest.py`: async client fixture using `httpx.AsyncClient` + `ASGITransport`
- `test_health.py`: test health endpoint returns 200 with expected shape

### Dependencies (requirements.txt)
```
fastapi>=0.115
uvicorn[standard]>=0.34
sqlalchemy[asyncio]>=2.0
asyncpg>=0.30
alembic>=1.15
pydantic>=2.0
pydantic-settings>=2.0
python-dotenv>=1.0
pytest>=8.0
pytest-asyncio>=0.25
httpx>=0.28
```

### Acceptance Criteria
- `pip install -r requirements.txt` succeeds in a venv
- `alembic upgrade head` runs without error
- `python -m app.main` (or `uvicorn app.main:app`) starts on port 8000
- `GET /health` returns `200 { status: "ok", database: "connected", version: "0.1.0" }`
- `pytest` passes (health endpoint test)

---

## Milestone 1.3: Frontend Foundation

### Goal
Vite + React + TypeScript app with Ant Design layout, 4-page routing, Zustand store skeleton, and Axios API client.

### File Structure
```
frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx               # Router setup
│   ├── layouts/
│   │   └── MainLayout.tsx    # Sider + Header + Content
│   ├── pages/
│   │   ├── Templates/
│   │   │   └── index.tsx
│   │   ├── Devices/
│   │   │   └── index.tsx
│   │   ├── Simulation/
│   │   │   └── index.tsx
│   │   └── Monitor/
│   │       └── index.tsx
│   ├── components/           # empty for now
│   ├── stores/
│   │   └── appStore.ts       # UI state (sidebar collapsed)
│   ├── services/
│   │   └── api.ts            # Axios instance
│   └── types/
│       └── index.ts          # shared interfaces
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── Dockerfile
└── nginx.conf
```

### Key Components

**MainLayout.tsx**:
- Ant Design `Layout` with collapsible `Sider`
- Menu items: Templates (AppstoreOutlined), Devices (HddOutlined), Simulation (ExperimentOutlined), Monitor (DashboardOutlined)
- `Content` area renders child routes via `<Outlet />`
- Responsive: sider collapses on small screens

**Pages** (all placeholders):
- Each page: functional component with page title in Ant Design `Typography.Title`
- Will be filled in Phase 2-6

**App.tsx**:
- `BrowserRouter` with routes:
  - `/` → redirect to `/templates`
  - `/templates` → Templates page
  - `/devices` → Devices page
  - `/simulation` → Simulation page
  - `/monitor` → Monitor page
- All wrapped in `MainLayout`

**api.ts**:
- Axios instance with `baseURL: "/api/v1"`
- Response interceptor: on error, show Ant Design `message.error` with server detail
- Request interceptor: (placeholder for future auth headers)

**appStore.ts**:
- Zustand store: `{ sidebarCollapsed: boolean, toggleSidebar: () => void }`

**vite.config.ts**:
- Proxy: `/api` → `http://localhost:8000`
- `/ws` → `ws://localhost:8000` (for future WebSocket)

**Dockerfile** (multi-stage):
```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

**nginx.conf**:
- Serve static files from `/usr/share/nginx/html`
- SPA fallback: `try_files $uri $uri/ /index.html`
- Proxy `/api` → `http://backend:8000`
- Proxy `/ws` → `ws://backend:8000`

### Dependencies
```
react, react-dom
react-router-dom
antd, @ant-design/icons
zustand
axios
```

### Testing
- No test runner configured in Phase 1. Frontend testing (Vitest) will be set up in Phase 2 when there is actual logic to test.

### Acceptance Criteria
- `npm install && npm run dev` starts dev server
- Browser shows layout with sidebar, 4 pages navigable
- Sidebar highlights active page
- Axios client configured (can hit `/health` through vite proxy when backend is running)
- `npm run build` succeeds with no TypeScript errors

---

## Implementation Order

1. Milestone 1.1: Docker + PostgreSQL (~1 commit)
2. Milestone 1.2: Backend foundation (~2-3 commits)
3. Milestone 1.3: Frontend foundation (~2-3 commits)
4. Integration test: all three running together
5. Update docker-compose.yml to uncomment backend + frontend services

---

## Out of Scope

- Database models / migrations (Phase 2)
- Any business logic or real API endpoints (Phase 2+)
- Authentication / authorization
- CI/CD pipeline (Phase 7)
- Production optimizations
