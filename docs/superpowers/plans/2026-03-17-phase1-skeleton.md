# Phase 1: Project Skeleton & Foundation — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational infrastructure — Docker + PostgreSQL, FastAPI backend with health check, and React frontend with routing and layout.

**Architecture:** Bottom-up approach: database first, then backend API server, then frontend UI. Each milestone is independently verifiable. Local development with Docker only for PostgreSQL.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / asyncpg / Alembic / Pydantic v2 / React 18 / TypeScript / Vite / Ant Design 5 / Zustand / Axios

**Spec:** `docs/superpowers/specs/2026-03-17-phase1-skeleton-design.md`

---

## File Structure

### New files to create:

**Milestone 1.1 (Docker):**
- `.env.example` — Environment variable template
- `.env` — Local env (gitignored)

**Milestone 1.2 (Backend):**
- `backend/requirements.txt` — Python dependencies
- `backend/app/config.py` — pydantic-settings configuration
- `backend/app/database.py` — Async SQLAlchemy engine + session
- `backend/app/exceptions.py` — Custom exceptions + global handlers
- `backend/app/api/routes/health.py` — Health check endpoint
- `backend/app/main.py` — FastAPI app entry with lifespan
- `backend/alembic.ini` — Alembic configuration
- `backend/alembic/env.py` — Async Alembic env
- `backend/alembic/script.py.mako` — Migration template
- `backend/Dockerfile` — Backend container image
- `backend/tests/conftest.py` — Pytest async fixtures
- `backend/tests/test_health.py` — Health endpoint tests

**Milestone 1.3 (Frontend):**
- `frontend/package.json` — Node dependencies
- `frontend/tsconfig.json` — TypeScript config
- `frontend/tsconfig.node.json` — TS config for Vite
- `frontend/vite.config.ts` — Vite config with proxy
- `frontend/index.html` — HTML entry
- `frontend/src/main.tsx` — React entry
- `frontend/src/App.tsx` — Router setup
- `frontend/src/layouts/MainLayout.tsx` — Ant Design layout
- `frontend/src/pages/Templates/index.tsx` — Placeholder page
- `frontend/src/pages/Devices/index.tsx` — Placeholder page
- `frontend/src/pages/Simulation/index.tsx` — Placeholder page
- `frontend/src/pages/Monitor/index.tsx` — Placeholder page
- `frontend/src/stores/appStore.ts` — Zustand UI store
- `frontend/src/services/api.ts` — Axios instance
- `frontend/src/types/index.ts` — Shared interfaces
- `frontend/Dockerfile` — Frontend container image
- `frontend/nginx.conf` — Nginx config for SPA

### Files to modify:
- `docker-compose.yml` — Add healthcheck, env vars, commented services
- `.gitignore` — Add frontend build artifacts, venv

---

## Chunk 1: Docker + PostgreSQL (Milestone 1.1)

### Task 1: Setup environment files and update docker-compose

**Files:**
- Create: `.env.example`
- Create: `.env`
- Modify: `docker-compose.yml`
- Modify: `.gitignore`

- [ ] **Step 1: Create `.env.example`**

```ini
# PostgreSQL
POSTGRES_USER=ghostmeter
POSTGRES_PASSWORD=ghostmeter
POSTGRES_DB=ghostmeter
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Backend
APP_NAME=GhostMeter
APP_VERSION=0.1.0
DEBUG=true
LOG_LEVEL=INFO
```

- [ ] **Step 2: Create `.env` from `.env.example`**

```bash
cp .env.example .env
```

- [ ] **Step 3: Verify `.gitignore` already covers needed entries**

The existing `.gitignore` already includes `.env`, `__pycache__/`, `.venv/`, `node_modules/`, `frontend/dist/`, etc. No changes needed.

- [ ] **Step 4: Rewrite `docker-compose.yml`**

