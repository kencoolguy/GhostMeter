# Simulation Profiles Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Auto-apply physically consistent simulation parameters when creating devices, via a reusable `simulation_profiles` table.

**Architecture:** New `simulation_profiles` table stores reusable parameter sets. Built-in profiles are loaded from seed JSON files at startup. When a device is created, the default profile for its template is automatically expanded into `simulation_configs` rows. Profile CRUD API allows users to create custom profiles.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16, pytest + httpx

**Spec:** `docs/superpowers/specs/2026-03-24-simulation-profiles-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/models/simulation_profile.py` | Create | ORM model for `simulation_profiles` table |
| `backend/app/models/__init__.py` | Modify | Register new model |
| `backend/app/schemas/simulation_profile.py` | Create | Pydantic request/response schemas |
| `backend/app/schemas/device.py` | Modify | Add `profile_id` to DeviceCreate / DeviceBatchCreate |
| `backend/app/services/simulation_profile_service.py` | Create | CRUD + apply logic |
| `backend/app/services/device_service.py` | Modify | Call profile apply on create |
| `backend/app/api/routes/simulation_profiles.py` | Create | REST endpoints |
| `backend/app/main.py` | Modify | Register new router |
| `backend/app/seed/loader.py` | Modify | Add profile seed loading |
| `backend/app/seed/profiles/three_phase_meter_normal.json` | Create | Seed data |
| `backend/app/seed/profiles/single_phase_meter_normal.json` | Create | Seed data |
| `backend/app/seed/profiles/solar_inverter_normal.json` | Create | Seed data |
| `backend/tests/conftest.py` | Modify | Add `simulation_profiles` to TRUNCATE |
| `backend/tests/test_simulation_profiles.py` | Create | Profile CRUD API tests |
| `backend/tests/test_device_profile_apply.py` | Create | Profile auto-apply tests |
| `backend/tests/test_seed_profiles.py` | Create | Seed loading tests |
| `backend/alembic/versions/xxxx_add_simulation_profiles.py` | Create | Migration |

---

## Chunk 1: Model, Schema, Migration

### Task 1: ORM Model

**Files:**
- Create: `backend/app/models/simulation_profile.py`
- Modify: `backend/app/models/__init__.py`

- [x] **Step 1: Create ORM model**

```python
# backend/app/models/simulation_profile.py
"""ORM model for simulation profiles."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class SimulationProfile(Base):
    """Reusable set of simulation parameters for a device template."""

    __tablename__ = "simulation_profiles"
    __table_args__ = (
        UniqueConstraint(
            "template_id", "name",
            name="uq_simulation_profile_template_name",
        ),
        Index(
            "ix_simulation_profiles_default",
            "template_id",
            unique=True,
            postgresql_where=text("is_default = true"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_templates.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    configs: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
```

- [x] **Step 2: Register in models/__init__.py**

Add to `backend/app/models/__init__.py`:

```python
from app.models.simulation_profile import SimulationProfile
# Add "SimulationProfile" to __all__
```

- [x] **Step 3: Create Alembic migration**

Run:
```bash
cd backend && alembic revision --autogenerate -m "add simulation_profiles table"
```

- [x] **Step 4: Apply migration**

Run:
```bash
cd backend && alembic upgrade head
```
Expected: Migration applies successfully, `simulation_profiles` table created.

- [x] **Step 5: Commit**

```bash
git add backend/app/models/simulation_profile.py backend/app/models/__init__.py backend/alembic/versions/*simulation_profiles*
git commit -m "feat: add SimulationProfile ORM model and migration"
```

---

### Task 2: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/simulation_profile.py`

- [x] **Step 1: Create schemas**

```python
# backend/app/schemas/simulation_profile.py
"""Pydantic schemas for simulation profile API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.simulation import VALID_DATA_MODES


class ProfileConfigEntry(BaseModel):
    """A single register config entry within a profile."""

    register_name: str
    data_mode: str
    mode_params: dict[str, Any] = {}
    is_enabled: bool = True
    update_interval_ms: int = 1000

    @field_validator("data_mode")
    @classmethod
    def validate_data_mode(cls, v: str) -> str:
        if v not in VALID_DATA_MODES:
            raise ValueError(f"data_mode must be one of {VALID_DATA_MODES}")
        return v

    @field_validator("update_interval_ms")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        if v < 100:
            raise ValueError("update_interval_ms must be >= 100")
        if v > 60000:
            raise ValueError("update_interval_ms must be <= 60000")
        return v


class SimulationProfileCreate(BaseModel):
    """Schema for creating a simulation profile."""

    template_id: UUID
    name: str
    description: str | None = None
    is_default: bool = False
    configs: list[ProfileConfigEntry]

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > 200:
            raise ValueError("name must not exceed 200 characters")
        return v


class SimulationProfileUpdate(BaseModel):
    """Schema for updating a simulation profile."""

    name: str | None = None
    description: str | None = None
    is_default: bool | None = None
    configs: list[ProfileConfigEntry] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("name must not be empty")
            if len(v) > 200:
                raise ValueError("name must not exceed 200 characters")
        return v


class SimulationProfileResponse(BaseModel):
    """Schema for profile in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    name: str
    description: str | None
    is_builtin: bool
    is_default: bool
    configs: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
```

- [x] **Step 2: Commit**

```bash
git add backend/app/schemas/simulation_profile.py
git commit -m "feat: add Pydantic schemas for simulation profiles"
```

---

### Task 3: Modify DeviceCreate Schema

**Files:**
- Modify: `backend/app/schemas/device.py`

