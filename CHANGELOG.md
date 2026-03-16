# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
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
