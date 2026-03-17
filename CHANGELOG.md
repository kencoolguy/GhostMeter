# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Device template CRUD API (`/api/v1/templates`) — create, list, get, update, delete
- Register definition management with address overlap validation and data type constraints
- Template clone endpoint (`POST /api/v1/templates/{id}/clone`) with auto-generated name
- Template export endpoint (`GET /api/v1/templates/{id}/export`) — JSON file download
- Template import endpoint (`POST /api/v1/templates/import`) — JSON file upload
- Alembic migration for `device_templates` and `register_definitions` tables
- Seed data loader: auto-creates 3 built-in templates on startup (Three-Phase Meter / Single-Phase Meter / Solar Inverter)
- Built-in template protection: update and delete blocked with `403 BUILTIN_TEMPLATE_IMMUTABLE`
- `ForbiddenException` custom exception class with HTTP 403 response
- `ApiResponse[T]` generic envelope schema shared across all API responses
- Frontend Templates page: list view with template table, register count, built-in badge
- Frontend TemplateForm page: create/edit form with register map table
- Frontend RegisterTable component: add, remove, inline-edit registers with sort order
- Frontend ImportExportButtons component: JSON file upload and download
- Zustand `templateStore` for template list and selection state
- `templateApi` service for all `/api/v1/templates` Axios calls
- TypeScript interfaces for `DeviceTemplate`, `RegisterDefinition`, `TemplateSummary`, `TemplateDetail`
- React Router routes for `/templates/new` and `/templates/:id`
- Docker Compose setup with PostgreSQL 16, healthcheck, and env parameterization
- FastAPI backend with async lifespan, CORS, and structured logging
- Health check endpoint (`GET /health`) with DB connectivity verification
- Pydantic-settings configuration (auto-constructs DATABASE_URL from individual env vars)
- Async SQLAlchemy 2.0 engine + session factory with asyncpg
- Custom exception classes (AppException, NotFoundException, ValidationException) with global handlers
- Alembic setup with async SQLAlchemy support (migrations infrastructure, no tables yet)
- Backend test suite with pytest-asyncio (health endpoint tests)
- React 18 + TypeScript frontend with Vite build tool
- Ant Design 5 layout with collapsible sidebar navigation
- 4 placeholder pages: Templates, Devices, Simulation, Monitor
- React Router with nested layout routing
- Zustand store for UI state (sidebar collapsed)
- Axios API client with error interceptor
- Backend Dockerfile (python:3.12-slim)
- Frontend Dockerfile (multi-stage: node:22-alpine build → nginx:alpine serve)
- Nginx config with SPA fallback and API/WebSocket proxy
- `.env.example` with all configuration variables