- [x] **Step 1: Add profile_id to DeviceCreate and DeviceBatchCreate**

In `backend/app/schemas/device.py`, add `profile_id` field to both schemas:

```python
class DeviceCreate(BaseModel):
    """Schema for creating a single device."""

    template_id: UUID
    name: str
    slave_id: int
    port: int = 502
    description: str | None = None
    profile_id: UUID | None = None  # See model_fields_set for absent vs null

    # ... existing validator unchanged ...


class DeviceBatchCreate(BaseModel):
    """Schema for batch creating devices."""

    template_id: UUID
    slave_id_start: int
    slave_id_end: int
    port: int = 502
    name_prefix: str | None = None
    description: str | None = None
    profile_id: UUID | None = None  # See model_fields_set for absent vs null

    # ... existing validators unchanged ...
```

**Implementation note**: The service layer uses `"profile_id" in data.model_fields_set` to distinguish:
- `profile_id` absent from JSON → auto-apply default
- `profile_id` explicitly `null` → skip profile
- `profile_id` is UUID → apply that specific profile

- [x] **Step 2: Commit**

```bash
git add backend/app/schemas/device.py
git commit -m "feat: add profile_id field to DeviceCreate and DeviceBatchCreate"
```

---

## Chunk 2: Service Layer

### Task 4: Profile CRUD Service

**Files:**
- Create: `backend/app/services/simulation_profile_service.py`

- [x] **Step 1: Write failing test for profile creation**

Create `backend/tests/test_simulation_profiles.py`:

```python
"""Integration tests for simulation profile CRUD API."""

import uuid

from httpx import AsyncClient


TEMPLATE_PAYLOAD = {
    "name": "Profile Test Meter",
    "protocol": "modbus_tcp",
    "registers": [
        {
            "name": "voltage",
            "address": 0,
            "function_code": 4,
            "data_type": "float32",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "V",
            "description": "Voltage",
            "sort_order": 0,
        },
        {
            "name": "current",
            "address": 2,
            "function_code": 4,
            "data_type": "float32",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "A",
            "description": "Current",
            "sort_order": 1,
        },
    ],
}

PROFILE_CONFIGS = [
    {
        "register_name": "voltage",
        "data_mode": "random",
        "mode_params": {"base": 220, "amplitude": 3, "distribution": "gaussian"},
    },
    {
        "register_name": "current",
        "data_mode": "daily_curve",
        "mode_params": {"base": 8, "amplitude": 6, "peak_hour": 14},
    },
]


async def _create_template(client: AsyncClient) -> str:
    """Helper: create a template and return template_id."""
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


class TestCreateProfile:
    async def test_create_profile_success(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Normal Operation",
            "description": "Test profile",
            "is_default": True,
            "configs": PROFILE_CONFIGS,
        }
        resp = await client.post("/api/v1/simulation-profiles", json=payload)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Normal Operation"
        assert data["is_default"] is True
        assert data["is_builtin"] is False
        assert len(data["configs"]) == 2

    async def test_create_profile_invalid_template(self, client: AsyncClient) -> None:
        payload = {
            "template_id": str(uuid.uuid4()),
            "name": "Bad Profile",
            "configs": PROFILE_CONFIGS,
        }
        resp = await client.post("/api/v1/simulation-profiles", json=payload)
        assert resp.status_code == 404

    async def test_create_duplicate_name_same_template(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Same Name",
            "configs": PROFILE_CONFIGS,
        }
        resp1 = await client.post("/api/v1/simulation-profiles", json=payload)
        assert resp1.status_code == 201
        resp2 = await client.post("/api/v1/simulation-profiles", json=payload)
        assert resp2.status_code == 409

    async def test_create_second_default_clears_first(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload1 = {
            "template_id": template_id,
            "name": "First Default",
            "is_default": True,
            "configs": PROFILE_CONFIGS,
        }
        resp1 = await client.post("/api/v1/simulation-profiles", json=payload1)
        assert resp1.status_code == 201
        first_id = resp1.json()["data"]["id"]

        payload2 = {
            "template_id": template_id,
            "name": "Second Default",
            "is_default": True,
            "configs": PROFILE_CONFIGS,
        }
        resp2 = await client.post("/api/v1/simulation-profiles", json=payload2)
        assert resp2.status_code == 201

        # First profile should no longer be default
        resp = await client.get(f"/api/v1/simulation-profiles/{first_id}")
        assert resp.json()["data"]["is_default"] is False


class TestListProfiles:
    async def test_list_by_template(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Test Profile",
            "configs": PROFILE_CONFIGS,
        }
        await client.post("/api/v1/simulation-profiles", json=payload)
        resp = await client.get(
            f"/api/v1/simulation-profiles?template_id={template_id}"
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    async def test_list_empty(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        resp = await client.get(
            f"/api/v1/simulation-profiles?template_id={template_id}"
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestGetProfile:
    async def test_get_by_id(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Get Test",
            "configs": PROFILE_CONFIGS,
        }
        resp = await client.post("/api/v1/simulation-profiles", json=payload)
        profile_id = resp.json()["data"]["id"]
        resp = await client.get(f"/api/v1/simulation-profiles/{profile_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Get Test"

    async def test_get_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.get(
            f"/api/v1/simulation-profiles/{uuid.uuid4()}"
        )
        assert resp.status_code == 404


class TestUpdateProfile:
    async def test_update_name(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Original",
            "configs": PROFILE_CONFIGS,
        }
        resp = await client.post("/api/v1/simulation-profiles", json=payload)
        profile_id = resp.json()["data"]["id"]
        resp = await client.put(
            f"/api/v1/simulation-profiles/{profile_id}",
            json={"name": "Updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Updated"

    async def test_update_builtin_configs_rejected(self, client: AsyncClient) -> None:
        # Seed profiles are builtin — we'll test this via seed test
        # For now, test that updating configs on a non-builtin works
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Updatable",
            "configs": PROFILE_CONFIGS,
        }
        resp = await client.post("/api/v1/simulation-profiles", json=payload)
        profile_id = resp.json()["data"]["id"]
        new_configs = [
            {
                "register_name": "voltage",
                "data_mode": "static",
                "mode_params": {"value": 230},
            },
        ]
        resp = await client.put(
            f"/api/v1/simulation-profiles/{profile_id}",
            json={"configs": new_configs},
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]["configs"]) == 1


class TestDeleteProfile:
    async def test_delete_custom_profile(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Deletable",
            "configs": PROFILE_CONFIGS,
        }
        resp = await client.post("/api/v1/simulation-profiles", json=payload)
        profile_id = resp.json()["data"]["id"]
        resp = await client.delete(f"/api/v1/simulation-profiles/{profile_id}")
        assert resp.status_code == 200

        resp = await client.get(f"/api/v1/simulation-profiles/{profile_id}")
        assert resp.status_code == 404

    async def test_delete_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.delete(
            f"/api/v1/simulation-profiles/{uuid.uuid4()}"
        )
        assert resp.status_code == 404
```

