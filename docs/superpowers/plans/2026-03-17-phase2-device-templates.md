# Phase 2: Device Template Module Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add device template CRUD with register definitions, seed data, import/export, and frontend management UI.

**Architecture:** Layered backend (routes → services → models) with async SQLAlchemy 2.0. Frontend uses Zustand store + Ant Design 5. All IDs are UUID. Registers use 0-based Modbus addresses. PUT replaces registers wholesale.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 / asyncpg / Pydantic v2 / Alembic / pytest / React 18 / TypeScript / Ant Design 5 / Zustand / Axios

**Spec:** `docs/superpowers/specs/2026-03-17-phase2-device-templates-design.md`

---

## File Structure

### Backend — New Files

| File | Responsibility |
|------|---------------|
| `backend/app/models/template.py` | SQLAlchemy ORM models: DeviceTemplate, RegisterDefinition |
| `backend/app/schemas/common.py` | ApiResponse envelope (shared across modules) |
| `backend/app/schemas/template.py` | Pydantic request/response schemas for templates |
| `backend/app/services/template_service.py` | Business logic: CRUD, clone, import/export, address validation |
| `backend/app/api/routes/templates.py` | FastAPI route handlers for /api/v1/templates |
| `backend/app/seed/loader.py` | Scan seed/*.json and create builtin templates on startup |
| `backend/app/seed/three_phase_meter.json` | SDM630 register map (FC04, 0-based addresses) |
| `backend/app/seed/single_phase_meter.json` | SDM120 register map |
| `backend/app/seed/solar_inverter.json` | Fronius Symo / SunSpec register map |
| `backend/tests/test_templates.py` | API integration tests for template CRUD |
| `backend/tests/test_seed.py` | Tests for seed data loading |

### Backend — Modified Files

| File | Change |
|------|--------|
| `backend/app/main.py` | Register templates router + call seed loader in lifespan |
| `backend/app/exceptions.py` | Add ForbiddenException class |
| `backend/app/database.py` | No changes (Base already exported) |
| `backend/tests/conftest.py` | Update for test DB with table create/truncate |

### Frontend — New Files

| File | Responsibility |
|------|---------------|
| `frontend/src/types/template.ts` | TypeScript interfaces for template domain |
| `frontend/src/services/templateApi.ts` | Axios API calls for templates |
| `frontend/src/stores/templateStore.ts` | Zustand store for template state |
| `frontend/src/pages/Templates/TemplateList.tsx` | Table component for template list |
| `frontend/src/pages/Templates/TemplateForm.tsx` | Create/edit page with register table |
| `frontend/src/pages/Templates/RegisterTable.tsx` | Editable register map table |
| `frontend/src/pages/Templates/ImportExportButtons.tsx` | Import/export UI controls |

### Frontend — Modified Files

| File | Change |
|------|--------|
| `frontend/src/pages/Templates/index.tsx` | Replace placeholder with TemplateList |
| `frontend/src/App.tsx` | Add routes for /templates/new and /templates/:id |
| `frontend/src/types/index.ts` | Re-export from template.ts |

---

## Chunk 1: Backend Foundation (Models, Schemas, Exceptions, Migration)

### Task 1: Add ForbiddenException

**Files:**
- Modify: `backend/app/exceptions.py`

- [ ] **Step 1: Add ForbiddenException to exceptions.py**

Add after `ValidationException`:

```python
class ForbiddenException(AppException):
    """Action not allowed."""

    def __init__(
        self,
        detail: str = "Action not allowed",
        error_code: str = "FORBIDDEN",
    ) -> None:
        super().__init__(status_code=403, error_code=error_code, detail=detail)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/exceptions.py
git commit -m "feat: add ForbiddenException for builtin template protection"
```

---

### Task 2: Create SQLAlchemy ORM Models

**Files:**
- Create: `backend/app/models/template.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write DeviceTemplate and RegisterDefinition models**

Create `backend/app/models/template.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class DeviceTemplate(Base):
    """Device template defining a register map."""

    __tablename__ = "device_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    protocol: Mapped[str] = mapped_column(
        String(50), nullable=False, default="modbus_tcp"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    registers: Mapped[list["RegisterDefinition"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="RegisterDefinition.sort_order",
    )


class RegisterDefinition(Base):
    """Single register within a device template."""

    __tablename__ = "register_definitions"
    __table_args__ = (
        UniqueConstraint("template_id", "name", name="uq_register_template_name"),
        UniqueConstraint(
            "template_id", "address", "function_code",
            name="uq_register_template_addr_fc",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_templates.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[int] = mapped_column(Integer, nullable=False)
    function_code: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=3
    )
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    byte_order: Mapped[str] = mapped_column(
        String(30), nullable=False, default="big_endian"
    )
    scale_factor: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    template: Mapped["DeviceTemplate"] = relationship(
        back_populates="registers"
    )
```

- [ ] **Step 2: Export models from `__init__.py`**

Replace `backend/app/models/__init__.py`:

```python
from app.models.template import DeviceTemplate, RegisterDefinition

__all__ = ["DeviceTemplate", "RegisterDefinition"]
```

- [ ] **Step 3: Verify import works**

Run: `cd backend && python -c "from app.models import DeviceTemplate, RegisterDefinition; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/template.py backend/app/models/__init__.py
git commit -m "feat: add DeviceTemplate and RegisterDefinition ORM models"
```

---

### Task 3: Create Alembic Migration

**Files:**
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/xxxx_add_templates_and_registers.py` (auto-generated)

- [ ] **Step 1: Import models in alembic env.py so autogenerate sees them**

Add to `backend/alembic/env.py` after `from app.database import Base`:

```python
import app.models  # noqa: F401 — ensure models are registered with Base.metadata
```

- [ ] **Step 2: Generate migration**

Run: `cd backend && alembic revision --autogenerate -m "add device_templates and register_definitions"`
Expected: New file in `alembic/versions/` with `create_table` operations for both tables.

- [ ] **Step 3: Review generated migration**

Verify it contains:
- `op.create_table('device_templates', ...)` with all columns
- `op.create_table('register_definitions', ...)` with FK, unique constraints
- Correct `downgrade()` with `op.drop_table` in reverse order

- [ ] **Step 4: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: Tables created successfully.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/env.py backend/alembic/versions/
git commit -m "feat: add migration for device_templates and register_definitions"
```

---

### Task 4: Create Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/common.py`
- Create: `backend/app/schemas/template.py`
- Modify: `backend/app/schemas/__init__.py`

- [ ] **Step 1: Write ApiResponse envelope in common.py**

Create `backend/app/schemas/common.py`:

```python
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Unified API response envelope."""

    data: T | None = None
    message: str | None = None
    success: bool = True
```

- [ ] **Step 2: Write template schemas**

Create `backend/app/schemas/template.py`:

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


# --- Data type → register count mapping ---

DATA_TYPE_REGISTER_COUNT: dict[str, int] = {
    "int16": 1,
    "uint16": 1,
    "int32": 2,
    "uint32": 2,
    "float32": 2,
    "float64": 4,
}

VALID_DATA_TYPES = set(DATA_TYPE_REGISTER_COUNT.keys())

VALID_BYTE_ORDERS = {
    "big_endian",
    "little_endian",
    "big_endian_word_swap",
    "little_endian_word_swap",
}

VALID_FUNCTION_CODES = {3, 4}


# --- Request Schemas ---

class RegisterDefinitionCreate(BaseModel):
    """Schema for creating a register definition."""

    name: str
    address: int
    function_code: int = 3
    data_type: str
    byte_order: str = "big_endian"
    scale_factor: float = 1.0
    unit: str | None = None
    description: str | None = None
    sort_order: int = 0

    @field_validator("data_type")
    @classmethod
    def validate_data_type(cls, v: str) -> str:
        if v not in VALID_DATA_TYPES:
            raise ValueError(
                f"Invalid data_type '{v}'. Must be one of: {sorted(VALID_DATA_TYPES)}"
            )
        return v

    @field_validator("byte_order")
    @classmethod
    def validate_byte_order(cls, v: str) -> str:
        if v not in VALID_BYTE_ORDERS:
            raise ValueError(
                f"Invalid byte_order '{v}'. Must be one of: {sorted(VALID_BYTE_ORDERS)}"
            )
        return v

    @field_validator("function_code")
    @classmethod
    def validate_function_code(cls, v: int) -> int:
        if v not in VALID_FUNCTION_CODES:
            raise ValueError(
                f"Invalid function_code {v}. Must be one of: {sorted(VALID_FUNCTION_CODES)}"
            )
        return v

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Address must be >= 0")
        return v


class TemplateCreate(BaseModel):
    """Schema for creating a device template."""

    name: str
    protocol: str = "modbus_tcp"
    description: str | None = None
    registers: list[RegisterDefinitionCreate]

    @field_validator("registers")
    @classmethod
    def validate_registers_not_empty(
        cls, v: list[RegisterDefinitionCreate],
    ) -> list[RegisterDefinitionCreate]:
        if not v:
            raise ValueError("Template must have at least one register")
        return v


class TemplateUpdate(BaseModel):
    """Schema for updating a device template (full replacement)."""

    name: str
    protocol: str = "modbus_tcp"
    description: str | None = None
    registers: list[RegisterDefinitionCreate]

    @field_validator("registers")
    @classmethod
    def validate_registers_not_empty(
        cls, v: list[RegisterDefinitionCreate],
    ) -> list[RegisterDefinitionCreate]:
        if not v:
            raise ValueError("Template must have at least one register")
        return v


class TemplateClone(BaseModel):
    """Schema for cloning a template."""

    new_name: str | None = None


# --- Response Schemas ---

class RegisterDefinitionResponse(BaseModel):
    """Schema for register definition in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    address: int
    function_code: int
    data_type: str
    byte_order: str
    scale_factor: float
    unit: str | None
    description: str | None
    sort_order: int


class TemplateSummary(BaseModel):
    """Schema for template list items (without full registers)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    protocol: str
    description: str | None
    is_builtin: bool
    register_count: int
    created_at: datetime
    updated_at: datetime


class TemplateDetail(BaseModel):
    """Schema for full template detail (with registers)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    protocol: str
    description: str | None
    is_builtin: bool
    registers: list[RegisterDefinitionResponse]
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 3: Export from `__init__.py`**

Replace `backend/app/schemas/__init__.py`:

```python
from app.schemas.common import ApiResponse
from app.schemas.template import (
    TemplateClone,
    TemplateCreate,
    TemplateDetail,
    TemplateSummary,
    TemplateUpdate,
)

__all__ = [
    "ApiResponse",
    "TemplateClone",
    "TemplateCreate",
    "TemplateDetail",
    "TemplateSummary",
    "TemplateUpdate",
]
```

- [ ] **Step 4: Verify import works**

Run: `cd backend && python -c "from app.schemas import TemplateCreate, ApiResponse; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/common.py backend/app/schemas/template.py backend/app/schemas/__init__.py
git commit -m "feat: add Pydantic schemas for template CRUD and ApiResponse envelope"
```

---

## Chunk 2: Backend Service Layer & Tests

### Task 5: Write Service Layer Tests First (TDD Red)

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_templates.py`

- [ ] **Step 1: Update conftest.py for test database**

Replace `backend/tests/conftest.py`:

```python
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.database import Base, get_session
from app.main import app

settings = get_settings()

test_engine = create_async_engine(
    settings.database_url_computed,
    echo=False,
    pool_pre_ping=True,
)

test_session_factory = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
    """Override session dependency for tests."""
    async with test_session_factory() as session:
        yield session


app.dependency_overrides[get_session] = override_get_session


@pytest.fixture(autouse=True)
async def setup_database():
    """Create tables before each test and truncate after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE device_templates, register_definitions CASCADE"
        ))


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for testing FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

Note: `asyncio_mode = "auto"` is already set in `backend/pyproject.toml`.

- [ ] **Step 2: Write test_templates.py (RED — tests will fail)**

Create `backend/tests/test_templates.py`:

```python
import json

from httpx import AsyncClient

TEMPLATE_PAYLOAD = {
    "name": "Test Meter",
    "protocol": "modbus_tcp",
    "description": "A test template",
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


async def create_template(client: AsyncClient, payload: dict | None = None) -> dict:
    """Helper to create a template and return the response data."""
    response = await client.post(
        "/api/v1/templates", json=payload or TEMPLATE_PAYLOAD
    )
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    return body["data"]


class TestCreateTemplate:
    async def test_create_template_success(self, client: AsyncClient) -> None:
        data = await create_template(client)
        assert data["name"] == "Test Meter"
        assert len(data["registers"]) == 2
        assert data["is_builtin"] is False

    async def test_create_template_validates_empty_registers(
        self, client: AsyncClient,
    ) -> None:
        payload = {**TEMPLATE_PAYLOAD, "registers": []}
        response = await client.post("/api/v1/templates", json=payload)
        assert response.status_code == 422

    async def test_create_template_validates_invalid_data_type(
        self, client: AsyncClient,
    ) -> None:
        payload = {
            **TEMPLATE_PAYLOAD,
            "registers": [{**TEMPLATE_PAYLOAD["registers"][0], "data_type": "invalid"}],
        }
        response = await client.post("/api/v1/templates", json=payload)
        assert response.status_code == 422

    async def test_create_template_validates_address_overlap(
        self, client: AsyncClient,
    ) -> None:
        payload = {
            **TEMPLATE_PAYLOAD,
            "registers": [
                {**TEMPLATE_PAYLOAD["registers"][0], "address": 0},
                {**TEMPLATE_PAYLOAD["registers"][1], "name": "overlap", "address": 1},
            ],
        }
        response = await client.post("/api/v1/templates", json=payload)
        assert response.status_code == 422
        assert "overlap" in response.json()["detail"].lower()

    async def test_create_template_duplicate_name(
        self, client: AsyncClient,
    ) -> None:
        await create_template(client)
        response = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
        assert response.status_code == 422
        assert "already exists" in response.json()["detail"]


class TestListTemplates:
    async def test_list_templates_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/templates")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == []

    async def test_list_templates_with_data(self, client: AsyncClient) -> None:
        await create_template(client)
        response = await client.get("/api/v1/templates")
        body = response.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["register_count"] == 2


class TestGetTemplate:
    async def test_get_template_success(self, client: AsyncClient) -> None:
        created = await create_template(client)
        response = await client.get(f"/api/v1/templates/{created['id']}")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["name"] == "Test Meter"
        assert len(body["data"]["registers"]) == 2

    async def test_get_template_not_found(self, client: AsyncClient) -> None:
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/v1/templates/{fake_id}")
        assert response.status_code == 404
        assert response.json()["error_code"] == "TEMPLATE_NOT_FOUND"


class TestUpdateTemplate:
    async def test_update_template_success(self, client: AsyncClient) -> None:
        created = await create_template(client)
        update_payload = {
            **TEMPLATE_PAYLOAD,
            "name": "Updated Meter",
            "registers": [TEMPLATE_PAYLOAD["registers"][0]],
        }
        response = await client.put(
            f"/api/v1/templates/{created['id']}", json=update_payload
        )
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["name"] == "Updated Meter"
        assert len(body["data"]["registers"]) == 1


class TestDeleteTemplate:
    async def test_delete_template_success(self, client: AsyncClient) -> None:
        created = await create_template(client)
        response = await client.delete(f"/api/v1/templates/{created['id']}")
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify deleted
        response = await client.get(f"/api/v1/templates/{created['id']}")
        assert response.status_code == 404

    async def test_delete_template_not_found(self, client: AsyncClient) -> None:
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.delete(f"/api/v1/templates/{fake_id}")
        assert response.status_code == 404


class TestCloneTemplate:
    async def test_clone_template_default_name(self, client: AsyncClient) -> None:
        created = await create_template(client)
        response = await client.post(f"/api/v1/templates/{created['id']}/clone")
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["name"] == "Copy of Test Meter"
        assert body["data"]["is_builtin"] is False
        assert len(body["data"]["registers"]) == 2

    async def test_clone_template_custom_name(self, client: AsyncClient) -> None:
        created = await create_template(client)
        response = await client.post(
            f"/api/v1/templates/{created['id']}/clone",
            json={"new_name": "My Clone"},
        )
        assert response.status_code == 201
        assert response.json()["data"]["name"] == "My Clone"


class TestExportImport:
    async def test_export_template(self, client: AsyncClient) -> None:
        created = await create_template(client)
        response = await client.get(f"/api/v1/templates/{created['id']}/export")
        assert response.status_code == 200
        assert "attachment" in response.headers.get("content-disposition", "")
        export_data = response.json()
        assert "id" not in export_data
        assert export_data["name"] == "Test Meter"
        assert len(export_data["registers"]) == 2
        for reg in export_data["registers"]:
            assert "id" not in reg

    async def test_import_template(self, client: AsyncClient) -> None:
        import_data = {
            "name": "Imported Meter",
            "protocol": "modbus_tcp",
            "registers": [TEMPLATE_PAYLOAD["registers"][0]],
        }
        response = await client.post(
            "/api/v1/templates/import",
            files={"file": ("template.json", json.dumps(import_data), "application/json")},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["name"] == "Imported Meter"

    async def test_import_template_name_conflict(self, client: AsyncClient) -> None:
        await create_template(client)
        import_data = {**TEMPLATE_PAYLOAD}
        response = await client.post(
            "/api/v1/templates/import",
            files={"file": ("template.json", json.dumps(import_data), "application/json")},
        )
        assert response.status_code == 422
        assert "already exists" in response.json()["detail"]
```

- [ ] **Step 3: Commit tests (RED)**

```bash
git add backend/tests/conftest.py backend/tests/test_templates.py
git commit -m "test: add template CRUD API tests (RED — implementation pending)"
```

---

### Task 6: Implement Template Service (TDD Green)

**Files:**
- Create: `backend/app/services/template_service.py`
- Modify: `backend/app/services/__init__.py`

- [ ] **Step 1: Write template_service.py**

Create `backend/app/services/template_service.py`:

```python
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.models.template import DeviceTemplate, RegisterDefinition
from app.schemas.template import (
    DATA_TYPE_REGISTER_COUNT,
    RegisterDefinitionCreate,
    TemplateClone,
    TemplateCreate,
    TemplateUpdate,
)

logger = logging.getLogger(__name__)


def _validate_no_address_overlap(
    registers: list[RegisterDefinitionCreate],
) -> None:
    """Validate that register address ranges do not overlap within the same function_code.

    Each register occupies [address, address + register_count - 1] inclusive.
    Raises ValidationException if any two registers overlap.
    """
    by_fc: dict[int, list[tuple[str, int, int]]] = {}
    for reg in registers:
        count = DATA_TYPE_REGISTER_COUNT[reg.data_type]
        start = reg.address
        end = reg.address + count - 1
        by_fc.setdefault(reg.function_code, []).append((reg.name, start, end))

    for fc, ranges in by_fc.items():
        sorted_ranges = sorted(ranges, key=lambda r: r[1])
        for i in range(len(sorted_ranges) - 1):
            name_a, _, end_a = sorted_ranges[i]
            name_b, start_b, _ = sorted_ranges[i + 1]
            if end_a >= start_b:
                raise ValidationException(
                    f"Register address overlap: '{name_a}' and '{name_b}' "
                    f"overlap in FC{fc}"
                )


def _build_registers(
    data_registers: list[RegisterDefinitionCreate],
) -> list[RegisterDefinition]:
    """Build RegisterDefinition ORM objects from schema data."""
    return [
        RegisterDefinition(
            name=reg.name,
            address=reg.address,
            function_code=reg.function_code,
            data_type=reg.data_type,
            byte_order=reg.byte_order,
            scale_factor=reg.scale_factor,
            unit=reg.unit,
            description=reg.description,
            sort_order=reg.sort_order,
        )
        for reg in data_registers
    ]


async def list_templates(session: AsyncSession) -> list[dict]:
    """List all templates with register count."""
    stmt = (
        select(
            DeviceTemplate,
            func.count(RegisterDefinition.id).label("register_count"),
        )
        .outerjoin(RegisterDefinition)
        .group_by(DeviceTemplate.id)
        .order_by(DeviceTemplate.created_at)
    )
    result = await session.execute(stmt)
    rows = result.all()
    return [
        {
            "id": row.DeviceTemplate.id,
            "name": row.DeviceTemplate.name,
            "protocol": row.DeviceTemplate.protocol,
            "description": row.DeviceTemplate.description,
            "is_builtin": row.DeviceTemplate.is_builtin,
            "register_count": row.register_count,
            "created_at": row.DeviceTemplate.created_at,
            "updated_at": row.DeviceTemplate.updated_at,
        }
        for row in rows
    ]


async def get_template(session: AsyncSession, template_id: uuid.UUID) -> DeviceTemplate:
    """Get a single template with all registers."""
    stmt = (
        select(DeviceTemplate)
        .options(selectinload(DeviceTemplate.registers))
        .where(DeviceTemplate.id == template_id)
    )
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundException(detail="Template not found")
    return template


async def create_template(
    session: AsyncSession,
    data: TemplateCreate,
    is_builtin: bool = False,
) -> DeviceTemplate:
    """Create a new template with registers."""
    _validate_no_address_overlap(data.registers)

    # Check for duplicate name before hitting DB constraint
    existing = await session.execute(
        select(DeviceTemplate).where(DeviceTemplate.name == data.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise ValidationException(
            f"Template with name '{data.name}' already exists"
        )

    template = DeviceTemplate(
        name=data.name,
        protocol=data.protocol,
        description=data.description,
        is_builtin=is_builtin,
    )
    template.registers = _build_registers(data.registers)

    session.add(template)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValidationException(f"Database constraint violation: {e}") from e
    await session.refresh(template)

    return await get_template(session, template.id)


async def update_template(
    session: AsyncSession,
    template_id: uuid.UUID,
    data: TemplateUpdate,
) -> DeviceTemplate:
    """Update a template, replacing all registers."""
    template = await get_template(session, template_id)

    if template.is_builtin:
        raise ForbiddenException(
            detail="Built-in templates cannot be modified",
            error_code="BUILTIN_TEMPLATE_IMMUTABLE",
        )

    _validate_no_address_overlap(data.registers)

    template.name = data.name
    template.protocol = data.protocol
    template.description = data.description

    # Replace registers wholesale
    template.registers.clear()
    template.registers = _build_registers(data.registers)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValidationException(f"Database constraint violation: {e}") from e

    return await get_template(session, template.id)


async def delete_template(
    session: AsyncSession,
    template_id: uuid.UUID,
) -> None:
    """Delete a template and its registers."""
    template = await get_template(session, template_id)

    if template.is_builtin:
        raise ForbiddenException(
            detail="Built-in templates cannot be deleted",
            error_code="BUILTIN_TEMPLATE_IMMUTABLE",
        )

    await session.delete(template)
    await session.commit()


async def clone_template(
    session: AsyncSession,
    template_id: uuid.UUID,
    data: TemplateClone,
) -> DeviceTemplate:
    """Clone a template with a new name."""
    source = await get_template(session, template_id)

    new_name = data.new_name or f"Copy of {source.name}"

    clone_data = TemplateCreate(
        name=new_name,
        protocol=source.protocol,
        description=source.description,
        registers=[
            RegisterDefinitionCreate(
                name=reg.name,
                address=reg.address,
                function_code=reg.function_code,
                data_type=reg.data_type,
                byte_order=reg.byte_order,
                scale_factor=reg.scale_factor,
                unit=reg.unit,
                description=reg.description,
                sort_order=reg.sort_order,
            )
            for reg in source.registers
        ],
    )
    return await create_template(session, clone_data, is_builtin=False)


async def export_template(
    session: AsyncSession,
    template_id: uuid.UUID,
) -> dict:
    """Export a template as a JSON-serializable dict (no id fields)."""
    template = await get_template(session, template_id)
    return {
        "name": template.name,
        "protocol": template.protocol,
        "description": template.description,
        "registers": [
            {
                "name": reg.name,
                "address": reg.address,
                "function_code": reg.function_code,
                "data_type": reg.data_type,
                "byte_order": reg.byte_order,
                "scale_factor": reg.scale_factor,
                "unit": reg.unit,
                "description": reg.description,
                "sort_order": reg.sort_order,
            }
            for reg in template.registers
        ],
    }


async def import_template(
    session: AsyncSession,
    data: TemplateCreate,
) -> DeviceTemplate:
    """Import a template from JSON data. Name conflicts raise 422."""
    return await create_template(session, data, is_builtin=False)
```

- [ ] **Step 2: Update NotFoundException to use TEMPLATE_NOT_FOUND**

In `backend/app/exceptions.py`, the generic `NotFoundException` uses `error_code="NOT_FOUND"`. The service passes `detail="Template not found"` but we need `error_code="TEMPLATE_NOT_FOUND"` per spec.

Update `NotFoundException` to accept `error_code`:

```python
class NotFoundException(AppException):
    """Resource not found."""

    def __init__(
        self,
        detail: str = "Resource not found",
        error_code: str = "NOT_FOUND",
    ) -> None:
        super().__init__(status_code=404, error_code=error_code, detail=detail)
```

Then in `template_service.py`, the `get_template` call becomes:

```python
raise NotFoundException(detail="Template not found", error_code="TEMPLATE_NOT_FOUND")
```

- [ ] **Step 3: Export from `__init__.py`**

Replace `backend/app/services/__init__.py`:

```python
from app.services import template_service

__all__ = ["template_service"]
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/template_service.py backend/app/services/__init__.py backend/app/exceptions.py
git commit -m "feat: add template service with CRUD, clone, import/export, address validation"
```

---

### Task 7: Create Template API Routes (TDD Green continued)

**Files:**
- Create: `backend/app/api/routes/templates.py`

- [ ] **Step 1: Write route handlers**

Create `backend/app/api/routes/templates.py`:

IMPORTANT: `/import` route must be declared **before** any `/{template_id}` routes to avoid FastAPI matching "import" as a UUID path parameter.

```python
import json
import uuid

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiResponse
from app.schemas.template import (
    TemplateClone,
    TemplateCreate,
    TemplateDetail,
    TemplateSummary,
    TemplateUpdate,
)
from app.services import template_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[TemplateSummary]])
async def list_templates(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[TemplateSummary]]:
    """List all device templates."""
    templates = await template_service.list_templates(session)
    summaries = [TemplateSummary(**t) for t in templates]
    return ApiResponse(data=summaries)


@router.post("", response_model=ApiResponse[TemplateDetail], status_code=201)
async def create_template(
    data: TemplateCreate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TemplateDetail]:
    """Create a new device template."""
    template = await template_service.create_template(session, data)
    return ApiResponse(data=TemplateDetail.model_validate(template))


# --- /import MUST come before /{template_id} routes ---

@router.post("/import", response_model=ApiResponse[TemplateDetail], status_code=201)
async def import_template(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TemplateDetail]:
    """Import a template from a JSON file."""
    content = await file.read()
    raw = json.loads(content)
    data = TemplateCreate(**raw)
    template = await template_service.import_template(session, data)
    return ApiResponse(data=TemplateDetail.model_validate(template))


# --- /{template_id} routes ---

@router.get("/{template_id}", response_model=ApiResponse[TemplateDetail])
async def get_template(
    template_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TemplateDetail]:
    """Get a single template with all register definitions."""
    template = await template_service.get_template(session, template_id)
    return ApiResponse(data=TemplateDetail.model_validate(template))


@router.put("/{template_id}", response_model=ApiResponse[TemplateDetail])
async def update_template(
    template_id: uuid.UUID,
    data: TemplateUpdate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TemplateDetail]:
    """Update a device template (full replacement including registers)."""
    template = await template_service.update_template(session, template_id, data)
    return ApiResponse(data=TemplateDetail.model_validate(template))


@router.delete("/{template_id}", response_model=ApiResponse[None])
async def delete_template(
    template_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete a device template."""
    await template_service.delete_template(session, template_id)
    return ApiResponse(message="Template deleted successfully")


@router.post(
    "/{template_id}/clone",
    response_model=ApiResponse[TemplateDetail],
    status_code=201,
)
async def clone_template(
    template_id: uuid.UUID,
    data: TemplateClone = TemplateClone(),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TemplateDetail]:
    """Clone a device template."""
    template = await template_service.clone_template(session, template_id, data)
    return ApiResponse(data=TemplateDetail.model_validate(template))


@router.get("/{template_id}/export")
async def export_template(
    template_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export a template as a JSON file download."""
    export_data = await template_service.export_template(session, template_id)
    content = json.dumps(export_data, indent=2, ensure_ascii=False)
    filename = f"{export_data['name'].replace(' ', '_').lower()}.json"
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/routes/templates.py
git commit -m "feat: add template API route handlers"
```

---

### Task 8: Wire Up Routes in main.py & Run Tests (TDD Green)

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Register template router**

In `backend/app/main.py`, add import:

```python
from app.api.routes.templates import router as templates_router
```

Replace the comment `# Future route routers will be included here:` and the commented line with:

```python
api_v1_router.include_router(templates_router, prefix="/templates", tags=["templates"])
```

Do NOT add seed loader yet (that's Task 10).

- [ ] **Step 2: Run tests to verify GREEN**

Run: `cd backend && pytest tests/test_templates.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Run full test suite**

Run: `cd backend && pytest -v`
Expected: All tests PASS (including existing health tests).

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: register template routes in main app — tests green"
```

---

## Chunk 3: Seed Data & Seed Tests

### Task 9: Create Seed JSON Files

**Files:**
- Create: `backend/app/seed/three_phase_meter.json`
- Create: `backend/app/seed/single_phase_meter.json`
- Create: `backend/app/seed/solar_inverter.json`

- [ ] **Step 1: Create three_phase_meter.json (SDM630 reference)**

Create `backend/app/seed/three_phase_meter.json`:

```json
{
  "name": "SDM630 Three-Phase Meter",
  "protocol": "modbus_tcp",
  "description": "Three-phase power meter based on Eastron SDM630 register map. Registers use Input Register (FC04) with 0-based addressing.",
  "registers": [
    {"name": "voltage_l1", "address": 0, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "V", "description": "Phase L1 line-to-neutral voltage", "sort_order": 0},
    {"name": "voltage_l2", "address": 2, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "V", "description": "Phase L2 line-to-neutral voltage", "sort_order": 1},
    {"name": "voltage_l3", "address": 4, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "V", "description": "Phase L3 line-to-neutral voltage", "sort_order": 2},
    {"name": "current_l1", "address": 6, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "A", "description": "Phase L1 current", "sort_order": 3},
    {"name": "current_l2", "address": 8, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "A", "description": "Phase L2 current", "sort_order": 4},
    {"name": "current_l3", "address": 10, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "A", "description": "Phase L3 current", "sort_order": 5},
    {"name": "power_l1", "address": 12, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "W", "description": "Phase L1 active power", "sort_order": 6},
    {"name": "power_l2", "address": 14, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "W", "description": "Phase L2 active power", "sort_order": 7},
    {"name": "power_l3", "address": 16, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "W", "description": "Phase L3 active power", "sort_order": 8},
    {"name": "total_power", "address": 52, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "W", "description": "Total system active power", "sort_order": 9},
    {"name": "frequency", "address": 70, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "Hz", "description": "Line frequency", "sort_order": 10},
    {"name": "total_energy", "address": 342, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "kWh", "description": "Total active energy imported", "sort_order": 11},
    {"name": "power_factor_total", "address": 62, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "", "description": "Total system power factor", "sort_order": 12}
  ]
}
```

- [ ] **Step 2: Create single_phase_meter.json (SDM120 reference)**

Create `backend/app/seed/single_phase_meter.json`:

```json
{
  "name": "SDM120 Single-Phase Meter",
  "protocol": "modbus_tcp",
  "description": "Single-phase power meter based on Eastron SDM120 register map. Registers use Input Register (FC04) with 0-based addressing.",
  "registers": [
    {"name": "voltage", "address": 0, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "V", "description": "Line-to-neutral voltage", "sort_order": 0},
    {"name": "current", "address": 6, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "A", "description": "Current", "sort_order": 1},
    {"name": "active_power", "address": 12, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "W", "description": "Active power", "sort_order": 2},
    {"name": "apparent_power", "address": 18, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "VA", "description": "Apparent power", "sort_order": 3},
    {"name": "reactive_power", "address": 24, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "VAr", "description": "Reactive power", "sort_order": 4},
    {"name": "power_factor", "address": 30, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "", "description": "Power factor", "sort_order": 5},
    {"name": "frequency", "address": 70, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "Hz", "description": "Line frequency", "sort_order": 6},
    {"name": "total_energy", "address": 342, "function_code": 4, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "kWh", "description": "Total active energy", "sort_order": 7}
  ]
}
```

- [ ] **Step 3: Create solar_inverter.json (SunSpec reference)**

Create `backend/app/seed/solar_inverter.json`:

```json
{
  "name": "SunSpec Solar Inverter",
  "protocol": "modbus_tcp",
  "description": "Solar inverter based on SunSpec/Fronius Symo register map. Uses Holding Registers (FC03) with 0-based addressing.",
  "registers": [
    {"name": "dc_voltage", "address": 0, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "V", "description": "DC input voltage", "sort_order": 0},
    {"name": "dc_current", "address": 2, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "A", "description": "DC input current", "sort_order": 1},
    {"name": "dc_power", "address": 4, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "W", "description": "DC input power", "sort_order": 2},
    {"name": "ac_voltage", "address": 6, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "V", "description": "AC output voltage", "sort_order": 3},
    {"name": "ac_current", "address": 8, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "A", "description": "AC output current", "sort_order": 4},
    {"name": "ac_power", "address": 10, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "W", "description": "AC output power", "sort_order": 5},
    {"name": "ac_frequency", "address": 12, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "Hz", "description": "AC output frequency", "sort_order": 6},
    {"name": "total_energy", "address": 14, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "kWh", "description": "Total energy generated", "sort_order": 7},
    {"name": "inverter_status", "address": 16, "function_code": 3, "data_type": "uint16", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "", "description": "Inverter operating status (0=Off, 1=Sleeping, 2=Starting, 3=Running, 4=Throttled, 5=Fault)", "sort_order": 8},
    {"name": "efficiency", "address": 17, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 0.1, "unit": "%", "description": "Conversion efficiency", "sort_order": 9}
  ]
}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/seed/three_phase_meter.json backend/app/seed/single_phase_meter.json backend/app/seed/solar_inverter.json
git commit -m "feat: add seed data JSON files for builtin device templates"
```

---

### Task 10: Create Seed Loader & Wire Into main.py

**Files:**
- Create: `backend/app/seed/loader.py`
- Modify: `backend/app/main.py`

Note: `backend/app/seed/__init__.py` already exists from Phase 1.

- [ ] **Step 1: Write seed loader**

Create `backend/app/seed/loader.py`:

```python
import json
import logging
from pathlib import Path

from sqlalchemy import select

from app.database import async_session_factory
from app.models.template import DeviceTemplate
from app.schemas.template import TemplateCreate
from app.services import template_service

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).parent


async def seed_builtin_templates() -> None:
    """Load all seed JSON files and create builtin templates if they don't exist."""
    json_files = sorted(SEED_DIR.glob("*.json"))
    if not json_files:
        logger.info("No seed files found in %s", SEED_DIR)
        return

    async with async_session_factory() as session:
        for json_file in json_files:
            try:
                raw = json.loads(json_file.read_text(encoding="utf-8"))
                template_name = raw["name"]

                # Check if already exists
                stmt = select(DeviceTemplate).where(
                    DeviceTemplate.name == template_name,
                    DeviceTemplate.is_builtin.is_(True),
                )
                result = await session.execute(stmt)
                if result.scalar_one_or_none() is not None:
                    logger.debug(
                        "Builtin template '%s' already exists, skipping",
                        template_name,
                    )
                    continue

                data = TemplateCreate(**raw)
                await template_service.create_template(
                    session, data, is_builtin=True
                )
                logger.info("Seeded builtin template: %s", template_name)

            except Exception:
                logger.error(
                    "Failed to load seed file %s", json_file.name, exc_info=True
                )
```

- [ ] **Step 2: Add seed loader call to main.py lifespan**

In `backend/app/main.py`, add import:

```python
from app.seed.loader import seed_builtin_templates
```

In the `lifespan` function, after `logger.info("Database connection verified")`, add:

```python
        # Seed built-in templates
        await seed_builtin_templates()
        logger.info("Seed data check complete")
```

- [ ] **Step 3: Verify import works**

Run: `cd backend && python -c "from app.seed.loader import seed_builtin_templates; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/seed/loader.py backend/app/main.py
git commit -m "feat: add seed data loader and wire into app startup"
```

---

### Task 11: Write Seed Data Tests

**Files:**
- Create: `backend/tests/test_seed.py`

- [ ] **Step 1: Write seed tests**

Create `backend/tests/test_seed.py`:

```python
from httpx import AsyncClient

from app.seed.loader import seed_builtin_templates


class TestSeedLoader:
    async def test_seed_creates_builtin_templates(self, client: AsyncClient) -> None:
        await seed_builtin_templates()

        response = await client.get("/api/v1/templates")
        body = response.json()
        templates = body["data"]

        builtin = [t for t in templates if t["is_builtin"]]
        assert len(builtin) == 3

        names = {t["name"] for t in builtin}
        assert "SDM630 Three-Phase Meter" in names
        assert "SDM120 Single-Phase Meter" in names
        assert "SunSpec Solar Inverter" in names

    async def test_seed_is_idempotent(self, client: AsyncClient) -> None:
        await seed_builtin_templates()
        await seed_builtin_templates()

        response = await client.get("/api/v1/templates")
        templates = response.json()["data"]
        builtin = [t for t in templates if t["is_builtin"]]
        assert len(builtin) == 3

    async def test_builtin_template_cannot_be_deleted(
        self, client: AsyncClient,
    ) -> None:
        await seed_builtin_templates()

        response = await client.get("/api/v1/templates")
        builtin = [t for t in response.json()["data"] if t["is_builtin"]][0]

        response = await client.delete(f"/api/v1/templates/{builtin['id']}")
        assert response.status_code == 403
        assert response.json()["error_code"] == "BUILTIN_TEMPLATE_IMMUTABLE"

    async def test_builtin_template_cannot_be_updated(
        self, client: AsyncClient,
    ) -> None:
        await seed_builtin_templates()

        response = await client.get("/api/v1/templates")
        builtin = [t for t in response.json()["data"] if t["is_builtin"]][0]

        detail_response = await client.get(f"/api/v1/templates/{builtin['id']}")
        detail = detail_response.json()["data"]

        update_payload = {
            "name": "Hacked Name",
            "protocol": detail["protocol"],
            "registers": [
                {
                    "name": r["name"],
                    "address": r["address"],
                    "function_code": r["function_code"],
                    "data_type": r["data_type"],
                    "byte_order": r["byte_order"],
                    "scale_factor": r["scale_factor"],
                    "unit": r["unit"],
                    "description": r["description"],
                    "sort_order": r["sort_order"],
                }
                for r in detail["registers"]
            ],
        }
        response = await client.put(
            f"/api/v1/templates/{builtin['id']}", json=update_payload
        )
        assert response.status_code == 403
        assert response.json()["error_code"] == "BUILTIN_TEMPLATE_IMMUTABLE"

    async def test_builtin_template_can_be_cloned(
        self, client: AsyncClient,
    ) -> None:
        await seed_builtin_templates()

        response = await client.get("/api/v1/templates")
        builtin = [t for t in response.json()["data"] if t["is_builtin"]][0]

        response = await client.post(
            f"/api/v1/templates/{builtin['id']}/clone",
            json={"new_name": "My Custom Meter"},
        )
        assert response.status_code == 201
        clone = response.json()["data"]
        assert clone["name"] == "My Custom Meter"
        assert clone["is_builtin"] is False
```

- [ ] **Step 2: Run all tests**

Run: `cd backend && pytest -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_seed.py
git commit -m "test: add seed data loading and builtin template protection tests"
```

---

## Chunk 4: Frontend Types, Store & API

### Task 12: Create TypeScript Types

**Files:**
- Create: `frontend/src/types/template.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Create template types**

Create `frontend/src/types/template.ts`:

```typescript
export interface TemplateSummary {
  id: string;
  name: string;
  protocol: string;
  description: string | null;
  is_builtin: boolean;
  register_count: number;
  created_at: string;
  updated_at: string;
}

export interface RegisterDefinition {
  id?: string;
  name: string;
  address: number;
  function_code: number;
  data_type: string;
  byte_order: string;
  scale_factor: number;
  unit: string | null;
  description: string | null;
  sort_order: number;
}

export interface TemplateDetail
  extends Omit<TemplateSummary, "register_count"> {
  registers: RegisterDefinition[];
}

export interface CreateTemplate {
  name: string;
  protocol?: string;
  description?: string | null;
  registers: Omit<RegisterDefinition, "id">[];
}

export interface UpdateTemplate extends CreateTemplate {}

export interface TemplateClone {
  new_name?: string;
}

export interface ApiResponse<T> {
  data: T | null;
  message: string | null;
  success: boolean;
}
```

- [ ] **Step 2: Re-export from index.ts**

Add to `frontend/src/types/index.ts`:

```typescript
export type {
  ApiResponse,
  CreateTemplate,
  RegisterDefinition,
  TemplateClone,
  TemplateDetail,
  TemplateSummary,
  UpdateTemplate,
} from "./template";
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/template.ts frontend/src/types/index.ts
git commit -m "feat: add TypeScript types for template domain"
```

---

### Task 13: Create Template API Service

**Files:**
- Create: `frontend/src/services/templateApi.ts`

- [ ] **Step 1: Write API service**

Create `frontend/src/services/templateApi.ts`:

```typescript
import { api } from "./api";
import type {
  ApiResponse,
  CreateTemplate,
  TemplateClone,
  TemplateDetail,
  TemplateSummary,
  UpdateTemplate,
} from "../types";

export const templateApi = {
  list: () =>
    api.get<ApiResponse<TemplateSummary[]>>("/templates").then((r) => r.data),

  get: (id: string) =>
    api.get<ApiResponse<TemplateDetail>>(`/templates/${id}`).then((r) => r.data),

  create: (data: CreateTemplate) =>
    api
      .post<ApiResponse<TemplateDetail>>("/templates", data)
      .then((r) => r.data),

  update: (id: string, data: UpdateTemplate) =>
    api
      .put<ApiResponse<TemplateDetail>>(`/templates/${id}`, data)
      .then((r) => r.data),

  delete: (id: string) =>
    api.delete<ApiResponse<null>>(`/templates/${id}`).then((r) => r.data),

  clone: (id: string, data?: TemplateClone) =>
    api
      .post<ApiResponse<TemplateDetail>>(`/templates/${id}/clone`, data)
      .then((r) => r.data),

  exportTemplate: (id: string) =>
    api
      .get(`/templates/${id}/export`, { responseType: "blob" })
      .then((r) => r.data),

  importTemplate: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return api
      .post<ApiResponse<TemplateDetail>>("/templates/import", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/templateApi.ts
git commit -m "feat: add template API client service"
```

---

### Task 14: Create Template Zustand Store

**Files:**
- Create: `frontend/src/stores/templateStore.ts`

- [ ] **Step 1: Write store**

Create `frontend/src/stores/templateStore.ts`:

```typescript
import { message } from "antd";
import { create } from "zustand";
import { templateApi } from "../services/templateApi";
import type {
  CreateTemplate,
  TemplateClone,
  TemplateDetail,
  TemplateSummary,
  UpdateTemplate,
} from "../types";

interface TemplateState {
  templates: TemplateSummary[];
  currentTemplate: TemplateDetail | null;
  loading: boolean;
  fetchTemplates: () => Promise<void>;
  fetchTemplate: (id: string) => Promise<void>;
  createTemplate: (data: CreateTemplate) => Promise<TemplateDetail | null>;
  updateTemplate: (
    id: string,
    data: UpdateTemplate
  ) => Promise<TemplateDetail | null>;
  deleteTemplate: (id: string) => Promise<boolean>;
  cloneTemplate: (
    id: string,
    data?: TemplateClone
  ) => Promise<TemplateDetail | null>;
  clearCurrentTemplate: () => void;
}

export const useTemplateStore = create<TemplateState>((set) => ({
  templates: [],
  currentTemplate: null,
  loading: false,

  fetchTemplates: async () => {
    set({ loading: true });
    try {
      const response = await templateApi.list();
      set({ templates: response.data ?? [] });
    } finally {
      set({ loading: false });
    }
  },

  fetchTemplate: async (id: string) => {
    set({ loading: true });
    try {
      const response = await templateApi.get(id);
      set({ currentTemplate: response.data });
    } finally {
      set({ loading: false });
    }
  },

  createTemplate: async (data: CreateTemplate) => {
    set({ loading: true });
    try {
      const response = await templateApi.create(data);
      message.success("Template created successfully");
      return response.data;
    } catch {
      return null;
    } finally {
      set({ loading: false });
    }
  },

  updateTemplate: async (id: string, data: UpdateTemplate) => {
    set({ loading: true });
    try {
      const response = await templateApi.update(id, data);
      message.success("Template updated successfully");
      return response.data;
    } catch {
      return null;
    } finally {
      set({ loading: false });
    }
  },

  deleteTemplate: async (id: string) => {
    set({ loading: true });
    try {
      await templateApi.delete(id);
      message.success("Template deleted successfully");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  cloneTemplate: async (id: string, data?: TemplateClone) => {
    set({ loading: true });
    try {
      const response = await templateApi.clone(id, data);
      message.success("Template cloned successfully");
      return response.data;
    } catch {
      return null;
    } finally {
      set({ loading: false });
    }
  },

  clearCurrentTemplate: () => set({ currentTemplate: null }),
}));
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/stores/templateStore.ts
git commit -m "feat: add Zustand template store"
```

---

## Chunk 5: Frontend Pages

### Task 15: Create Template List Page

**Files:**
- Create: `frontend/src/pages/Templates/TemplateList.tsx`
- Create: `frontend/src/pages/Templates/ImportExportButtons.tsx`
- Modify: `frontend/src/pages/Templates/index.tsx`

- [ ] **Step 1: Create ImportExportButtons component**

Create `frontend/src/pages/Templates/ImportExportButtons.tsx`:

```tsx
import { UploadOutlined } from "@ant-design/icons";
import { Button, Upload } from "antd";
import type { UploadProps } from "antd";
import { templateApi } from "../../services/templateApi";
import { useTemplateStore } from "../../stores/templateStore";

export function ImportExportButtons() {
  const { fetchTemplates } = useTemplateStore();

  const handleImport: UploadProps["customRequest"] = async (options) => {
    const file = options.file as File;
    try {
      await templateApi.importTemplate(file);
      await fetchTemplates();
      options.onSuccess?.(null);
    } catch (error) {
      options.onError?.(error as Error);
    }
  };

  return (
    <Upload
      accept=".json"
      showUploadList={false}
      customRequest={handleImport}
    >
      <Button icon={<UploadOutlined />}>Import</Button>
    </Upload>
  );
}

export async function handleExport(templateId: string, templateName: string) {
  const blob = await templateApi.exportTemplate(templateId);
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${templateName.replace(/\s+/g, "_").toLowerCase()}.json`;
  a.click();
  window.URL.revokeObjectURL(url);
}
```

- [ ] **Step 2: Create TemplateList component**

Create `frontend/src/pages/Templates/TemplateList.tsx`:

```tsx
import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExportOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { Button, Popconfirm, Space, Table, Tag, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import type { TemplateSummary } from "../../types";
import { useTemplateStore } from "../../stores/templateStore";
import { handleExport, ImportExportButtons } from "./ImportExportButtons";

export function TemplateList() {
  const navigate = useNavigate();
  const { templates, loading, fetchTemplates, deleteTemplate, cloneTemplate } =
    useTemplateStore();

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  const handleDelete = async (id: string) => {
    const success = await deleteTemplate(id);
    if (success) {
      await fetchTemplates();
    }
  };

  const handleClone = async (id: string) => {
    const cloned = await cloneTemplate(id);
    if (cloned) {
      await fetchTemplates();
    }
  };

  const columns: ColumnsType<TemplateSummary> = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (name: string, record) => (
        <Space>
          {name}
          {record.is_builtin && <Tag color="blue">Built-in</Tag>}
        </Space>
      ),
    },
    {
      title: "Protocol",
      dataIndex: "protocol",
      key: "protocol",
    },
    {
      title: "Registers",
      dataIndex: "register_count",
      key: "register_count",
      align: "center",
    },
    {
      title: "Created",
      dataIndex: "created_at",
      key: "created_at",
      render: (val: string) => new Date(val).toLocaleDateString(),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_, record) => (
        <Space size="small">
          {!record.is_builtin && (
            <Tooltip title="Edit">
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                onClick={() => navigate(`/templates/${record.id}`)}
              />
            </Tooltip>
          )}
          <Tooltip title="Clone">
            <Button
              type="text"
              size="small"
              icon={<CopyOutlined />}
              onClick={() => handleClone(record.id)}
            />
          </Tooltip>
          <Tooltip title="Export">
            <Button
              type="text"
              size="small"
              icon={<ExportOutlined />}
              onClick={() => handleExport(record.id, record.name)}
            />
          </Tooltip>
          {!record.is_builtin && (
            <Popconfirm
              title="Delete this template?"
              onConfirm={() => handleDelete(record.id)}
            >
              <Tooltip title="Delete">
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                />
              </Tooltip>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <div />
        <Space>
          <ImportExportButtons />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate("/templates/new")}
          >
            New Template
          </Button>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={templates}
        rowKey="id"
        loading={loading}
        pagination={false}
      />
    </div>
  );
}
```

- [ ] **Step 3: Update index.tsx**

Replace `frontend/src/pages/Templates/index.tsx`:

```tsx
import { Typography } from "antd";
import { TemplateList } from "./TemplateList";

export default function TemplatesPage() {
  return (
    <div>
      <Typography.Title level={2}>Device Templates</Typography.Title>
      <TemplateList />
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Templates/
git commit -m "feat: add template list page with CRUD actions and import/export"
```

---

### Task 16: Create Register Table Component

**Files:**
- Create: `frontend/src/pages/Templates/RegisterTable.tsx`

- [ ] **Step 1: Write RegisterTable component**

Create `frontend/src/pages/Templates/RegisterTable.tsx`:

```tsx
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Input, InputNumber, Select, Table } from "antd";
import type { RegisterDefinition } from "../../types";

const DATA_TYPE_OPTIONS = [
  { value: "int16", label: "int16" },
  { value: "uint16", label: "uint16" },
  { value: "int32", label: "int32" },
  { value: "uint32", label: "uint32" },
  { value: "float32", label: "float32" },
  { value: "float64", label: "float64" },
];

const BYTE_ORDER_OPTIONS = [
  { value: "big_endian", label: "Big Endian" },
  { value: "little_endian", label: "Little Endian" },
  { value: "big_endian_word_swap", label: "Big Endian (Word Swap)" },
  { value: "little_endian_word_swap", label: "Little Endian (Word Swap)" },
];

const FC_OPTIONS = [
  { value: 3, label: "FC03 (Holding)" },
  { value: 4, label: "FC04 (Input)" },
];

interface RegisterTableProps {
  registers: Omit<RegisterDefinition, "id">[];
  onChange: (registers: Omit<RegisterDefinition, "id">[]) => void;
  disabled?: boolean;
}

export function RegisterTable({
  registers,
  onChange,
  disabled = false,
}: RegisterTableProps) {
  const updateRow = (index: number, field: string, value: unknown) => {
    const updated = [...registers];
    updated[index] = { ...updated[index], [field]: value };
    onChange(updated);
  };

  const addRow = () => {
    onChange([
      ...registers,
      {
        name: "",
        address: 0,
        function_code: 3,
        data_type: "float32",
        byte_order: "big_endian",
        scale_factor: 1.0,
        unit: null,
        description: null,
        sort_order: registers.length,
      },
    ]);
  };

  const deleteRow = (index: number) => {
    const updated = registers.filter((_, i) => i !== index);
    onChange(updated.map((r, i) => ({ ...r, sort_order: i })));
  };

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      width: 140,
      render: (_: string, __: unknown, index: number) => (
        <Input
          value={registers[index].name}
          onChange={(e) => updateRow(index, "name", e.target.value)}
          disabled={disabled}
          size="small"
        />
      ),
    },
    {
      title: "Address",
      dataIndex: "address",
      width: 90,
      render: (_: number, __: unknown, index: number) => (
        <InputNumber
          value={registers[index].address}
          onChange={(val) => updateRow(index, "address", val ?? 0)}
          disabled={disabled}
          size="small"
          min={0}
          style={{ width: "100%" }}
        />
      ),
    },
    {
      title: "FC",
      dataIndex: "function_code",
      width: 130,
      render: (_: number, __: unknown, index: number) => (
        <Select
          value={registers[index].function_code}
          onChange={(val) => updateRow(index, "function_code", val)}
          options={FC_OPTIONS}
          disabled={disabled}
          size="small"
          style={{ width: "100%" }}
        />
      ),
    },
    {
      title: "Data Type",
      dataIndex: "data_type",
      width: 110,
      render: (_: string, __: unknown, index: number) => (
        <Select
          value={registers[index].data_type}
          onChange={(val) => updateRow(index, "data_type", val)}
          options={DATA_TYPE_OPTIONS}
          disabled={disabled}
          size="small"
          style={{ width: "100%" }}
        />
      ),
    },
    {
      title: "Byte Order",
      dataIndex: "byte_order",
      width: 170,
      render: (_: string, __: unknown, index: number) => (
        <Select
          value={registers[index].byte_order}
          onChange={(val) => updateRow(index, "byte_order", val)}
          options={BYTE_ORDER_OPTIONS}
          disabled={disabled}
          size="small"
          style={{ width: "100%" }}
        />
      ),
    },
    {
      title: "Scale",
      dataIndex: "scale_factor",
      width: 80,
      render: (_: number, __: unknown, index: number) => (
        <InputNumber
          value={registers[index].scale_factor}
          onChange={(val) => updateRow(index, "scale_factor", val ?? 1.0)}
          disabled={disabled}
          size="small"
          step={0.1}
          style={{ width: "100%" }}
        />
      ),
    },
    {
      title: "Unit",
      dataIndex: "unit",
      width: 70,
      render: (_: string | null, __: unknown, index: number) => (
        <Input
          value={registers[index].unit ?? ""}
          onChange={(e) => updateRow(index, "unit", e.target.value || null)}
          disabled={disabled}
          size="small"
        />
      ),
    },
    {
      title: "Description",
      dataIndex: "description",
      render: (_: string | null, __: unknown, index: number) => (
        <Input
          value={registers[index].description ?? ""}
          onChange={(e) =>
            updateRow(index, "description", e.target.value || null)
          }
          disabled={disabled}
          size="small"
        />
      ),
    },
    ...(disabled
      ? []
      : [
          {
            title: "",
            width: 40,
            render: (_: unknown, __: unknown, index: number) => (
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => deleteRow(index)}
              />
            ),
          },
        ]),
  ];

  return (
    <div>
      <Table
        columns={columns}
        dataSource={registers.map((r, i) => ({ ...r, _key: i }))}
        rowKey="_key"
        pagination={false}
        size="small"
        scroll={{ x: 1000 }}
      />
      {!disabled && (
        <Button
          type="dashed"
          onClick={addRow}
          icon={<PlusOutlined />}
          style={{ width: "100%", marginTop: 8 }}
        >
          Add Register
        </Button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Templates/RegisterTable.tsx
git commit -m "feat: add editable register table component"
```

---

### Task 17: Create Template Form Page & Update Routes

**Files:**
- Create: `frontend/src/pages/Templates/TemplateForm.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write TemplateForm page**

Create `frontend/src/pages/Templates/TemplateForm.tsx`:

```tsx
import { Button, Card, Form, Input, Select, Space, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { RegisterDefinition } from "../../types";
import { useTemplateStore } from "../../stores/templateStore";
import { RegisterTable } from "./RegisterTable";

const PROTOCOL_OPTIONS = [{ value: "modbus_tcp", label: "Modbus TCP" }];

export default function TemplateForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const {
    currentTemplate,
    loading,
    fetchTemplate,
    createTemplate,
    updateTemplate,
    clearCurrentTemplate,
  } = useTemplateStore();

  const isEdit = Boolean(id);
  const [registers, setRegisters] = useState<Omit<RegisterDefinition, "id">[]>(
    []
  );

  useEffect(() => {
    if (id) {
      fetchTemplate(id);
    }
    return () => clearCurrentTemplate();
  }, [id, fetchTemplate, clearCurrentTemplate]);

  useEffect(() => {
    if (currentTemplate && isEdit) {
      form.setFieldsValue({
        name: currentTemplate.name,
        protocol: currentTemplate.protocol,
        description: currentTemplate.description,
      });
      setRegisters(
        currentTemplate.registers.map(({ id: _id, ...rest }) => rest)
      );
    }
  }, [currentTemplate, isEdit, form]);

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const payload = {
      ...values,
      registers: registers.map((r, i) => ({ ...r, sort_order: i })),
    };

    let result;
    if (isEdit && id) {
      result = await updateTemplate(id, payload);
    } else {
      result = await createTemplate(payload);
    }

    if (result) {
      navigate("/templates");
    }
  };

  return (
    <div>
      <Typography.Title level={2}>
        {isEdit ? "Edit Template" : "New Template"}
      </Typography.Title>

      <Card style={{ marginBottom: 16 }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{ protocol: "modbus_tcp" }}
        >
          <Form.Item
            name="name"
            label="Template Name"
            rules={[{ required: true, message: "Please enter a name" }]}
          >
            <Input placeholder="e.g. My Custom Meter" />
          </Form.Item>
          <Form.Item name="protocol" label="Protocol">
            <Select options={PROTOCOL_OPTIONS} />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} placeholder="Optional description" />
          </Form.Item>
        </Form>
      </Card>

      <Card title="Register Map" style={{ marginBottom: 16 }}>
        <RegisterTable registers={registers} onChange={setRegisters} />
      </Card>

      <Space>
        <Button type="primary" onClick={handleSubmit} loading={loading}>
          {isEdit ? "Save Changes" : "Create Template"}
        </Button>
        <Button onClick={() => navigate("/templates")}>Cancel</Button>
      </Space>
    </div>
  );
}
```

- [ ] **Step 2: Update App.tsx with new routes**

In `frontend/src/App.tsx`, add import:

```typescript
import TemplateForm from "./pages/Templates/TemplateForm";
```

Add two new routes inside the `<Route element={<MainLayout />}>` block. Place them **before** the existing `/templates` route:

```tsx
<Route path="/templates/new" element={<TemplateForm />} />
<Route path="/templates/:id" element={<TemplateForm />} />
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Templates/TemplateForm.tsx frontend/src/App.tsx
git commit -m "feat: add template create/edit page with register table"
```

---

## Chunk 6: Documentation & Final Verification

### Task 18: Update Project Documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/development-log.md`
- Modify: `docs/database-schema.md`
- Modify: `docs/api-reference.md`
- Modify: `docs/development-phases.md`

- [ ] **Step 1: Update CHANGELOG.md**

Add under `## [Unreleased]` → `### Added`:

```markdown
- Device template CRUD API (`GET/POST/PUT/DELETE /api/v1/templates`)
- Template clone API (`POST /api/v1/templates/{id}/clone`)
- Template import/export API (JSON file upload/download)
- Built-in device templates: SDM630 Three-Phase Meter, SDM120 Single-Phase Meter, SunSpec Solar Inverter
- Seed data auto-loader (scans `seed/*.json` on startup)
- Address overlap validation for register definitions
- ApiResponse envelope for consistent API responses (`{data, message, success}`)
- Template list page with Ant Design table, CRUD actions, import/export
- Template create/edit page with editable register map table
- Zustand template store and API client service
- ForbiddenException for builtin template protection
- Alembic migration for `device_templates` and `register_definitions` tables
```

- [ ] **Step 2: Update docs/database-schema.md**

Add the following sections:

```markdown
## device_templates

| Column | Type | Constraint | Description |
|--------|------|-----------|-------------|
| id | UUID | PK, default uuid4 | |
| name | VARCHAR(100) | NOT NULL, UNIQUE | Template name |
| protocol | VARCHAR(50) | NOT NULL, default "modbus_tcp" | Protocol type |
| description | TEXT | nullable | |
| is_builtin | BOOLEAN | NOT NULL, default false | Built-in templates cannot be modified or deleted |
| created_at | TIMESTAMP(TZ) | NOT NULL, server_default now() | |
| updated_at | TIMESTAMP(TZ) | NOT NULL, auto-update on change | |

## register_definitions

| Column | Type | Constraint | Description |
|--------|------|-----------|-------------|
| id | UUID | PK, default uuid4 | |
| template_id | UUID | FK → device_templates.id ON DELETE CASCADE | |
| name | VARCHAR(100) | NOT NULL | Register name (e.g. voltage_l1) |
| address | INTEGER | NOT NULL | Modbus protocol-level 0-based address |
| function_code | SMALLINT | NOT NULL, default 3 | FC03=Holding, FC04=Input |
| data_type | VARCHAR(20) | NOT NULL | int16/uint16/int32/uint32/float32/float64 |
| byte_order | VARCHAR(30) | NOT NULL, default "big_endian" | big/little endian + word swap variants |
| scale_factor | FLOAT | NOT NULL, default 1.0 | raw × scale = display value |
| unit | VARCHAR(20) | nullable | V, A, W, kWh, etc. |
| description | TEXT | nullable | |
| sort_order | INTEGER | NOT NULL, default 0 | Frontend display order |

**Constraints:**
- `(template_id, name)` UNIQUE
- `(template_id, address, function_code)` UNIQUE
```

- [ ] **Step 3: Update docs/api-reference.md**

Add the following sections:

```markdown
## Templates API

Base path: `/api/v1/templates`

### GET /templates
List all templates with register count.
Response: `ApiResponse<TemplateSummary[]>` (200)

### POST /templates
Create a new template with registers.
Body: `TemplateCreate`
Response: `ApiResponse<TemplateDetail>` (201)

### GET /templates/{id}
Get template with full register definitions.
Response: `ApiResponse<TemplateDetail>` (200)
Error: 404 `TEMPLATE_NOT_FOUND`

### PUT /templates/{id}
Update template (full replacement including registers).
Body: `TemplateUpdate`
Response: `ApiResponse<TemplateDetail>` (200)
Error: 403 `BUILTIN_TEMPLATE_IMMUTABLE`, 404 `TEMPLATE_NOT_FOUND`

### DELETE /templates/{id}
Delete a template.
Response: `ApiResponse<null>` with message (200)
Error: 403 `BUILTIN_TEMPLATE_IMMUTABLE`, 404 `TEMPLATE_NOT_FOUND`

### POST /templates/{id}/clone
Clone a template.
Body: `TemplateClone` (optional `new_name`, default: "Copy of {name}")
Response: `ApiResponse<TemplateDetail>` (201)

### GET /templates/{id}/export
Export template as JSON file download (no id fields, Content-Disposition: attachment).
Response: JSON file (200)

### POST /templates/import
Import template from JSON file upload.
Body: multipart/form-data with `file` field
Response: `ApiResponse<TemplateDetail>` (201)
Error: 422 if name already exists
```

- [ ] **Step 4: Update docs/development-phases.md**

Mark all Milestone 2.1 and 2.2 items as `[x]` completed. Update Phase 2 row in the summary table from `🔲` to `✅`.

- [ ] **Step 5: Update docs/development-log.md**

Add entry:

```markdown
## Phase 2: Device Template Module (2026-03-17)

### What was done
- Implemented full device template CRUD with register definitions
- Built seed data system for 3 built-in templates (SDM630, SDM120, SunSpec)
- Created template import/export (JSON file upload/download)
- Built frontend management UI with editable register map table

### Key decisions
- **0-based Modbus addressing**: DB stores protocol-level addresses, not convention (30001+)
- **PUT wholesale replacement**: Update replaces all registers rather than patching individual ones
- **Seed auto-loader**: Scans `seed/*.json` on startup, idempotent (skip if exists)
- **ApiResponse envelope**: Shared `{data, message, success}` format in `schemas/common.py`
- **Route ordering**: `/import` declared before `/{template_id}` to avoid path matching issues

### Issues encountered
- (to be filled during implementation)
```

- [ ] **Step 6: Commit**

```bash
git add CHANGELOG.md docs/
git commit -m "docs: update project docs for Phase 2 completion"
```

---

### Task 19: Full System Verification

- [ ] **Step 1: Run backend tests**

Run: `cd backend && pytest -v`
Expected: All tests PASS.

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 3: Start Docker Compose and verify**

Run: `docker compose up -d`
Verify:
- `curl http://localhost:8000/health` returns `{"status": "ok"}`
- `curl http://localhost:8000/api/v1/templates` returns 3 builtin templates
- Frontend at http://localhost:3000 shows template list

- [ ] **Step 4: Stop Docker Compose**

Run: `docker compose down`