Note: This replaces the existing `docker-compose.yml` which has simplified service definitions without healthcheck or env parameterization.

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

  # Uncomment after Dockerfiles are ready:
  # backend:
  #   build: ./backend
  #   container_name: ghostmeter-backend
  #   env_file: .env
  #   environment:
  #     POSTGRES_HOST: postgres
  #     DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-ghostmeter}:${POSTGRES_PASSWORD:-ghostmeter}@postgres:5432/${POSTGRES_DB:-ghostmeter}
  #   ports:
  #     - "8000:8000"
  #     - "502:502"
  #   depends_on:
  #     postgres:
  #       condition: service_healthy
  #   restart: unless-stopped

  # frontend:
  #   build: ./frontend
  #   container_name: ghostmeter-frontend
  #   ports:
  #     - "3000:80"
  #   depends_on:
  #     - backend
  #   restart: unless-stopped

volumes:
  pgdata:
```

- [ ] **Step 5: Verify PostgreSQL starts**

Run:
```bash
docker compose up -d postgres
```
Expected: Container starts successfully.

Then:
```bash
docker compose ps
```
Expected: `ghostmeter-postgres` shows `healthy` status (may take ~30s).

- [ ] **Step 6: Verify DB connectivity**

Run:
```bash
docker compose exec postgres psql -U ghostmeter -d ghostmeter -c "SELECT 1;"
```
Expected: Returns `1` successfully.

- [ ] **Step 7: Commit**

```bash
git add .env.example docker-compose.yml .gitignore
git commit -m "feat: setup Docker PostgreSQL with healthcheck and env config"
```

---

## Chunk 2: Backend Foundation — Config, DB, Exceptions (Milestone 1.2 part 1)

### Task 2: Create requirements.txt and virtual environment

**Files:**
- Create: `backend/requirements.txt`

- [ ] **Step 1: Create `backend/requirements.txt`**

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

- [ ] **Step 2: Create venv and install dependencies**

Run:
```bash
cd backend && python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```
Expected: All packages install successfully.

- [ ] **Step 3: Verify installation**

Run (from `backend/` with venv active):
```bash
python -c "import fastapi; import sqlalchemy; import asyncpg; print('OK')"
```
Expected: Prints `OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat: add backend Python dependencies"
```

---

### Task 3: Implement config.py

**Files:**
- Create: `backend/app/config.py`

- [ ] **Step 1: Write `backend/app/config.py`**

```python
from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    APP_NAME: str = "GhostMeter"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # PostgreSQL (individual vars shared with docker-compose)
    POSTGRES_USER: str = "ghostmeter"
    POSTGRES_PASSWORD: str = "ghostmeter"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "ghostmeter"

    # Direct override (takes precedence if set)
    DATABASE_URL: str | None = None

    @computed_field
    @property
    def database_url_computed(self) -> str:
        """Build DATABASE_URL from individual vars, or use direct override."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
```

- [ ] **Step 2: Verify config loads**

Run (from `backend/` with venv active):
```bash
python -c "from app.config import get_settings; s = get_settings(); print(s.database_url_computed)"
```
Expected: Prints `postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5432/ghostmeter`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add pydantic-settings config with DATABASE_URL construction"
```

---

### Task 4: Implement database.py

**Files:**
- Create: `backend/app/database.py`

- [ ] **Step 1: Write `backend/app/database.py`**

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url_computed,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session for FastAPI dependency injection."""
    async with async_session_factory() as session:
        yield session
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/database.py
git commit -m "feat: add async SQLAlchemy engine and session factory"
```

---

### Task 5: Implement exceptions.py

**Files:**
- Create: `backend/app/exceptions.py`

- [ ] **Step 1: Write `backend/app/exceptions.py`**

```python
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        detail: str = "An unexpected error occurred",
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail
        super().__init__(detail)


class NotFoundException(AppException):
    """Resource not found."""

    def __init__(self, detail: str = "Resource not found") -> None:
        super().__init__(status_code=404, error_code="NOT_FOUND", detail=detail)


