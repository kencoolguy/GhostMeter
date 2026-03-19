# GhostMeter Phase 7: System Finalization Design Spec

> Covers Milestone 7.1 (System Features), 7.2 (Testing & Quality), 7.3 (Release).

---

## Milestone 7.1: System Features

### 7.1.1 Config Import/Export (Full Snapshot)

#### Overview

Single JSON file containing all templates, devices, simulation configs, and anomaly schedules. Enables full environment migration between machines.

#### Export API

`GET /api/v1/system/export`

Response: JSON file download with `Content-Disposition: attachment`.

**Export format:**

```json
{
  "version": "1.0",
  "exported_at": "2026-03-19T12:00:00Z",
  "templates": [
    {
      "name": "SDM630 Three-Phase Meter",
      "manufacturer": "Eastron",
      "model": "SDM630",
      "description": "...",
      "is_builtin": false,
      "registers": [
        {
          "name": "voltage_l1",
          "address": 0,
          "data_type": "float32",
          "byte_order": "big",
          "function_code": 3,
          "scale_factor": 1.0,
          "unit": "V",
          "description": "Phase 1 Voltage"
        }
      ]
    }
  ],
  "devices": [
    {
      "name": "Meter-01",
      "template_name": "SDM630 Three-Phase Meter",
      "slave_id": 1,
      "port": 502,
      "description": "..."
    }
  ],
  "simulation_configs": [
    {
      "device_name": "Meter-01",
      "register_name": "voltage_l1",
      "data_mode": "daily_curve",
      "mode_params": {"base": 230, "amplitude": 10, "peak_hour": 14},
      "is_enabled": true,
      "update_interval_ms": 1000
    }
  ],
  "anomaly_schedules": [
    {
      "device_name": "Meter-01",
      "register_name": "voltage_l1",
      "anomaly_type": "spike",
      "anomaly_params": {"multiplier": 3.0, "probability": 0.1},
      "trigger_after_seconds": 300,
      "duration_seconds": 60,
      "is_enabled": true
    }
  ]
}
```

**Design decisions:**
- Reference by `name` (templates) and `device_name` + `template_name` (devices), not UUIDs — UUIDs are instance-specific and won't match across machines.
- Built-in templates (`is_builtin=true`) are included in export but skipped on import (already seeded).
- Devices reference templates by `template_name` — import validates template exists.

#### Import API

`POST /api/v1/system/import`

Request: JSON body (same format as export).

**Import behavior:**
1. Validate JSON format and `version` field.
2. **Templates**: Upsert by `name`. Skip built-in templates. Create new or update existing user templates.
3. **Devices**: Upsert by `(slave_id, port)`. Must reference an existing or just-imported template by `template_name`. Devices in `running` state are stopped before update.
4. **Simulation configs**: Replace all configs for each imported device. Delete existing → insert new.
5. **Anomaly schedules**: Replace all schedules for each imported device. Delete existing → insert new.

**All operations wrapped in a single DB transaction.** If any step fails, roll back entirely.

**Response:**

```json
{
  "success": true,
  "data": {
    "templates_created": 2,
    "templates_updated": 1,
    "templates_skipped": 3,
    "devices_created": 5,
    "devices_updated": 0,
    "simulation_configs_set": 15,
    "anomaly_schedules_set": 3
  },
  "message": "Import completed successfully"
}
```

**Error cases:**
- 400: Invalid JSON or missing `version`
- 422: Template referenced by device not found, invalid data mode, etc.
- 500: Transaction rollback on unexpected error

#### Frontend

Add a "System" section to the sidebar navigation (or a Settings page):
- **Export button**: `GET /api/v1/system/export` → browser downloads JSON file
- **Import button**: File picker → upload JSON → `POST /api/v1/system/import` → show result summary

Minimal UI — no new page needed. Can be placed in a dropdown menu in the sidebar header or as a simple Settings page with two buttons.

#### Files

| File | Purpose |
|------|---------|
| `backend/app/schemas/system.py` | Pydantic schemas for export/import format |
| `backend/app/services/system_service.py` | Export query + import upsert logic |
| `backend/app/api/routes/system.py` | API route handlers |
| `frontend/src/services/systemApi.ts` | API client for export/import |
| `frontend/src/pages/Settings/index.tsx` | Settings page with export/import buttons |

### 7.1.2 Docker Compose Production Config

Current `docker-compose.yml` already has:
- [x] Health checks for all services
- [x] `restart: unless-stopped`
- [x] Named volume `pgdata`
- [x] `env_file: .env`

