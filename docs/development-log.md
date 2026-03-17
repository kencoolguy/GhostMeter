# Development Log

## 2026-03-17 — Phase 2: Device Template Module

### What was done
- Implemented full device template CRUD backend (Tasks 1–11 of Phase 2 plan)
- Implemented frontend template management UI (Tasks 12–17 of Phase 2 plan)
- 24/24 backend tests passing; frontend build passes

### Backend highlights
- **ORM models**: `DeviceTemplate` + `RegisterDefinition` with cascade delete and two uniqueness constraints (name per template, address+FC per template)
- **Alembic migration**: `448f2e5c6613` creates both tables
- **Pydantic schemas**: `TemplateCreate`/`TemplateUpdate`/`TemplateDetail`/`TemplateSummary`/`TemplateClone` + shared `ApiResponse[T]` envelope
- **Service layer** (`template_service.py`): address overlap validation (per FC, per template), `ForbiddenException` guard on built-in templates for update/delete, export strips IDs for portability
- **API routes** (`/api/v1/templates`): list, create, get, update, delete, clone, export, import
- **Seed loader** (`seed/loader.py`): runs at FastAPI startup, idempotent — skips templates that already exist by name; loads three JSON files: `three_phase_meter.json` (SDM630), `single_phase_meter.json` (SDM120), `solar_inverter.json` (Fronius Symo / SunSpec)
- **Tests**: `test_templates.py` (API integration, 20 cases) + `test_seed.py` (4 cases)

### Frontend highlights
- **Types**: `DeviceTemplate`, `RegisterDefinition`, `TemplateSummary`, `TemplateDetail` in `src/types/template.ts`
- **API service**: `src/services/templateApi.ts` wraps all Axios calls
- **Zustand store**: `templateStore` holds list, loading state, and selected template
- **Pages**: `TemplateList` (table with built-in badge), `TemplateForm` (create/edit with register table), `RegisterTable` (editable rows), `ImportExportButtons`
- **Routing**: `/templates` → list, `/templates/new` → create, `/templates/:id` → edit

### Key decisions
- **PUT replaces registers wholesale**: simpler than PATCH + partial register diffs; client always sends the full register list
- **`/import` route must precede `/{template_id}`**: FastAPI path matching would otherwise treat the literal string `"import"` as a UUID, causing 422 errors
- **Seed data is idempotent**: loader checks name existence before insert; safe to run on every startup without duplicating templates
- **Address overlap uses half-open ranges per FC**: `float32` at address 0 occupies registers 0–1; any other register with address 1 in the same FC would overlap and is rejected
- **VirtualBox workaround carries over**: pytest and npm still run from outside the shared folder (`/home/ken/ghostmeter-venv` and `/home/ken/ghostmeter-node`)

### Issues encountered
- FastAPI route ordering: `/import` must be registered before `/{template_id}` to prevent the literal `"import"` being parsed as a UUID path parameter
- `updated_at` `onupdate` does not trigger on relationship mutations (registers replaced via `clear()` + reassign); workaround: the `get_template` re-fetch after commit returns the DB-refreshed value which is sufficient for tests

---

## 2026-03-17 — Phase 1: Project Skeleton & Foundation

### What was done
- Completed all 3 milestones of Phase 1 (Docker, Backend, Frontend)
- Full stack verified: `docker compose up --build` starts all 3 services successfully
- Backend health check returns `{"status":"ok","database":"connected","version":"0.1.0"}`
- Frontend serves Ant Design layout with 4 navigable pages via nginx

### Key decisions
- **Local dev approach**: Docker only for PostgreSQL, backend/frontend run natively for faster iteration
- **Port 5434**: PostgreSQL mapped to host port 5434 instead of 5432 due to port conflict with existing service on dev machine
- **DATABASE_URL construction**: Uses `@computed_field` to auto-build from individual `POSTGRES_*` env vars, allowing `.env` to be shared between docker-compose and backend app
- **Health endpoint at root**: `GET /health` is at root path (not under `/api/v1`) — exempt from standard response wrapper for infrastructure monitoring compatibility
- **Alembic migration deferred**: Only Alembic infrastructure set up in Phase 1; actual table migrations will be created in Phase 2 when ORM models are defined
- **VirtualBox workaround**: Python venv and npm node_modules stored outside shared folder due to symlink restrictions on vboxsf filesystem

### Issues encountered
- VirtualBox shared folder (`vboxsf`) does not support symlinks, which breaks both Python venv and npm node_modules creation. Solved by placing these in native Linux filesystem (`/tmp/` and `/home/ken/`).
- Port 5432 occupied by existing `enol-pgbouncer` container, switched to 5434.