class ValidationException(AppException):
    """Validation error."""

    def __init__(self, detail: str = "Validation error") -> None:
        super().__init__(status_code=422, error_code="VALIDATION_ERROR", detail=detail)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": exc.error_code},
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with logging."""
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_code": "INTERNAL_ERROR"},
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/exceptions.py
git commit -m "feat: add custom exception classes and global handlers"
```

---

## Chunk 3: Backend Foundation — Health, Main, Alembic, Tests (Milestone 1.2 part 2)

### Task 6: Implement health endpoint

**Files:**
- Create: `backend/app/api/routes/health.py`

- [ ] **Step 1: Write `backend/app/api/routes/health.py`**

```python
import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.database import engine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint with DB connectivity status.

    Returns:
        Dict with status, database connectivity, and app version.
    """
    settings = get_settings()
    db_status = "connected"

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.warning("Database health check failed", exc_info=True)
        db_status = "disconnected"

    status = "ok" if db_status == "connected" else "error"

    return {
        "status": status,
        "database": db_status,
        "version": settings.APP_VERSION,
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes/health.py
git commit -m "feat: add health check endpoint with DB connectivity"
```

---

### Task 7: Implement main.py (FastAPI app entry)

**Files:**
- Create: `backend/app/main.py`

- [ ] **Step 1: Write `backend/app/main.py`**

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.config import get_settings
from app.database import engine
from app.exceptions import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
)

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)

    # Verify DB connection on startup
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
    except Exception:
        logger.error("Database connection failed", exc_info=True)

    yield

    # Shutdown
    await engine.dispose()
    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Routes — health at root, API routes under /api/v1
app.include_router(health_router)
api_v1_router = APIRouter(prefix="/api/v1")
# Future route routers will be included here:
# api_v1_router.include_router(templates_router, prefix="/templates", tags=["templates"])
app.include_router(api_v1_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
```

- [ ] **Step 2: Verify app starts**

Run (from `backend/` with venv active, postgres running):
```bash
python -m app.main
```
Expected: Uvicorn starts on port 8000, logs show "Database connection verified".

- [ ] **Step 3: Verify health endpoint**

Run (in another terminal):
```bash
curl http://localhost:8000/health
```
Expected: `{"status":"ok","database":"connected","version":"0.1.0"}`

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: add FastAPI app with lifespan, CORS, and exception handlers"
```

---

### Task 8: Setup Alembic for async migrations

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/` (empty directory)

- [ ] **Step 1: Write `backend/alembic.ini`**

```ini
[alembic]
script_location = alembic
# sqlalchemy.url is overridden in env.py from app config

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Write `backend/alembic/env.py`**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.database import Base

# Alembic Config object
config = context.config

# Set sqlalchemy.url from app config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url_computed)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Configure context and run migrations."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Write `backend/alembic/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Create empty versions directory**

```bash
mkdir -p backend/alembic/versions
touch backend/alembic/versions/.gitkeep
```

- [ ] **Step 5: Verify Alembic runs**

Run (from `backend/` with venv active, postgres running):
```bash
alembic upgrade head
```
Expected: Runs without error (no migrations to apply yet, but connection succeeds).

- [ ] **Step 6: Commit**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat: setup Alembic with async SQLAlchemy support"
```

---

### Task 9: Write backend tests

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Write `backend/tests/conftest.py`**

```python
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for testing FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

- [ ] **Step 2: Write `backend/tests/test_health.py`**

```python
async def test_health_returns_200(client):
    """Health endpoint should return 200 with expected fields."""
    response = await client.get("/health")

    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "version" in data
    assert data["version"] == "0.1.0"


async def test_health_status_values(client):
    """Health endpoint status should be 'ok' or 'error'."""
    response = await client.get("/health")
    data = response.json()

    assert data["status"] in ("ok", "error")
    assert data["database"] in ("connected", "disconnected")
```

Note: No `@pytest.mark.asyncio` needed — `asyncio_mode = "auto"` in pyproject.toml auto-detects async test functions.

- [ ] **Step 3: Create `backend/pyproject.toml` for pytest config**

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 4: Run tests**

Run (from `backend/` with venv active, postgres running):
```bash
pytest tests/ -v
```
Expected: Both tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_health.py backend/pyproject.toml
git commit -m "test: add health endpoint tests with async client"
```

---

### Task 10: Create backend Dockerfile

**Files:**
- Create: `backend/Dockerfile`

- [ ] **Step 1: Write `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Verify Docker build**

Run:
```bash
docker build -t ghostmeter-backend ./backend
```
Expected: Build completes successfully.

- [ ] **Step 3: Commit**

```bash
git add backend/Dockerfile
git commit -m "feat: add backend Dockerfile"
```

---

## Chunk 4: Frontend Foundation (Milestone 1.3)

### Task 11: Initialize Vite + React + TypeScript project

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/vite.config.ts`, `frontend/index.html`, `frontend/src/vite-env.d.ts`

- [ ] **Step 1: Scaffold Vite project**

Run:
```bash
cd frontend && npm create vite@latest . -- --template react-ts
```
Expected: Scaffolds React + TypeScript project in `frontend/`. If prompted about existing files, choose to overwrite (the `src/` dir is empty anyway).

- [ ] **Step 2: Install dependencies**

Run (from `frontend/`):
```bash
npm install
npm install antd @ant-design/icons react-router-dom zustand axios
```
Expected: All packages install successfully.

- [ ] **Step 3: Update `frontend/vite.config.ts` with proxy**

```typescript
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
  },
});
```

- [ ] **Step 4: Verify dev server starts**

Run (from `frontend/`):
```bash
npm run dev
```
Expected: Vite dev server starts on port 5173.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/tsconfig.node.json frontend/tsconfig.app.json frontend/vite.config.ts frontend/index.html frontend/src/vite-env.d.ts frontend/eslint.config.js
git commit -m "feat: initialize Vite React TypeScript project with dependencies"
```