- [x] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && docker run --rm -v "$(pwd)":/app -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter_test" ghostmeter-backend pytest tests/test_simulation_profiles.py -v 2>&1 | head -50
```
Expected: FAIL (404s because route doesn't exist yet)

- [x] **Step 3: Create profile service**

```python
# backend/app/services/simulation_profile_service.py
"""CRUD service for simulation profiles."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app.models.simulation import SimulationConfig
from app.models.simulation_profile import SimulationProfile
from app.models.template import DeviceTemplate
from app.schemas.simulation_profile import (
    SimulationProfileCreate,
    SimulationProfileUpdate,
)

logger = logging.getLogger(__name__)


async def _get_profile_or_404(
    session: AsyncSession, profile_id: uuid.UUID,
) -> SimulationProfile:
    """Get profile or raise 404."""
    stmt = select(SimulationProfile).where(SimulationProfile.id == profile_id)
    result = await session.execute(stmt)
    profile = result.scalar_one_or_none()
    if profile is None:
        raise NotFoundException(
            detail="Simulation profile not found",
            error_code="PROFILE_NOT_FOUND",
        )
    return profile


async def _get_template_or_404(
    session: AsyncSession, template_id: uuid.UUID,
) -> DeviceTemplate:
    """Get template or raise 404."""
    stmt = select(DeviceTemplate).where(DeviceTemplate.id == template_id)
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundException(
            detail="Template not found", error_code="TEMPLATE_NOT_FOUND"
        )
    return template


async def _clear_existing_default(
    session: AsyncSession, template_id: uuid.UUID,
) -> None:
    """Clear is_default flag on any existing default profile for this template."""
    stmt = select(SimulationProfile).where(
        SimulationProfile.template_id == template_id,
        SimulationProfile.is_default.is_(True),
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.is_default = False


async def list_profiles(
    session: AsyncSession, template_id: uuid.UUID,
) -> list[SimulationProfile]:
    """List all profiles for a template."""
    await _get_template_or_404(session, template_id)
    stmt = (
        select(SimulationProfile)
        .where(SimulationProfile.template_id == template_id)
        .order_by(SimulationProfile.name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_profile(
    session: AsyncSession, profile_id: uuid.UUID,
) -> SimulationProfile:
    """Get a single profile by ID."""
    return await _get_profile_or_404(session, profile_id)


async def create_profile(
    session: AsyncSession, data: SimulationProfileCreate,
) -> SimulationProfile:
    """Create a new simulation profile."""
    await _get_template_or_404(session, data.template_id)

    if data.is_default:
        await _clear_existing_default(session, data.template_id)

    profile = SimulationProfile(
        template_id=data.template_id,
        name=data.name,
        description=data.description,
        is_default=data.is_default,
        configs=[c.model_dump() for c in data.configs],
    )
    session.add(profile)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if "uq_simulation_profile_template_name" in str(e):
            raise ConflictException(
                detail=f"Profile name '{data.name}' already exists for this template",
                error_code="PROFILE_NAME_CONFLICT",
            ) from e
        raise ValidationException(f"Database constraint violation: {e}") from e
    await session.refresh(profile)
    return profile


async def update_profile(
    session: AsyncSession,
    profile_id: uuid.UUID,
    data: SimulationProfileUpdate,
) -> SimulationProfile:
    """Update a simulation profile."""
    profile = await _get_profile_or_404(session, profile_id)

    if profile.is_builtin and data.configs is not None:
        raise ForbiddenException(
            detail="Cannot modify configs of a built-in profile",
            error_code="BUILTIN_PROFILE_IMMUTABLE",
        )

    if data.name is not None:
        profile.name = data.name
    if data.description is not None:
        profile.description = data.description
    if data.is_default is not None:
        if data.is_default:
            await _clear_existing_default(session, profile.template_id)
        profile.is_default = data.is_default
    if data.configs is not None:
        profile.configs = [c.model_dump() for c in data.configs]

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if "uq_simulation_profile_template_name" in str(e):
            raise ConflictException(
                detail=f"Profile name '{data.name}' already exists for this template",
                error_code="PROFILE_NAME_CONFLICT",
            ) from e
        raise ValidationException(f"Database constraint violation: {e}") from e
    await session.refresh(profile)
    return profile


async def delete_profile(
    session: AsyncSession, profile_id: uuid.UUID,
) -> None:
    """Delete a simulation profile. Built-in profiles cannot be deleted."""
    profile = await _get_profile_or_404(session, profile_id)
    if profile.is_builtin:
        raise ForbiddenException(
            detail="Cannot delete a built-in profile",
            error_code="BUILTIN_PROFILE_IMMUTABLE",
        )
    await session.delete(profile)
    await session.commit()


async def apply_profile_to_device(
    session: AsyncSession,
    profile: SimulationProfile,
    device_id: uuid.UUID,
) -> None:
    """Expand profile configs into simulation_configs rows for a device."""
    for cfg in profile.configs:
        sim_config = SimulationConfig(
            device_id=device_id,
            register_name=cfg["register_name"],
            data_mode=cfg["data_mode"],
            mode_params=cfg.get("mode_params", {}),
            is_enabled=cfg.get("is_enabled", True),
            update_interval_ms=cfg.get("update_interval_ms", 1000),
        )
        session.add(sim_config)
    await session.flush()


async def get_default_profile(
    session: AsyncSession, template_id: uuid.UUID,
) -> SimulationProfile | None:
    """Get the default profile for a template, if any."""
    stmt = select(SimulationProfile).where(
        SimulationProfile.template_id == template_id,
        SimulationProfile.is_default.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
```

- [x] **Step 4: Commit service**

```bash
git add backend/app/services/simulation_profile_service.py
git commit -m "feat: add simulation profile CRUD service with apply logic"
```

---

### Task 5: API Routes

**Files:**
- Create: `backend/app/api/routes/simulation_profiles.py`
- Modify: `backend/app/main.py`

- [x] **Step 1: Create route file**

```python
# backend/app/api/routes/simulation_profiles.py
"""API routes for simulation profile CRUD."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiResponse
from app.schemas.simulation_profile import (
    SimulationProfileCreate,
    SimulationProfileResponse,
    SimulationProfileUpdate,
)
from app.services import simulation_profile_service

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[list[SimulationProfileResponse]],
)
async def list_profiles(
    template_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[SimulationProfileResponse]]:
    """List all simulation profiles for a template."""
    profiles = await simulation_profile_service.list_profiles(session, template_id)
    return ApiResponse(
        data=[SimulationProfileResponse.model_validate(p) for p in profiles]
    )