**Remaining work:**
- Optimize backend Dockerfile with multi-stage build (separate dependency install from app copy for better caching)
- Add `.dockerignore` files to reduce build context

**Backend Dockerfile (optimized):**

```dockerfile
FROM python:3.12-slim AS base
WORKDIR /app

FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM deps AS app
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**backend/.dockerignore:**
```
__pycache__
*.pyc
.pytest_cache
tests/
alembic/versions/__pycache__
.ruff_cache
```

**frontend/.dockerignore:**
```
node_modules
dist
.vite
```

### 7.1.3 Ruff Lint Config

Already committed in `backend/pyproject.toml`. No further work needed.

---

## Milestone 7.2: Testing & Quality

### 7.2.1 Backend Test Coverage > 70%

**Current state:** ~163 tests across 16 test files.

**Approach:**
1. Run `pytest --cov=app --cov-report=term-missing` to measure current coverage.
2. Identify modules with lowest coverage.
3. Prioritize adding tests for:
   - New system export/import service
   - Any uncovered service methods
   - Edge cases in existing modules
4. Target: overall line coverage > 70%.

### 7.2.2 Frontend Smoke E2E Tests

**Tool:** Playwright

**Test cases (4-5):**

| Test | What it verifies |
|------|-----------------|
| Templates page loads | Navigate to `/templates`, table renders |
| Devices page loads | Navigate to `/devices`, page renders without error |
| Simulation page loads | Navigate to `/simulation`, page renders |
| Monitor page loads | Navigate to `/monitor`, card grid renders |
| Settings page loads | Navigate to `/settings`, export/import buttons visible |

**Setup:**
- `frontend/playwright.config.ts` — config file
- `frontend/e2e/smoke.spec.ts` — all smoke tests
- `frontend/package.json` — add `playwright` dev dependency + `test:e2e` script

**Note:** These tests run against the built frontend only (no backend needed for smoke). They verify pages load and critical UI elements render without JavaScript errors.

### 7.2.3 GitHub Actions CI

**File:** `.github/workflows/ci.yml`

**Triggers:** push to `dev`/`main`, PR to `dev`/`main`

**Backend job:**
- Python 3.12
- PostgreSQL 16 service container
- Install dependencies
- `ruff check .` (lint)
- `pytest --cov=app` (tests with coverage)

**Frontend job:**
- Node 20
- `npm ci`
- `npx tsc --noEmit` (type check)
- `npm run build` (build verification)
- Playwright smoke tests (against built files)

### 7.2.4 Documentation

**README.md:**
- Already comprehensive. Minor updates if needed after export/import feature.

**CONTRIBUTING.md:**
- Development setup instructions
- Branch naming convention
- Commit message format
- Test requirements
- PR process

---

## Milestone 7.3: Release

### GitHub Release v0.1.0

- Tag `v0.1.0` on `main` after all Phase 7 work is merged
- Release notes summarizing all features (Phase 1–7)
- No Docker Hub publish (deferred)
- No community outreach (deferred)

---

## Implementation Order

1. Config export/import (backend → frontend)
2. Dockerfile optimization + .dockerignore
3. Backend test coverage improvement
4. GitHub Actions CI
5. Frontend Playwright smoke tests
6. CONTRIBUTING.md
7. Update docs (CHANGELOG, dev-log, dev-phases)
8. Tag v0.1.0 release

---

## Files Summary

| File | Change |
|------|--------|
| `backend/app/schemas/system.py` | New: export/import Pydantic schemas |
| `backend/app/services/system_service.py` | New: export/import business logic |
| `backend/app/api/routes/system.py` | New: export/import API routes |
| `backend/tests/test_system_export_import.py` | New: export/import tests |
| `backend/Dockerfile` | Update: multi-stage build |
| `backend/.dockerignore` | New |
| `frontend/.dockerignore` | New |
| `frontend/src/services/systemApi.ts` | New: export/import API client |
| `frontend/src/pages/Settings/index.tsx` | New: settings page |
| `frontend/playwright.config.ts` | New: Playwright config |
| `frontend/e2e/smoke.spec.ts` | New: smoke tests |
| `.github/workflows/ci.yml` | New: CI pipeline |
| `CONTRIBUTING.md` | New |
| `CHANGELOG.md` | Update |
| `docs/development-log.md` | Update |
| `docs/development-phases.md` | Update |