Note: The exact config files generated by `npm create vite@latest` may vary. Add all generated config files.

---

### Task 12: Create shared types, API client, and Zustand store

**Files:**
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/services/api.ts`
- Create: `frontend/src/stores/appStore.ts`

- [ ] **Step 1: Write `frontend/src/types/index.ts`**

```typescript
export interface HealthResponse {
  status: "ok" | "error";
  database: "connected" | "disconnected";
  version: string;
}

export interface ApiErrorResponse {
  detail: string;
  error_code: string;
}
```

- [ ] **Step 2: Write `frontend/src/services/api.ts`**

```typescript
import { message } from "antd";
import axios from "axios";
import type { ApiErrorResponse } from "../types";

const api = axios.create({
  baseURL: "/api/v1",
  timeout: 10000,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.data) {
      const data = error.response.data as ApiErrorResponse;
      message.error(data.detail || "An error occurred");
    } else if (error.message) {
      message.error(error.message);
    }
    return Promise.reject(error);
  }
);

export { api };
```

- [ ] **Step 3: Write `frontend/src/stores/appStore.ts`**

```typescript
import { create } from "zustand";

interface AppState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  sidebarCollapsed: false,
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
}));
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/services/api.ts frontend/src/stores/appStore.ts
git commit -m "feat: add TypeScript types, Axios API client, and Zustand store"
```

---

### Task 13: Create layout and pages

**Files:**
- Create: `frontend/src/layouts/MainLayout.tsx`
- Create: `frontend/src/pages/Templates/index.tsx`
- Create: `frontend/src/pages/Devices/index.tsx`
- Create: `frontend/src/pages/Simulation/index.tsx`
- Create: `frontend/src/pages/Monitor/index.tsx`

- [ ] **Step 1: Write `frontend/src/layouts/MainLayout.tsx`**

```tsx
import {
  AppstoreOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  HddOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, theme } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAppStore } from "../stores/appStore";

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: "/templates", icon: <AppstoreOutlined />, label: "Templates" },
  { key: "/devices", icon: <HddOutlined />, label: "Devices" },
  { key: "/simulation", icon: <ExperimentOutlined />, label: "Simulation" },
  { key: "/monitor", icon: <DashboardOutlined />, label: "Monitor" },
];