@router.get(
    "/{profile_id}",
    response_model=ApiResponse[SimulationProfileResponse],
)
async def get_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[SimulationProfileResponse]:
    """Get a single simulation profile."""
    profile = await simulation_profile_service.get_profile(session, profile_id)
    return ApiResponse(data=SimulationProfileResponse.model_validate(profile))


@router.post(
    "",
    response_model=ApiResponse[SimulationProfileResponse],
    status_code=201,
)
async def create_profile(
    data: SimulationProfileCreate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[SimulationProfileResponse]:
    """Create a new simulation profile."""
    profile = await simulation_profile_service.create_profile(session, data)
    return ApiResponse(data=SimulationProfileResponse.model_validate(profile))


@router.put(
    "/{profile_id}",
    response_model=ApiResponse[SimulationProfileResponse],
)
async def update_profile(
    profile_id: uuid.UUID,
    data: SimulationProfileUpdate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[SimulationProfileResponse]:
    """Update a simulation profile."""
    profile = await simulation_profile_service.update_profile(
        session, profile_id, data,
    )
    return ApiResponse(data=SimulationProfileResponse.model_validate(profile))


@router.delete(
    "/{profile_id}",
    response_model=ApiResponse[None],
)
async def delete_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete a simulation profile."""
    await simulation_profile_service.delete_profile(session, profile_id)
    return ApiResponse(message="Profile deleted successfully")
```

- [x] **Step 2: Register router in main.py**

In `backend/app/main.py`, add:

```python
from app.api.routes.simulation_profiles import router as profiles_router
```

And in the router registration section:

```python
api_v1_router.include_router(profiles_router, prefix="/simulation-profiles", tags=["simulation-profiles"])
```

- [x] **Step 3: Update conftest.py TRUNCATE**

In `backend/tests/conftest.py`, add `simulation_profiles` to the TRUNCATE statement:

```python
await conn.execute(text(
    "TRUNCATE device_templates, register_definitions, device_instances, "
    "simulation_configs, anomaly_schedules, simulation_profiles CASCADE"
))
```

- [x] **Step 4: Run profile CRUD tests**

Run:
```bash
cd backend && docker run --rm -v "$(pwd)":/app -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter_test" ghostmeter-backend pytest tests/test_simulation_profiles.py -v
```
Expected: All tests PASS

- [x] **Step 5: Run all existing tests to confirm no regressions**

Run:
```bash
cd backend && docker run --rm -v "$(pwd)":/app -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter_test" ghostmeter-backend pytest -v
```
Expected: All tests PASS

- [x] **Step 6: Commit**

```bash
git add backend/app/api/routes/simulation_profiles.py backend/app/main.py backend/tests/conftest.py backend/tests/test_simulation_profiles.py
git commit -m "feat: add simulation profile CRUD API routes and tests"
```

---

## Chunk 3: Device Creation Integration

### Task 6: Profile Auto-Apply in Device Service

**Files:**
- Modify: `backend/app/services/device_service.py`
- Create: `backend/tests/test_device_profile_apply.py`

- [x] **Step 1: Write failing test for auto-apply**

Create `backend/tests/test_device_profile_apply.py`:

```python
"""Tests for profile auto-apply on device creation."""

import uuid

from httpx import AsyncClient


TEMPLATE_PAYLOAD = {
    "name": "Apply Test Meter",
    "protocol": "modbus_tcp",
    "registers": [
        {
            "name": "voltage",
            "address": 0,
            "function_code": 4,
            "data_type": "float32",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "V",
            "description": "Voltage",
            "sort_order": 0,
        },
        {
            "name": "current",
            "address": 2,
            "function_code": 4,
            "data_type": "float32",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "A",
            "description": "Current",
            "sort_order": 1,
        },
    ],
}

PROFILE_CONFIGS = [
    {
        "register_name": "voltage",
        "data_mode": "random",
        "mode_params": {"base": 220, "amplitude": 3, "distribution": "gaussian"},
    },
    {
        "register_name": "current",
        "data_mode": "static",
        "mode_params": {"value": 10},
    },
]


async def _setup(client: AsyncClient) -> tuple[str, str]:
    """Create template + default profile, return (template_id, profile_id)."""
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    template_id = resp.json()["data"]["id"]

    resp = await client.post("/api/v1/simulation-profiles", json={
        "template_id": template_id,
        "name": "Default",
        "is_default": True,
        "configs": PROFILE_CONFIGS,
    })
    profile_id = resp.json()["data"]["id"]
    return template_id, profile_id


class TestAutoApplyDefaultProfile:
    async def test_device_gets_default_profile_configs(
        self, client: AsyncClient,
    ) -> None:
        """Creating a device without profile_id auto-applies default profile."""
        template_id, _ = await _setup(client)
        resp = await client.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "Auto Device",
            "slave_id": 1,
        })
        assert resp.status_code == 201
        device_id = resp.json()["data"]["id"]

        # Check simulation configs were created
        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert resp.status_code == 200
        configs = resp.json()["data"]
        assert len(configs) == 2
        names = {c["register_name"] for c in configs}
        assert names == {"voltage", "current"}

    async def test_explicit_null_skips_profile(
        self, client: AsyncClient,
    ) -> None:
        """Passing profile_id=null explicitly skips profile apply."""
        template_id, _ = await _setup(client)
        resp = await client.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "No Profile Device",
            "slave_id": 2,
            "profile_id": None,
        })
        assert resp.status_code == 201
        device_id = resp.json()["data"]["id"]

        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert resp.json()["data"] == []

    async def test_specific_profile_id_applied(
        self, client: AsyncClient,
    ) -> None:
        """Passing a specific profile_id applies that profile."""
        template_id, profile_id = await _setup(client)

        # Create a second non-default profile
        resp = await client.post("/api/v1/simulation-profiles", json={
            "template_id": template_id,
            "name": "Custom",
            "configs": [
                {
                    "register_name": "voltage",
                    "data_mode": "static",
                    "mode_params": {"value": 230},
                },
            ],
        })
        custom_id = resp.json()["data"]["id"]

        resp = await client.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "Custom Profile Device",
            "slave_id": 3,
            "profile_id": custom_id,
        })
        assert resp.status_code == 201
        device_id = resp.json()["data"]["id"]

        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        configs = resp.json()["data"]
        assert len(configs) == 1
        assert configs[0]["register_name"] == "voltage"
        assert configs[0]["data_mode"] == "static"

    async def test_nonexistent_profile_id_returns_404(
        self, client: AsyncClient,
    ) -> None:
        """Passing a nonexistent profile_id returns 404."""
        template_id, _ = await _setup(client)
        resp = await client.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "Bad Profile Device",
            "slave_id": 4,
            "profile_id": str(uuid.uuid4()),
        })
        assert resp.status_code == 404

    async def test_no_default_profile_creates_device_without_configs(
        self, client: AsyncClient,
    ) -> None:
        """If no default profile exists and profile_id absent, device has no configs."""
        resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD | {"name": "No Default Meter"})
        template_id = resp.json()["data"]["id"]

        resp = await client.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "No Default Device",
            "slave_id": 5,
        })
        assert resp.status_code == 201
        device_id = resp.json()["data"]["id"]

        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert resp.json()["data"] == []


class TestBatchCreateWithProfile:
    async def test_batch_create_applies_default(
        self, client: AsyncClient,
    ) -> None:
        template_id, _ = await _setup(client)
        resp = await client.post("/api/v1/devices/batch", json={
            "template_id": template_id,
            "slave_id_start": 10,
            "slave_id_end": 12,
        })
        assert resp.status_code == 201
        devices = resp.json()["data"]
        assert len(devices) == 3

        # Check first device has configs
        device_id = devices[0]["id"]
        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert len(resp.json()["data"]) == 2
```

- [x] **Step 2: Run tests to verify they fail**

Run:
```bash
cd backend && docker run --rm -v "$(pwd)":/app -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter_test" ghostmeter-backend pytest tests/test_device_profile_apply.py -v 2>&1 | head -40
```
Expected: FAIL (configs are empty because apply logic not implemented yet)

- [x] **Step 3: Modify device_service.py to apply profiles**

In `backend/app/services/device_service.py`, add the profile apply logic to `create_device` and `batch_create_devices`.

Add import at top:

```python
from app.services import simulation_profile_service
```

Add helper function:

```python
async def _resolve_and_apply_profile(
    session: AsyncSession,
    device_id: uuid.UUID,
    template_id: uuid.UUID,
    data: DeviceCreate | DeviceBatchCreate,
) -> None:
    """Resolve the profile to apply and expand into simulation_configs."""
    profile = None

    if "profile_id" in data.model_fields_set:
        # Explicitly provided
        if data.profile_id is not None:
            profile = await simulation_profile_service.get_profile(
                session, data.profile_id,
            )
            if profile.template_id != template_id:
                raise ValidationException(
                    "Profile does not belong to the device's template"
                )
        # else: explicit null → skip
    else:
        # Absent → auto-apply default
        profile = await simulation_profile_service.get_default_profile(
            session, template_id,
        )

    if profile is not None:
        await simulation_profile_service.apply_profile_to_device(
            session, profile, device_id,
        )
```

In `create_device`, after `await session.refresh(device)` and before `return`:

```python
    await _resolve_and_apply_profile(session, device.id, data.template_id, data)
    await session.commit()
```

In `batch_create_devices`, after the refresh loop and before `return result`:

```python
    for device in devices:
        await _resolve_and_apply_profile(session, device.id, data.template_id, data)
    await session.commit()
```

- [x] **Step 4: Run tests**

Run:
```bash
cd backend && docker run --rm -v "$(pwd)":/app -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter_test" ghostmeter-backend pytest tests/test_device_profile_apply.py -v
```
Expected: All tests PASS

- [x] **Step 5: Run all tests**

Run:
```bash
cd backend && docker run --rm -v "$(pwd)":/app -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter_test" ghostmeter-backend pytest -v
```
Expected: All tests PASS (including existing device tests that don't send profile_id — they should still work because absent = auto-apply default, and no default profile exists for test templates)

- [x] **Step 6: Commit**

```bash
git add backend/app/services/device_service.py backend/tests/test_device_profile_apply.py
git commit -m "feat: auto-apply simulation profile on device creation"
```

---

## Chunk 4: Seed Data

### Task 7: Seed Profile JSON Files

**Files:**
- Create: `backend/app/seed/profiles/three_phase_meter_normal.json`
- Create: `backend/app/seed/profiles/single_phase_meter_normal.json`
- Create: `backend/app/seed/profiles/solar_inverter_normal.json`

- [x] **Step 1: Create profiles directory**

```bash
mkdir -p backend/app/seed/profiles
```

- [x] **Step 2: Create three_phase_meter_normal.json**

```json
{
  "template_name": "SDM630 Three-Phase Meter",
  "name": "Normal Operation",
  "description": "Physically consistent three-phase meter simulation with daily load curve. Voltage ~220V gaussian, current follows daily peak at 14:00, power computed from V×I, energy accumulates from average.",
  "is_default": true,
  "configs": [
    {
      "register_name": "voltage_l1",
      "data_mode": "random",
      "mode_params": {"base": 220, "amplitude": 3, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "voltage_l2",
      "data_mode": "random",
      "mode_params": {"base": 220, "amplitude": 3, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "voltage_l3",
      "data_mode": "random",
      "mode_params": {"base": 220, "amplitude": 3, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "current_l1",
      "data_mode": "daily_curve",
      "mode_params": {"base": 15, "amplitude": 12, "peak_hour": 14},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "current_l2",
      "data_mode": "daily_curve",
      "mode_params": {"base": 15, "amplitude": 12, "peak_hour": 14},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "current_l3",
      "data_mode": "daily_curve",
      "mode_params": {"base": 15, "amplitude": 12, "peak_hour": 14},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "power_l1",
      "data_mode": "computed",
      "mode_params": {"expression": "{voltage_l1} * {current_l1}"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "power_l2",
      "data_mode": "computed",
      "mode_params": {"expression": "{voltage_l2} * {current_l2}"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "power_l3",
      "data_mode": "computed",
      "mode_params": {"expression": "{voltage_l3} * {current_l3}"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "total_power",
      "data_mode": "computed",
      "mode_params": {"expression": "{power_l1} + {power_l2} + {power_l3}"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "frequency",
      "data_mode": "random",
      "mode_params": {"base": 60, "amplitude": 0.05, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "power_factor_total",
      "data_mode": "random",
      "mode_params": {"base": 0.95, "amplitude": 0.03, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "total_energy",
      "data_mode": "accumulator",
      "mode_params": {"start_value": 1000, "increment_per_second": 0.00275},
      "update_interval_ms": 1000,
      "is_enabled": true
    }
  ]
}
```

- [x] **Step 3: Create single_phase_meter_normal.json**

```json
{
  "template_name": "SDM120 Single-Phase Meter",
  "name": "Normal Operation",
  "description": "Physically consistent single-phase meter simulation with daily load curve. Voltage ~220V, current peaks at 14:00, power and energy computed from measurements.",
  "is_default": true,
  "configs": [
    {
      "register_name": "voltage",
      "data_mode": "random",
      "mode_params": {"base": 220, "amplitude": 3, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "current",
      "data_mode": "daily_curve",
      "mode_params": {"base": 8, "amplitude": 6, "peak_hour": 14},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "power_factor",
      "data_mode": "random",
      "mode_params": {"base": 0.95, "amplitude": 0.03, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "active_power",
      "data_mode": "computed",
      "mode_params": {"expression": "{voltage} * {current} * {power_factor}"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "apparent_power",
      "data_mode": "computed",
      "mode_params": {"expression": "{voltage} * {current}"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "reactive_power",
      "data_mode": "computed",
      "mode_params": {"expression": "{apparent_power} * 0.31"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "frequency",
      "data_mode": "random",
      "mode_params": {"base": 60, "amplitude": 0.05, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "total_energy",
      "data_mode": "accumulator",
      "mode_params": {"start_value": 500, "increment_per_second": 0.00046},
      "update_interval_ms": 1000,
      "is_enabled": true
    }
  ]
}
```

- [x] **Step 4: Create solar_inverter_normal.json**

```json
{
  "template_name": "SunSpec Solar Inverter",
  "name": "Normal Operation",
  "description": "Solar inverter simulation with daily solar curve peaking at noon. DC voltage/current follow sunlight, AC power computed via efficiency, energy accumulates.",
  "is_default": true,
  "configs": [
    {
      "register_name": "dc_voltage",
      "data_mode": "daily_curve",
      "mode_params": {"base": 350, "amplitude": 100, "peak_hour": 12},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "dc_current",
      "data_mode": "daily_curve",
      "mode_params": {"base": 8, "amplitude": 7.5, "peak_hour": 12},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "dc_power",
      "data_mode": "computed",
      "mode_params": {"expression": "{dc_voltage} * {dc_current}"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "ac_voltage",
      "data_mode": "random",
      "mode_params": {"base": 220, "amplitude": 3, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "efficiency",
      "data_mode": "random",
      "mode_params": {"base": 960, "amplitude": 10, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "ac_power",
      "data_mode": "computed",
      "mode_params": {"expression": "{dc_power} * {efficiency} * 0.001"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "ac_current",
      "data_mode": "computed",
      "mode_params": {"expression": "{ac_power} / {ac_voltage}"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "ac_frequency",
      "data_mode": "random",
      "mode_params": {"base": 60, "amplitude": 0.05, "distribution": "gaussian"},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "inverter_status",
      "data_mode": "static",
      "mode_params": {"value": 3},
      "update_interval_ms": 1000,
      "is_enabled": true
    },
    {
      "register_name": "total_energy",
      "data_mode": "accumulator",
      "mode_params": {"start_value": 5000, "increment_per_second": 0.00069},
      "update_interval_ms": 1000,
      "is_enabled": true
    }
  ]
}
```

- [x] **Step 5: Commit seed files**

```bash
git add backend/app/seed/profiles/
git commit -m "feat: add built-in simulation profile seed data for all templates"
```

---

### Task 8: Seed Loader

**Files:**
- Modify: `backend/app/seed/loader.py`
- Create: `backend/tests/test_seed_profiles.py`

- [x] **Step 1: Write failing test for seed loading**

Create `backend/tests/test_seed_profiles.py`:

```python
"""Tests for simulation profile seed loading."""

from httpx import AsyncClient

from app.seed.loader import seed_builtin_profiles, seed_builtin_templates


class TestSeedProfiles:
    async def test_seed_creates_profiles(self, client: AsyncClient) -> None:
        """Seeding creates profiles for built-in templates."""
        # Seed templates first, then profiles
        await seed_builtin_templates()
        await seed_builtin_profiles()

        # List templates to get IDs
        resp = await client.get("/api/v1/templates")
        templates = resp.json()["data"]
        assert len(templates) >= 3  # 3 built-in templates

        # Each built-in template should have at least one profile
        for t in templates:
            if not t.get("is_builtin"):
                continue
            resp = await client.get(
                f"/api/v1/simulation-profiles?template_id={t['id']}"
            )
            profiles = resp.json()["data"]
            assert len(profiles) >= 1, f"No profile for template {t['name']}"
            # Default profile should exist
            defaults = [p for p in profiles if p["is_default"]]
            assert len(defaults) == 1, f"Expected 1 default for {t['name']}"
            assert defaults[0]["is_builtin"] is True

    async def test_seed_is_idempotent(self, client: AsyncClient) -> None:
        """Running seed twice doesn't create duplicates."""
        await seed_builtin_templates()
        await seed_builtin_profiles()
        await seed_builtin_profiles()  # Second run

        resp = await client.get("/api/v1/templates")
        templates = resp.json()["data"]
        for t in templates:
            if not t.get("is_builtin"):
                continue
            resp = await client.get(
                f"/api/v1/simulation-profiles?template_id={t['id']}"
            )
            profiles = resp.json()["data"]
            # Should still be exactly 1, not 2
            names = [p["name"] for p in profiles]
            assert len(names) == len(set(names)), f"Duplicate profiles for {t['name']}"

    async def test_builtin_profile_configs_cannot_be_updated(
        self, client: AsyncClient,
    ) -> None:
        """Built-in profile configs are immutable."""
        await seed_builtin_templates()
        await seed_builtin_profiles()

        # Find a builtin profile
        resp = await client.get("/api/v1/templates")
        template = next(t for t in resp.json()["data"] if t.get("is_builtin"))
        resp = await client.get(
            f"/api/v1/simulation-profiles?template_id={template['id']}"
        )
        profile = next(p for p in resp.json()["data"] if p["is_builtin"])

        # Attempt to update configs → 403
        resp = await client.put(
            f"/api/v1/simulation-profiles/{profile['id']}",
            json={"configs": [{"register_name": "voltage", "data_mode": "static", "mode_params": {"value": 0}}]},
        )
        assert resp.status_code == 403

        # But name/description update should work
        resp = await client.put(
            f"/api/v1/simulation-profiles/{profile['id']}",
            json={"name": "Renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Renamed"

    async def test_builtin_profile_cannot_be_deleted(
        self, client: AsyncClient,
    ) -> None:
        """Built-in profiles cannot be deleted."""
        await seed_builtin_templates()
        await seed_builtin_profiles()

        resp = await client.get("/api/v1/templates")
        template = next(t for t in resp.json()["data"] if t.get("is_builtin"))
        resp = await client.get(
            f"/api/v1/simulation-profiles?template_id={template['id']}"
        )
        profile = next(p for p in resp.json()["data"] if p["is_builtin"])

        resp = await client.delete(f"/api/v1/simulation-profiles/{profile['id']}")
        assert resp.status_code == 403
```

- [x] **Step 2: Run test to verify it fails**

Run:
```bash
cd backend && docker run --rm -v "$(pwd)":/app -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter_test" ghostmeter-backend pytest tests/test_seed_profiles.py -v 2>&1 | head -20
```
Expected: FAIL (`seed_builtin_profiles` doesn't exist yet)

- [x] **Step 3: Add profile seed loading to loader.py**

Add to `backend/app/seed/loader.py`:

```python
from app.models.simulation_profile import SimulationProfile


PROFILES_DIR = SEED_DIR / "profiles"


async def seed_builtin_profiles() -> None:
    """Load profile seed JSON files and create builtin profiles if they don't exist."""
    if not PROFILES_DIR.is_dir():
        logger.info("No profiles seed directory found at %s", PROFILES_DIR)
        return

    json_files = sorted(PROFILES_DIR.glob("*.json"))
    if not json_files:
        logger.info("No profile seed files found in %s", PROFILES_DIR)
        return

    async with async_session_factory() as session:
        for json_file in json_files:
            try:
                raw = json.loads(json_file.read_text(encoding="utf-8"))
                template_name = raw["template_name"]
                profile_name = raw["name"]

                # Find template by name
                stmt = select(DeviceTemplate).where(
                    DeviceTemplate.name == template_name,
                )
                result = await session.execute(stmt)
                template = result.scalar_one_or_none()
                if template is None:
                    logger.warning(
                        "Template '%s' not found for profile seed '%s', skipping",
                        template_name, json_file.name,
                    )
                    continue

                # Check if profile already exists
                stmt = select(SimulationProfile).where(
                    SimulationProfile.template_id == template.id,
                    SimulationProfile.name == profile_name,
                )
                result = await session.execute(stmt)
                if result.scalar_one_or_none() is not None:
                    logger.debug(
                        "Profile '%s' for '%s' already exists, skipping",
                        profile_name, template_name,
                    )
                    continue

                # If is_default, clear any existing default first
                if raw.get("is_default", False):
                    stmt = select(SimulationProfile).where(
                        SimulationProfile.template_id == template.id,
                        SimulationProfile.is_default.is_(True),
                    )
                    result = await session.execute(stmt)
                    existing_default = result.scalar_one_or_none()
                    if existing_default is not None:
                        existing_default.is_default = False

                profile = SimulationProfile(
                    template_id=template.id,
                    name=profile_name,
                    description=raw.get("description"),
                    is_builtin=True,
                    is_default=raw.get("is_default", False),
                    configs=raw["configs"],
                )
                session.add(profile)
                await session.commit()
                logger.info(
                    "Seeded profile '%s' for template '%s'",
                    profile_name, template_name,
                )

            except Exception:
                logger.error(
                    "Failed to load profile seed %s", json_file.name, exc_info=True,
                )
```

- [x] **Step 4: Call seed_builtin_profiles in main.py lifespan**

In `backend/app/main.py`, after `await seed_builtin_templates()`:

```python
from app.seed.loader import seed_builtin_profiles
# ...
await seed_builtin_profiles()
logger.info("Profile seed data check complete")
```

Update the import at top:

```python
from app.seed.loader import seed_builtin_templates, seed_builtin_profiles
```

- [x] **Step 5: Run seed tests**

Run:
```bash
cd backend && docker run --rm -v "$(pwd)":/app -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter_test" ghostmeter-backend pytest tests/test_seed_profiles.py -v
```
Expected: All tests PASS

- [x] **Step 6: Run all tests**

Run:
```bash
cd backend && docker run --rm -v "$(pwd)":/app -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter_test" ghostmeter-backend pytest -v
```
Expected: All tests PASS

- [x] **Step 7: Commit**

```bash
git add backend/app/seed/loader.py backend/app/main.py backend/tests/test_seed_profiles.py
git commit -m "feat: add profile seed loader and call from app startup"
```

---

## Chunk 5: Documentation Updates

### Task 9: Update Project Documentation

**Files:**
- Modify: `docs/api-reference.md`
- Modify: `docs/database-schema.md`
- Modify: `docs/development-log.md`
- Modify: `docs/development-phases.md`
- Modify: `CHANGELOG.md`

- [x] **Step 1: Update api-reference.md**

Add the new `/api/v1/simulation-profiles` endpoints section.

- [x] **Step 2: Update database-schema.md**

Add `simulation_profiles` table documentation.

- [x] **Step 3: Update development-log.md**

Add entry for simulation profiles feature.

- [x] **Step 4: Update development-phases.md**

Update current phase status.

- [x] **Step 5: Update CHANGELOG.md**

Add under `[Unreleased]`:
```markdown
### Added
- Simulation profiles: reusable sets of simulation parameters for device templates
- Built-in "Normal Operation" profiles for all three templates (three-phase meter, single-phase meter, solar inverter)
- Automatic profile apply on device creation (default profile auto-applied unless explicitly skipped)
- CRUD API for simulation profiles (`/api/v1/simulation-profiles`)
```

- [x] **Step 6: Commit**

```bash
git add docs/ CHANGELOG.md
git commit -m "docs: add simulation profiles to API reference, DB schema, and changelog"
```