export function MainLayout() {
  const { sidebarCollapsed, toggleSidebar } = useAppStore();
  const navigate = useNavigate();
  const location = useLocation();
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={sidebarCollapsed}
        breakpoint="lg"
        onBreakpoint={(broken) => {
          if (broken && !sidebarCollapsed) {
            toggleSidebar();
          }
        }}
      >
        <div
          style={{
            height: 32,
            margin: 16,
            color: "white",
            fontWeight: "bold",
            fontSize: sidebarCollapsed ? 14 : 18,
            textAlign: "center",
            lineHeight: "32px",
          }}
        >
          {sidebarCollapsed ? "GM" : "GhostMeter"}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            padding: "0 16px",
            background: colorBgContainer,
            display: "flex",
            alignItems: "center",
          }}
        >
          <Button
            type="text"
            icon={
              sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />
            }
            onClick={toggleSidebar}
          />
        </Header>
        <Content
          style={{
            margin: 24,
            padding: 24,
            background: colorBgContainer,
            borderRadius: borderRadiusLG,
            minHeight: 280,
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
```

- [ ] **Step 2: Write page placeholders**

`frontend/src/pages/Templates/index.tsx`:
```tsx
import { Typography } from "antd";

export default function TemplatesPage() {
  return <Typography.Title level={2}>Device Templates</Typography.Title>;
}
```

`frontend/src/pages/Devices/index.tsx`:
```tsx
import { Typography } from "antd";

export default function DevicesPage() {
  return <Typography.Title level={2}>Device Instances</Typography.Title>;
}
```

`frontend/src/pages/Simulation/index.tsx`:
```tsx
import { Typography } from "antd";

export default function SimulationPage() {
  return <Typography.Title level={2}>Simulation Control</Typography.Title>;
}
```

`frontend/src/pages/Monitor/index.tsx`:
```tsx
import { Typography } from "antd";

export default function MonitorPage() {
  return <Typography.Title level={2}>Real-time Monitor</Typography.Title>;
}
```

- [ ] **Step 3: Create empty components directory**

```bash
mkdir -p frontend/src/components
touch frontend/src/components/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/layouts/ frontend/src/pages/ frontend/src/components/.gitkeep
git commit -m "feat: add MainLayout with sidebar and placeholder pages"
```

---

### Task 14: Wire up App.tsx, main.tsx, and verify

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Rewrite `frontend/src/App.tsx`**

```tsx
import { Navigate, Route, Routes } from "react-router-dom";
import { MainLayout } from "./layouts/MainLayout";
import DevicesPage from "./pages/Devices";
import MonitorPage from "./pages/Monitor";
import SimulationPage from "./pages/Simulation";
import TemplatesPage from "./pages/Templates";

function App() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/devices" element={<DevicesPage />} />
        <Route path="/simulation" element={<SimulationPage />} />
        <Route path="/monitor" element={<MonitorPage />} />
        <Route path="/" element={<Navigate to="/templates" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
```

- [ ] **Step 2: Rewrite `frontend/src/main.tsx`**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);
```

- [ ] **Step 3: Remove Vite scaffold files we don't need**

```bash
rm -f frontend/src/App.css frontend/src/index.css frontend/src/assets/react.svg
```

- [ ] **Step 4: Verify — run dev server and check UI**

Run (from `frontend/`):
```bash
npm run dev
```
Open `http://localhost:5173` in browser.
Expected:
- Layout with dark sidebar showing 4 menu items
- Clicking each menu item navigates to the correct page
- Sidebar collapses/expands with the toggle button
- URL defaults to `/templates`

- [ ] **Step 5: Verify — TypeScript build**

Run (from `frontend/`):
```bash
npm run build
```
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/main.tsx
git commit -m "feat: wire up React Router with layout and page navigation"
```

---

### Task 15: Create frontend Dockerfile and nginx.conf

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`

- [ ] **Step 1: Write `frontend/Dockerfile`**

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

- [ ] **Step 2: Write `frontend/nginx.conf`**

```nginx
server {
    listen 80;
    server_name localhost;
    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API proxy
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Health proxy
    location /health {
        proxy_pass http://backend:8000;
    }

    # WebSocket proxy
    location /ws/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

- [ ] **Step 3: Create `frontend/.dockerignore`**

```
node_modules
dist
.git
```

- [ ] **Step 4: Verify Docker build**

Run:
```bash
docker build -t ghostmeter-frontend ./frontend
```
Expected: Build completes successfully (multi-stage: npm build → nginx).

- [ ] **Step 5: Commit**

```bash
git add frontend/Dockerfile frontend/nginx.conf frontend/.dockerignore
git commit -m "feat: add frontend Dockerfile and nginx config"
```

---

## Chunk 5: Integration & Finalization

### Task 16: Integration verification and docker-compose activation

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Local integration test**

Start all services locally:
```bash
# Terminal 1: postgres (already running from Task 1)
docker compose up -d postgres

# Terminal 2: backend
cd backend && source .venv/bin/activate && python -m app.main

# Terminal 3: frontend
cd frontend && npm run dev
```

Verify:
- `curl http://localhost:8000/health` → `{"status":"ok","database":"connected","version":"0.1.0"}`
- Open `http://localhost:5173` → Layout with 4 pages
- Navigate between pages → sidebar highlights correct item

- [ ] **Step 2: Uncomment backend and frontend in docker-compose.yml**

Update `docker-compose.yml` to uncomment the backend and frontend service blocks (remove `#` from lines added in Task 1).

- [ ] **Step 3: Verify full Docker Compose stack**

Run:
```bash
docker compose up --build -d
```
Expected: All 3 services start. `docker compose ps` shows all healthy/running.

Then:
```bash
curl http://localhost:8000/health
```
Expected: `{"status":"ok","database":"connected","version":"0.1.0"}`

Open `http://localhost:3000` in browser.
Expected: Same layout as dev mode.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: activate backend and frontend in docker-compose"
```

---

### Task 17: Update project documentation

**Files:**
- Modify: `docs/development-phases.md`
- Modify: `docs/development-log.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update `docs/development-phases.md`**

Mark Milestone 1.1, 1.2, 1.3 items as completed (`[x]`). Add note that Alembic "all tables" migration deferred to Phase 2.

- [ ] **Step 2: Update `docs/development-log.md`**

Add entry for Phase 1 implementation: what was done, key decisions, any issues encountered.

- [ ] **Step 3: Update `CHANGELOG.md`**

Add Phase 1 entries under `[Unreleased]`:
- Docker Compose with PostgreSQL healthcheck
- FastAPI backend with health check endpoint
- Async SQLAlchemy + Alembic setup
- React frontend with Ant Design layout and routing
- Backend and frontend Dockerfiles

- [ ] **Step 4: Commit**

```bash
git add docs/development-phases.md docs/development-log.md CHANGELOG.md
git commit -m "docs: update project docs for Phase 1 completion"
```

---

### Task 18: Push and create PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin feature/claude-phase1-skeleton-20260317
```

- [ ] **Step 2: Create PR to dev**

```bash
gh pr create --base dev --title "feat: Phase 1 — project skeleton and foundation" --body "$(cat <<'EOF'
## Summary
- Docker Compose with PostgreSQL 16 (healthcheck, env config)
- FastAPI backend: config, async DB, health endpoint, exceptions, Alembic
- React frontend: Vite + TypeScript, Ant Design layout, 4-page routing, Zustand, Axios
- Dockerfiles for both backend and frontend

## Test plan
- [ ] `docker compose up -d postgres` starts healthy DB
- [ ] Backend: `pytest` passes (health endpoint tests)
- [ ] Backend: `GET /health` returns connected status
- [ ] Frontend: `npm run dev` shows layout with 4 navigable pages
- [ ] Frontend: `npm run build` succeeds with no TS errors
- [ ] Full stack: `docker compose up --build` runs all 3 services

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Return PR URL to user**
