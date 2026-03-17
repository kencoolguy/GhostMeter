# Phase 3: Device Instance Module Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add device instance CRUD with batch creation, start/stop state control, register value view, and frontend management UI.

**Architecture:** Follows Phase 2 patterns — layered backend (routes → services → models), async SQLAlchemy 2.0, Zustand + Ant Design frontend. Devices reference templates via FK RESTRICT. Status is a pure DB field (no actual Modbus server yet).

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 / asyncpg / Pydantic v2 / Alembic / pytest / React 18 / TypeScript / Ant Design 5 / Zustand / Axios

**Spec:** `docs/superpowers/specs/2026-03-17-phase3-device-instances-design.md`

---

## File Structure

### Backend — New Files

| File | Responsibility |
|------|---------------|
| `backend/app/models/device.py` | SQLAlchemy ORM model: DeviceInstance |
| `backend/app/schemas/device.py` | Pydantic request/response schemas for devices |
| `backend/app/services/device_service.py` | Business logic: CRUD, batch, start/stop, registers |
| `backend/app/api/routes/devices.py` | FastAPI route handlers for /api/v1/devices |
| `backend/tests/test_devices.py` | API integration tests for device CRUD + state |
| `backend/tests/test_template_protection.py` | Tests for template deletion protection |

### Backend — Modified Files

| File | Change |
|------|--------|
| `backend/app/exceptions.py` | Add ConflictException (HTTP 409) |
| `backend/app/models/__init__.py` | Export DeviceInstance |
| `backend/app/schemas/__init__.py` | Export device schemas |
| `backend/app/services/__init__.py` | Export device_service |
| `backend/app/services/template_service.py` | Add device-in-use check in delete_template |
| `backend/app/main.py` | Register devices router |
| `backend/tests/conftest.py` | Add device_instances to TRUNCATE |

### Frontend — New Files

| File | Responsibility |
|------|---------------|
| `frontend/src/types/device.ts` | TypeScript interfaces for device domain |
| `frontend/src/services/deviceApi.ts` | Axios API calls for devices |
| `frontend/src/stores/deviceStore.ts` | Zustand store for device state |
| `frontend/src/pages/Devices/DeviceList.tsx` | Table component for device list |
| `frontend/src/pages/Devices/CreateDeviceModal.tsx` | Create device modal (single + batch tabs) |
| `frontend/src/pages/Devices/DeviceDetail.tsx` | Device detail page with register list |

### Frontend — Modified Files

| File | Change |
|------|--------|
| `frontend/src/pages/Devices/index.tsx` | Replace placeholder with DeviceList |
| `frontend/src/App.tsx` | Add route for /devices/:id |
| `frontend/src/types/index.ts` | Re-export from device.ts |

---

## Chunk 1: Backend Foundation (Exception, Model, Migration, Schemas)

### Task 1: Add ConflictException

**Files:**
- Modify: `backend/app/exceptions.py`

- [ ] **Step 1: Add ConflictException**

Add after `ForbiddenException` in `backend/app/exceptions.py`:

```python
class ConflictException(AppException):
    """Resource conflict."""

    def __init__(
        self,
        detail: str = "Resource conflict",
        error_code: str = "CONFLICT",
    ) -> None:
        super().__init__(status_code=409, error_code=error_code, detail=detail)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/exceptions.py
git commit -m "feat: add ConflictException for HTTP 409 responses"
```

---

### Task 2: Create DeviceInstance ORM Model

**Files:**
- Create: `backend/app/models/device.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write DeviceInstance model**

Create `backend/app/models/device.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class DeviceInstance(Base):
    """A virtual device instance created from a template."""

    __tablename__ = "device_instances"
    __table_args__ = (
        UniqueConstraint("slave_id", "port", name="uq_device_slave_port"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_templates.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slave_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="stopped"
    )
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=502)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    template: Mapped["DeviceTemplate"] = relationship()
```

Note: Import `DeviceTemplate` via string reference — SQLAlchemy resolves it at runtime.

- [ ] **Step 2: Export from `__init__.py`**

Update `backend/app/models/__init__.py`:

```python
from app.models.device import DeviceInstance
from app.models.template import DeviceTemplate, RegisterDefinition

__all__ = ["DeviceInstance", "DeviceTemplate", "RegisterDefinition"]
```

- [ ] **Step 3: Verify import**

Run: `cd backend && python3.12 -c "from app.models import DeviceInstance; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/device.py backend/app/models/__init__.py
git commit -m "feat: add DeviceInstance ORM model"
```

---

### Task 3: Create Alembic Migration

**Files:**
- Create: `backend/alembic/versions/xxxx_add_device_instances.py` (auto-generated)

- [ ] **Step 1: Generate migration**

Run: `cd backend && POSTGRES_PORT=5434 alembic revision --autogenerate -m "add device_instances"`

- [ ] **Step 2: Review generated migration**

Verify:
- `op.create_table('device_instances', ...)` with all columns
- FK to `device_templates.id` with `ondelete='RESTRICT'`
- Unique constraint `uq_device_slave_port` on `(slave_id, port)`

- [ ] **Step 3: Run migration**

Run: `cd backend && POSTGRES_PORT=5434 alembic upgrade head`

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat: add migration for device_instances table"
```

---

### Task 4: Create Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/device.py`
- Modify: `backend/app/schemas/__init__.py`

- [ ] **Step 1: Write device schemas**

Create `backend/app/schemas/device.py`:

```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


# --- Request Schemas ---

class DeviceCreate(BaseModel):
    """Schema for creating a single device."""

    template_id: UUID
    name: str
    slave_id: int
    port: int = 502
    description: str | None = None

    @field_validator("slave_id")
    @classmethod
    def validate_slave_id(cls, v: int) -> int:
        if v < 1 or v > 247:
            raise ValueError("Slave ID must be between 1 and 247")
        return v


class DeviceBatchCreate(BaseModel):
    """Schema for batch creating devices."""

    template_id: UUID
    slave_id_start: int
    slave_id_end: int
    port: int = 502
    name_prefix: str | None = None
    description: str | None = None

    @field_validator("slave_id_start", "slave_id_end")
    @classmethod
    def validate_slave_ids(cls, v: int) -> int:
        if v < 1 or v > 247:
            raise ValueError("Slave ID must be between 1 and 247")
        return v


class DeviceUpdate(BaseModel):
    """Schema for updating a device (full replacement, no template_id/status)."""

    name: str
    slave_id: int
    port: int = 502
    description: str | None = None

    @field_validator("slave_id")
    @classmethod
    def validate_slave_id(cls, v: int) -> int:
        if v < 1 or v > 247:
            raise ValueError("Slave ID must be between 1 and 247")
        return v


# --- Response Schemas ---

class DeviceSummary(BaseModel):
    """Schema for device list items."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    template_name: str
    name: str
    slave_id: int
    status: str
    port: int
    description: str | None
    created_at: datetime
    updated_at: datetime


class RegisterValue(BaseModel):
    """Register definition with current value (Phase 3: always None)."""

    name: str
    address: int
    function_code: int
    data_type: str
    byte_order: str
    scale_factor: float
    unit: str | None
    description: str | None
    value: float | None = None


class DeviceDetail(BaseModel):
    """Schema for full device detail with registers."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    template_name: str
    name: str
    slave_id: int
    status: str
    port: int
    description: str | None
    registers: list[RegisterValue]
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 2: Update `__init__.py`**

Add to `backend/app/schemas/__init__.py`:

```python
from app.schemas.device import (
    DeviceBatchCreate,
    DeviceCreate,
    DeviceDetail,
    DeviceSummary,
    DeviceUpdate,
    RegisterValue,
)
```

And add them all to `__all__`.

- [ ] **Step 3: Verify import**

Run: `cd backend && python3.12 -c "from app.schemas import DeviceCreate, DeviceSummary; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/device.py backend/app/schemas/__init__.py
git commit -m "feat: add Pydantic schemas for device CRUD"
```

---

## Chunk 2: Backend Tests & Service (TDD)

### Task 5: Write Device API Tests (TDD Red)

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_devices.py`

- [ ] **Step 1: Update conftest.py to truncate device_instances**

In `backend/tests/conftest.py`, update the TRUNCATE statement to include `device_instances`:

```python
await conn.execute(text(
    "TRUNCATE device_templates, register_definitions, device_instances CASCADE"
))
```

- [ ] **Step 2: Write test_devices.py**

Create `backend/tests/test_devices.py`:

```python
from httpx import AsyncClient

# Reuse template creation helper
TEMPLATE_PAYLOAD = {
    "name": "Test Meter",
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
    ],
}


async def create_template(client: AsyncClient) -> dict:
    """Helper: create a template and return its data."""
    response = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert response.status_code == 201
    return response.json()["data"]


async def create_device(
    client: AsyncClient,
    template_id: str,
    name: str = "Test Device",
    slave_id: int = 1,
) -> dict:
    """Helper: create a device and return its data."""
    response = await client.post(
        "/api/v1/devices",
        json={
            "template_id": template_id,
            "name": name,
            "slave_id": slave_id,
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


class TestCreateDevice:
    async def test_create_device_success(self, client: AsyncClient) -> None:
        template = await create_template(client)
        data = await create_device(client, template["id"])
        assert data["name"] == "Test Device"
        assert data["slave_id"] == 1
        assert data["status"] == "stopped"
        assert data["template_name"] == "Test Meter"

    async def test_create_device_invalid_slave_id(self, client: AsyncClient) -> None:
        template = await create_template(client)
        response = await client.post(
            "/api/v1/devices",
            json={"template_id": template["id"], "name": "Bad", "slave_id": 0},
        )
        assert response.status_code == 422

    async def test_create_device_slave_id_too_high(self, client: AsyncClient) -> None:
        template = await create_template(client)
        response = await client.post(
            "/api/v1/devices",
            json={"template_id": template["id"], "name": "Bad", "slave_id": 248},
        )
        assert response.status_code == 422

    async def test_create_device_duplicate_slave_id(self, client: AsyncClient) -> None:
        template = await create_template(client)
        await create_device(client, template["id"], slave_id=1)
        response = await client.post(
            "/api/v1/devices",
            json={"template_id": template["id"], "name": "Dup", "slave_id": 1},
        )
        assert response.status_code == 422
        assert "already in use" in response.json()["detail"]

    async def test_create_device_invalid_template(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/devices",
            json={
                "template_id": "00000000-0000-0000-0000-000000000000",
                "name": "Bad",
                "slave_id": 1,
            },
        )
        assert response.status_code == 404


class TestBatchCreateDevices:
    async def test_batch_create_success(self, client: AsyncClient) -> None:
        template = await create_template(client)
        response = await client.post(
            "/api/v1/devices/batch",
            json={
                "template_id": template["id"],
                "slave_id_start": 1,
                "slave_id_end": 3,
            },
        )
        assert response.status_code == 201
        devices = response.json()["data"]
        assert len(devices) == 3
        assert devices[0]["name"] == "Test Meter - Slave 1"

    async def test_batch_create_with_prefix(self, client: AsyncClient) -> None:
        template = await create_template(client)
        response = await client.post(
            "/api/v1/devices/batch",
            json={
                "template_id": template["id"],
                "slave_id_start": 10,
                "slave_id_end": 11,
                "name_prefix": "Floor 3",
            },
        )
        assert response.status_code == 201
        devices = response.json()["data"]
        assert devices[0]["name"] == "Floor 3 10"

    async def test_batch_create_invalid_range(self, client: AsyncClient) -> None:
        template = await create_template(client)
        response = await client.post(
            "/api/v1/devices/batch",
            json={
                "template_id": template["id"],
                "slave_id_start": 5,
                "slave_id_end": 3,
            },
        )
        assert response.status_code == 422

    async def test_batch_create_too_many(self, client: AsyncClient) -> None:
        template = await create_template(client)
        response = await client.post(
            "/api/v1/devices/batch",
            json={
                "template_id": template["id"],
                "slave_id_start": 1,
                "slave_id_end": 51,
            },
        )
        assert response.status_code == 422

    async def test_batch_create_partial_conflict(self, client: AsyncClient) -> None:
        template = await create_template(client)
        await create_device(client, template["id"], slave_id=2)
        response = await client.post(
            "/api/v1/devices/batch",
            json={
                "template_id": template["id"],
                "slave_id_start": 1,
                "slave_id_end": 3,
            },
        )
        assert response.status_code == 422


class TestListDevices:
    async def test_list_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/devices")
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_list_with_data(self, client: AsyncClient) -> None:
        template = await create_template(client)
        await create_device(client, template["id"])
        response = await client.get("/api/v1/devices")
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["template_name"] == "Test Meter"


class TestGetDevice:
    async def test_get_device_detail(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        response = await client.get(f"/api/v1/devices/{device['id']}")
        assert response.status_code == 200
        detail = response.json()["data"]
        assert detail["name"] == "Test Device"
        assert len(detail["registers"]) == 1
        assert detail["registers"][0]["name"] == "voltage"
        assert detail["registers"][0]["value"] is None
        assert "byte_order" in detail["registers"][0]
        assert "scale_factor" in detail["registers"][0]

    async def test_get_device_not_found(self, client: AsyncClient) -> None:
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/v1/devices/{fake_id}")
        assert response.status_code == 404
        assert response.json()["error_code"] == "DEVICE_NOT_FOUND"


class TestUpdateDevice:
    async def test_update_success(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        response = await client.put(
            f"/api/v1/devices/{device['id']}",
            json={"name": "Updated", "slave_id": 5},
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated"
        assert response.json()["data"]["slave_id"] == 5

    async def test_update_running_device_blocked(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        await client.post(f"/api/v1/devices/{device['id']}/start")
        response = await client.put(
            f"/api/v1/devices/{device['id']}",
            json={"name": "Updated", "slave_id": 1},
        )
        assert response.status_code == 409


class TestDeleteDevice:
    async def test_delete_success(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        response = await client.delete(f"/api/v1/devices/{device['id']}")
        assert response.status_code == 200

    async def test_delete_running_blocked(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        await client.post(f"/api/v1/devices/{device['id']}/start")
        response = await client.delete(f"/api/v1/devices/{device['id']}")
        assert response.status_code == 409

class TestStartStop:
    async def test_start_device(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        response = await client.post(f"/api/v1/devices/{device['id']}/start")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "running"

    async def test_stop_device(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        await client.post(f"/api/v1/devices/{device['id']}/start")
        response = await client.post(f"/api/v1/devices/{device['id']}/stop")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "stopped"

    async def test_start_already_running(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        await client.post(f"/api/v1/devices/{device['id']}/start")
        response = await client.post(f"/api/v1/devices/{device['id']}/start")
        assert response.status_code == 409

    async def test_stop_already_stopped(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        response = await client.post(f"/api/v1/devices/{device['id']}/stop")
        assert response.status_code == 409

    async def test_start_error_state_blocked(self, client: AsyncClient) -> None:
        """Devices in error state cannot be started (only stopped)."""
        # Phase 3 has no API to set error state directly;
        # we test via direct DB manipulation
        pass  # Covered in Phase 4 when error state can be triggered


class TestGetRegisters:
    async def test_get_registers(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        response = await client.get(f"/api/v1/devices/{device['id']}/registers")
        assert response.status_code == 200
        regs = response.json()["data"]
        assert len(regs) == 1
        assert regs[0]["name"] == "voltage"
        assert regs[0]["value"] is None
```

- [ ] **Step 3: Commit tests (RED)**

```bash
git add backend/tests/conftest.py backend/tests/test_devices.py
git commit -m "test: add device CRUD and state management tests (RED)"
```

---

### Task 6: Implement Device Service (TDD Green)

**Files:**
- Create: `backend/app/services/device_service.py`
- Modify: `backend/app/services/__init__.py`

- [ ] **Step 1: Write device_service.py**

Create `backend/app/services/device_service.py`:

```python
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.device import DeviceInstance
from app.models.template import DeviceTemplate, RegisterDefinition
from app.schemas.device import (
    DeviceBatchCreate,
    DeviceCreate,
    DeviceUpdate,
    RegisterValue,
)

logger = logging.getLogger(__name__)


async def _get_device_raw(
    session: AsyncSession, device_id: uuid.UUID,
) -> DeviceInstance:
    """Get device ORM object or raise 404."""
    stmt = select(DeviceInstance).where(DeviceInstance.id == device_id)
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()
    if device is None:
        raise NotFoundException(
            detail="Device not found", error_code="DEVICE_NOT_FOUND"
        )
    return device


async def _check_slave_id_available(
    session: AsyncSession,
    slave_id: int,
    port: int,
    exclude_device_id: uuid.UUID | None = None,
) -> None:
    """Raise 422 if slave_id is already in use on this port."""
    stmt = select(DeviceInstance).where(
        DeviceInstance.slave_id == slave_id,
        DeviceInstance.port == port,
    )
    if exclude_device_id:
        stmt = stmt.where(DeviceInstance.id != exclude_device_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise ValidationException(
            f"Slave ID {slave_id} is already in use on port {port}"
        )


async def _get_template_or_404(
    session: AsyncSession, template_id: uuid.UUID,
) -> DeviceTemplate:
    """Get template or raise 404."""
    stmt = (
        select(DeviceTemplate)
        .options(selectinload(DeviceTemplate.registers))
        .where(DeviceTemplate.id == template_id)
    )
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundException(
            detail="Template not found", error_code="TEMPLATE_NOT_FOUND"
        )
    return template


def _device_to_summary(device: DeviceInstance, template_name: str) -> dict:
    """Convert device ORM to summary dict."""
    return {
        "id": device.id,
        "template_id": device.template_id,
        "template_name": template_name,
        "name": device.name,
        "slave_id": device.slave_id,
        "status": device.status,
        "port": device.port,
        "description": device.description,
        "created_at": device.created_at,
        "updated_at": device.updated_at,
    }


async def list_devices(session: AsyncSession) -> list[dict]:
    """List all devices with template name."""
    stmt = (
        select(DeviceInstance, DeviceTemplate.name.label("template_name"))
        .join(DeviceTemplate, DeviceInstance.template_id == DeviceTemplate.id)
        .order_by(DeviceInstance.created_at)
    )
    result = await session.execute(stmt)
    return [
        _device_to_summary(row.DeviceInstance, row.template_name)
        for row in result.all()
    ]


async def get_device(session: AsyncSession, device_id: uuid.UUID) -> dict:
    """Get a single device with template name."""
    stmt = (
        select(DeviceInstance, DeviceTemplate.name.label("template_name"))
        .join(DeviceTemplate, DeviceInstance.template_id == DeviceTemplate.id)
        .where(DeviceInstance.id == device_id)
    )
    result = await session.execute(stmt)
    row = result.one_or_none()
    if row is None:
        raise NotFoundException(
            detail="Device not found", error_code="DEVICE_NOT_FOUND"
        )
    return _device_to_summary(row.DeviceInstance, row.template_name)


async def get_device_detail(session: AsyncSession, device_id: uuid.UUID) -> dict:
    """Get device with template registers (value=None)."""
    device_data = await get_device(session, device_id)

    # Get template registers
    template = await _get_template_or_404(session, device_data["template_id"])
    registers = [
        RegisterValue(
            name=reg.name,
            address=reg.address,
            function_code=reg.function_code,
            data_type=reg.data_type,
            byte_order=reg.byte_order,
            scale_factor=reg.scale_factor,
            unit=reg.unit,
            description=reg.description,
            value=None,
        ).model_dump()
        for reg in template.registers
    ]

    return {**device_data, "registers": registers}


async def create_device(
    session: AsyncSession, data: DeviceCreate,
) -> dict:
    """Create a single device."""
    await _get_template_or_404(session, data.template_id)
    await _check_slave_id_available(session, data.slave_id, data.port)

    device = DeviceInstance(
        template_id=data.template_id,
        name=data.name,
        slave_id=data.slave_id,
        port=data.port,
        description=data.description,
    )
    session.add(device)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValidationException(f"Database constraint violation: {e}") from e
    await session.refresh(device)

    return await get_device(session, device.id)


async def batch_create_devices(
    session: AsyncSession, data: DeviceBatchCreate,
) -> list[dict]:
    """Batch create devices. Atomic — all or nothing."""
    if data.slave_id_start > data.slave_id_end:
        raise ValidationException("slave_id_start must be <= slave_id_end")

    count = data.slave_id_end - data.slave_id_start + 1
    if count > 50:
        raise ValidationException("Batch create limited to 50 devices")

    template = await _get_template_or_404(session, data.template_id)

    # Check all slave IDs are available
    for sid in range(data.slave_id_start, data.slave_id_end + 1):
        await _check_slave_id_available(session, sid, data.port)

    # Build name prefix
    prefix = data.name_prefix or template.name

    devices = []
    for sid in range(data.slave_id_start, data.slave_id_end + 1):
        if data.name_prefix:
            name = f"{prefix} {sid}"
        else:
            name = f"{prefix} - Slave {sid}"

        if len(name) > 200:
            raise ValidationException(
                f"Generated name '{name}' exceeds 200 character limit"
            )

        device = DeviceInstance(
            template_id=data.template_id,
            name=name,
            slave_id=sid,
            port=data.port,
            description=data.description,
        )
        session.add(device)
        devices.append(device)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValidationException(f"Database constraint violation: {e}") from e

    # Refresh and get summaries
    result = []
    for device in devices:
        await session.refresh(device)
        result.append(await get_device(session, device.id))
    return result


async def update_device(
    session: AsyncSession, device_id: uuid.UUID, data: DeviceUpdate,
) -> dict:
    """Update a device. Running devices cannot be updated."""
    device = await _get_device_raw(session, device_id)

    if device.status == "running":
        raise ConflictException(
            detail="Cannot update a running device",
            error_code="DEVICE_RUNNING",
        )

    await _check_slave_id_available(
        session, data.slave_id, data.port, exclude_device_id=device_id
    )

    device.name = data.name
    device.slave_id = data.slave_id
    device.port = data.port
    device.description = data.description

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValidationException(f"Database constraint violation: {e}") from e

    return await get_device(session, device.id)


async def delete_device(
    session: AsyncSession, device_id: uuid.UUID,
) -> None:
    """Delete a device. Running devices cannot be deleted."""
    device = await _get_device_raw(session, device_id)

    if device.status == "running":
        raise ConflictException(
            detail="Cannot delete a running device",
            error_code="DEVICE_RUNNING",
        )

    await session.delete(device)
    await session.commit()


async def start_device(
    session: AsyncSession, device_id: uuid.UUID,
) -> dict:
    """Start a device (stopped → running)."""
    device = await _get_device_raw(session, device_id)

    if device.status != "stopped":
        raise ConflictException(
            detail=f"Device is already {device.status}",
            error_code="INVALID_STATE_TRANSITION",
        )

    device.status = "running"
    await session.commit()
    return await get_device(session, device.id)


async def stop_device(
    session: AsyncSession, device_id: uuid.UUID,
) -> dict:
    """Stop a device (running/error → stopped)."""
    device = await _get_device_raw(session, device_id)

    if device.status == "stopped":
        raise ConflictException(
            detail="Device is already stopped",
            error_code="INVALID_STATE_TRANSITION",
        )

    device.status = "stopped"
    await session.commit()
    return await get_device(session, device.id)


async def get_device_registers(
    session: AsyncSession, device_id: uuid.UUID,
) -> list[dict]:
    """Get register definitions for a device (value=None in Phase 3)."""
    device_data = await get_device(session, device_id)
    template = await _get_template_or_404(session, device_data["template_id"])
    return [
        RegisterValue(
            name=reg.name,
            address=reg.address,
            function_code=reg.function_code,
            data_type=reg.data_type,
            byte_order=reg.byte_order,
            scale_factor=reg.scale_factor,
            unit=reg.unit,
            description=reg.description,
            value=None,
        ).model_dump()
        for reg in template.registers
    ]
```

- [ ] **Step 2: Update `__init__.py`**

Add to `backend/app/services/__init__.py`:

```python
from app.services import device_service
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/device_service.py backend/app/services/__init__.py
git commit -m "feat: add device service with CRUD, batch, start/stop, registers"
```

---

### Task 7: Create Device API Routes & Wire Up

**Files:**
- Create: `backend/app/api/routes/devices.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write route handlers**

Create `backend/app/api/routes/devices.py`:

```python
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiResponse
from app.schemas.device import (
    DeviceBatchCreate,
    DeviceCreate,
    DeviceDetail,
    DeviceSummary,
    DeviceUpdate,
    RegisterValue,
)
from app.services import device_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[DeviceSummary]])
async def list_devices(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[DeviceSummary]]:
    """List all device instances."""
    devices = await device_service.list_devices(session)
    return ApiResponse(data=[DeviceSummary(**d) for d in devices])


@router.post("", response_model=ApiResponse[DeviceSummary], status_code=201)
async def create_device(
    data: DeviceCreate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[DeviceSummary]:
    """Create a single device instance."""
    device = await device_service.create_device(session, data)
    return ApiResponse(data=DeviceSummary(**device))


# /batch MUST come before /{device_id}
@router.post("/batch", response_model=ApiResponse[list[DeviceSummary]], status_code=201)
async def batch_create_devices(
    data: DeviceBatchCreate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[DeviceSummary]]:
    """Batch create device instances."""
    devices = await device_service.batch_create_devices(session, data)
    return ApiResponse(data=[DeviceSummary(**d) for d in devices])


@router.get("/{device_id}", response_model=ApiResponse[DeviceDetail])
async def get_device(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[DeviceDetail]:
    """Get device detail with register definitions."""
    detail = await device_service.get_device_detail(session, device_id)
    return ApiResponse(data=DeviceDetail(**detail))


@router.put("/{device_id}", response_model=ApiResponse[DeviceSummary])
async def update_device(
    device_id: uuid.UUID,
    data: DeviceUpdate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[DeviceSummary]:
    """Update a device instance."""
    device = await device_service.update_device(session, device_id, data)
    return ApiResponse(data=DeviceSummary(**device))


@router.delete("/{device_id}", response_model=ApiResponse[None])
async def delete_device(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete a device instance."""
    await device_service.delete_device(session, device_id)
    return ApiResponse(message="Device deleted successfully")


@router.post("/{device_id}/start", response_model=ApiResponse[DeviceSummary])
async def start_device(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[DeviceSummary]:
    """Start a device (stopped → running)."""
    device = await device_service.start_device(session, device_id)
    return ApiResponse(data=DeviceSummary(**device))


@router.post("/{device_id}/stop", response_model=ApiResponse[DeviceSummary])
async def stop_device(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[DeviceSummary]:
    """Stop a device (running/error → stopped)."""
    device = await device_service.stop_device(session, device_id)
    return ApiResponse(data=DeviceSummary(**device))


@router.get("/{device_id}/registers", response_model=ApiResponse[list[RegisterValue]])
async def get_device_registers(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[RegisterValue]]:
    """Get register values for a device (Phase 3: always null)."""
    registers = await device_service.get_device_registers(session, device_id)
    return ApiResponse(data=[RegisterValue(**r) for r in registers])
```

- [ ] **Step 2: Register devices router in main.py**

In `backend/app/main.py`, add import:

```python
from app.api.routes.devices import router as devices_router
```

Add after the templates router line:

```python
api_v1_router.include_router(devices_router, prefix="/devices", tags=["devices"])
```

- [ ] **Step 3: Run tests (TDD Green)**

Run: `cd backend && POSTGRES_PORT=5434 python3.12 -m pytest tests/test_devices.py -v`
Expected: All tests PASS.

- [ ] **Step 4: Run full suite**

Run: `cd backend && POSTGRES_PORT=5434 python3.12 -m pytest -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/devices.py backend/app/main.py
git commit -m "feat: add device API routes and register in main app — tests green"
```

---

### Task 8: Add Template Deletion Protection + Tests

**Files:**
- Modify: `backend/app/services/template_service.py`
- Create: `backend/tests/test_template_protection.py`

- [ ] **Step 1: Add device-in-use check to delete_template**

In `backend/app/services/template_service.py`, add import at top:

```python
from app.exceptions import ConflictException
from app.models.device import DeviceInstance
```

In `delete_template`, add before the `is_builtin` check:

```python
    # Check if template is in use by devices
    device_count = await session.scalar(
        select(func.count(DeviceInstance.id))
        .where(DeviceInstance.template_id == template_id)
    )
    if device_count > 0:
        raise ConflictException(
            detail=f"Template is in use by {device_count} device(s)",
            error_code="TEMPLATE_IN_USE",
        )
```

- [ ] **Step 2: Write protection tests**

Create `backend/tests/test_template_protection.py`:

```python
from httpx import AsyncClient


TEMPLATE_PAYLOAD = {
    "name": "Protected Meter",
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
            "sort_order": 0,
        },
    ],
}


class TestTemplateProtection:
    async def test_cannot_delete_template_in_use(self, client: AsyncClient) -> None:
        # Create template
        resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
        template_id = resp.json()["data"]["id"]

        # Create device using this template
        await client.post(
            "/api/v1/devices",
            json={"template_id": template_id, "name": "Dev 1", "slave_id": 1},
        )

        # Try to delete template
        resp = await client.delete(f"/api/v1/templates/{template_id}")
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "TEMPLATE_IN_USE"
        assert "1 device(s)" in resp.json()["detail"]

    async def test_can_delete_template_after_devices_removed(
        self, client: AsyncClient,
    ) -> None:
        resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
        template_id = resp.json()["data"]["id"]

        resp = await client.post(
            "/api/v1/devices",
            json={"template_id": template_id, "name": "Dev 1", "slave_id": 1},
        )
        device_id = resp.json()["data"]["id"]

        # Delete device first
        await client.delete(f"/api/v1/devices/{device_id}")

        # Now template can be deleted
        resp = await client.delete(f"/api/v1/templates/{template_id}")
        assert resp.status_code == 200
```

- [ ] **Step 3: Run all tests**

Run: `cd backend && POSTGRES_PORT=5434 python3.12 -m pytest -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/template_service.py backend/tests/test_template_protection.py
git commit -m "feat: add template deletion protection when devices exist"
```

---

## Chunk 3: Frontend Types, Store & API

### Task 9: Create TypeScript Types

**Files:**
- Create: `frontend/src/types/device.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Create device types**

Create `frontend/src/types/device.ts`:

```typescript
export interface DeviceSummary {
  id: string;
  template_id: string;
  template_name: string;
  name: string;
  slave_id: number;
  status: "stopped" | "running" | "error";
  port: number;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface RegisterValue {
  name: string;
  address: number;
  function_code: number;
  data_type: string;
  byte_order: string;
  scale_factor: number;
  unit: string | null;
  description: string | null;
  value: number | null;
}

export interface DeviceDetail extends DeviceSummary {
  registers: RegisterValue[];
}

export interface CreateDevice {
  template_id: string;
  name: string;
  slave_id: number;
  port?: number;
  description?: string | null;
}

export interface BatchCreateDevice {
  template_id: string;
  slave_id_start: number;
  slave_id_end: number;
  port?: number;
  name_prefix?: string | null;
  description?: string | null;
}

export interface UpdateDevice {
  name: string;
  slave_id: number;
  port?: number;
  description?: string | null;
}
```

- [ ] **Step 2: Re-export from index.ts**

Add to `frontend/src/types/index.ts`:

```typescript
export type {
  BatchCreateDevice,
  CreateDevice,
  DeviceDetail,
  DeviceSummary,
  RegisterValue,
  UpdateDevice,
} from "./device";
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/device.ts frontend/src/types/index.ts
git commit -m "feat: add TypeScript types for device domain"
```

---

### Task 10: Create Device API Service

**Files:**
- Create: `frontend/src/services/deviceApi.ts`

- [ ] **Step 1: Write API service**

Create `frontend/src/services/deviceApi.ts`:

```typescript
import { api } from "./api";
import type {
  ApiResponse,
  BatchCreateDevice,
  CreateDevice,
  DeviceDetail,
  DeviceSummary,
  RegisterValue,
  UpdateDevice,
} from "../types";

export const deviceApi = {
  list: () =>
    api.get<ApiResponse<DeviceSummary[]>>("/devices").then((r) => r.data),

  get: (id: string) =>
    api.get<ApiResponse<DeviceDetail>>(`/devices/${id}`).then((r) => r.data),

  create: (data: CreateDevice) =>
    api.post<ApiResponse<DeviceSummary>>("/devices", data).then((r) => r.data),

  batchCreate: (data: BatchCreateDevice) =>
    api
      .post<ApiResponse<DeviceSummary[]>>("/devices/batch", data)
      .then((r) => r.data),

  update: (id: string, data: UpdateDevice) =>
    api
      .put<ApiResponse<DeviceSummary>>(`/devices/${id}`, data)
      .then((r) => r.data),

  delete: (id: string) =>
    api.delete<ApiResponse<null>>(`/devices/${id}`).then((r) => r.data),

  start: (id: string) =>
    api
      .post<ApiResponse<DeviceSummary>>(`/devices/${id}/start`)
      .then((r) => r.data),

  stop: (id: string) =>
    api
      .post<ApiResponse<DeviceSummary>>(`/devices/${id}/stop`)
      .then((r) => r.data),

  getRegisters: (id: string) =>
    api
      .get<ApiResponse<RegisterValue[]>>(`/devices/${id}/registers`)
      .then((r) => r.data),
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/deviceApi.ts
git commit -m "feat: add device API client service"
```

---

### Task 11: Create Device Zustand Store

**Files:**
- Create: `frontend/src/stores/deviceStore.ts`

- [ ] **Step 1: Write store**

Create `frontend/src/stores/deviceStore.ts`:

```typescript
import { message } from "antd";
import { create } from "zustand";
import { deviceApi } from "../services/deviceApi";
import type {
  BatchCreateDevice,
  CreateDevice,
  DeviceDetail,
  DeviceSummary,
  UpdateDevice,
} from "../types";

interface DeviceState {
  devices: DeviceSummary[];
  currentDevice: DeviceDetail | null;
  loading: boolean;
  fetchDevices: () => Promise<void>;
  fetchDevice: (id: string) => Promise<void>;
  createDevice: (data: CreateDevice) => Promise<DeviceSummary | null>;
  batchCreateDevices: (data: BatchCreateDevice) => Promise<boolean>;
  updateDevice: (id: string, data: UpdateDevice) => Promise<DeviceSummary | null>;
  deleteDevice: (id: string) => Promise<boolean>;
  startDevice: (id: string) => Promise<boolean>;
  stopDevice: (id: string) => Promise<boolean>;
  clearCurrentDevice: () => void;
}

export const useDeviceStore = create<DeviceState>((set) => ({
  devices: [],
  currentDevice: null,
  loading: false,

  fetchDevices: async () => {
    set({ loading: true });
    try {
      const response = await deviceApi.list();
      set({ devices: response.data ?? [] });
    } finally {
      set({ loading: false });
    }
  },

  fetchDevice: async (id: string) => {
    set({ loading: true });
    try {
      const response = await deviceApi.get(id);
      set({ currentDevice: response.data });
    } finally {
      set({ loading: false });
    }
  },

  createDevice: async (data: CreateDevice) => {
    set({ loading: true });
    try {
      const response = await deviceApi.create(data);
      message.success("Device created successfully");
      return response.data;
    } catch {
      return null;
    } finally {
      set({ loading: false });
    }
  },

  batchCreateDevices: async (data: BatchCreateDevice) => {
    set({ loading: true });
    try {
      await deviceApi.batchCreate(data);
      message.success("Devices created successfully");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  updateDevice: async (id: string, data: UpdateDevice) => {
    set({ loading: true });
    try {
      const response = await deviceApi.update(id, data);
      message.success("Device updated successfully");
      return response.data;
    } catch {
      return null;
    } finally {
      set({ loading: false });
    }
  },

  deleteDevice: async (id: string) => {
    set({ loading: true });
    try {
      await deviceApi.delete(id);
      message.success("Device deleted successfully");
      return true;
    } catch {
      return false;
    } finally {
      set({ loading: false });
    }
  },

  startDevice: async (id: string) => {
    try {
      await deviceApi.start(id);
      return true;
    } catch {
      return false;
    }
  },

  stopDevice: async (id: string) => {
    try {
      await deviceApi.stop(id);
      return true;
    } catch {
      return false;
    }
  },

  clearCurrentDevice: () => set({ currentDevice: null }),
}));
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/stores/deviceStore.ts
git commit -m "feat: add Zustand device store"
```

---

## Chunk 4: Frontend Pages

### Task 12: Create Device List Page + Create Modal

**Files:**
- Create: `frontend/src/pages/Devices/CreateDeviceModal.tsx`
- Create: `frontend/src/pages/Devices/DeviceList.tsx`
- Modify: `frontend/src/pages/Devices/index.tsx`

- [ ] **Step 1: Create CreateDeviceModal**

Create `frontend/src/pages/Devices/CreateDeviceModal.tsx`:

```tsx
import { Form, Input, InputNumber, Modal, Select, Tabs } from "antd";
import { useEffect, useState } from "react";
import { useTemplateStore } from "../../stores/templateStore";
import { useDeviceStore } from "../../stores/deviceStore";

interface CreateDeviceModalProps {
  open: boolean;
  onClose: () => void;
}

export function CreateDeviceModal({ open, onClose }: CreateDeviceModalProps) {
  const [singleForm] = Form.useForm();
  const [batchForm] = Form.useForm();
  const [activeTab, setActiveTab] = useState("single");
  const { templates, fetchTemplates } = useTemplateStore();
  const { createDevice, batchCreateDevices, fetchDevices } = useDeviceStore();

  useEffect(() => {
    if (open) {
      fetchTemplates();
    }
  }, [open, fetchTemplates]);

  const templateOptions = templates.map((t) => ({
    value: t.id,
    label: `${t.name} (${t.register_count} registers)`,
  }));

  const handleSingleSubmit = async () => {
    const values = await singleForm.validateFields();
    const result = await createDevice(values);
    if (result) {
      singleForm.resetFields();
      await fetchDevices();
      onClose();
    }
  };

  const handleBatchSubmit = async () => {
    const values = await batchForm.validateFields();
    const success = await batchCreateDevices(values);
    if (success) {
      batchForm.resetFields();
      await fetchDevices();
      onClose();
    }
  };

  const handleOk = () => {
    if (activeTab === "single") {
      handleSingleSubmit();
    } else {
      handleBatchSubmit();
    }
  };

  return (
    <Modal
      title="Create Device"
      open={open}
      onOk={handleOk}
      onCancel={onClose}
      destroyOnClose
    >
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: "single",
            label: "Single",
            children: (
              <Form form={singleForm} layout="vertical">
                <Form.Item
                  name="template_id"
                  label="Template"
                  rules={[{ required: true }]}
                >
                  <Select options={templateOptions} placeholder="Select template" />
                </Form.Item>
                <Form.Item
                  name="name"
                  label="Device Name"
                  rules={[{ required: true }]}
                >
                  <Input />
                </Form.Item>
                <Form.Item
                  name="slave_id"
                  label="Slave ID"
                  rules={[{ required: true }]}
                >
                  <InputNumber min={1} max={247} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item name="description" label="Description">
                  <Input.TextArea rows={2} />
                </Form.Item>
              </Form>
            ),
          },
          {
            key: "batch",
            label: "Batch",
            children: (
              <Form form={batchForm} layout="vertical">
                <Form.Item
                  name="template_id"
                  label="Template"
                  rules={[{ required: true }]}
                >
                  <Select options={templateOptions} placeholder="Select template" />
                </Form.Item>
                <Form.Item
                  name="slave_id_start"
                  label="Slave ID Start"
                  rules={[{ required: true }]}
                >
                  <InputNumber min={1} max={247} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item
                  name="slave_id_end"
                  label="Slave ID End"
                  rules={[{ required: true }]}
                >
                  <InputNumber min={1} max={247} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item name="name_prefix" label="Name Prefix (optional)">
                  <Input placeholder="Leave empty to use template name" />
                </Form.Item>
                <Form.Item name="description" label="Description">
                  <Input.TextArea rows={2} />
                </Form.Item>
              </Form>
            ),
          },
        ]}
      />
    </Modal>
  );
}
```

- [ ] **Step 2: Create DeviceList**

Create `frontend/src/pages/Devices/DeviceList.tsx`:

```tsx
import {
  DeleteOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { Badge, Button, Popconfirm, Space, Table, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { DeviceSummary } from "../../types";
import { useDeviceStore } from "../../stores/deviceStore";
import { CreateDeviceModal } from "./CreateDeviceModal";

const STATUS_CONFIG: Record<string, { status: "success" | "default" | "error"; text: string }> = {
  running: { status: "success", text: "Running" },
  stopped: { status: "default", text: "Stopped" },
  error: { status: "error", text: "Error" },
};

export function DeviceList() {
  const navigate = useNavigate();
  const [modalOpen, setModalOpen] = useState(false);
  const {
    devices,
    loading,
    fetchDevices,
    deleteDevice,
    startDevice,
    stopDevice,
  } = useDeviceStore();

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  const handleToggle = async (device: DeviceSummary) => {
    let success: boolean;
    if (device.status === "running") {
      success = await stopDevice(device.id);
    } else {
      success = await startDevice(device.id);
    }
    if (success) {
      await fetchDevices();
    }
  };

  const handleDelete = async (id: string) => {
    const success = await deleteDevice(id);
    if (success) {
      await fetchDevices();
    }
  };

  const columns: ColumnsType<DeviceSummary> = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (name: string, record) => (
        <a onClick={() => navigate(`/devices/${record.id}`)}>{name}</a>
      ),
    },
    {
      title: "Slave ID",
      dataIndex: "slave_id",
      key: "slave_id",
      align: "center",
      width: 100,
    },
    {
      title: "Template",
      dataIndex: "template_name",
      key: "template_name",
    },
    {
      title: "Port",
      dataIndex: "port",
      key: "port",
      align: "center",
      width: 80,
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 120,
      render: (status: string) => {
        const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.stopped;
        return <Badge status={config.status} text={config.text} />;
      },
    },
    {
      title: "Actions",
      key: "actions",
      width: 120,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title={record.status === "running" ? "Stop" : "Start"}>
            <Button
              type="text"
              size="small"
              icon={
                record.status === "running" ? (
                  <PauseCircleOutlined />
                ) : (
                  <PlayCircleOutlined />
                )
              }
              onClick={() => handleToggle(record)}
              disabled={record.status === "error"}
            />
          </Tooltip>
          {record.status !== "running" && (
            <Popconfirm
              title="Delete this device?"
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
          justifyContent: "flex-end",
          marginBottom: 16,
        }}
      >
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setModalOpen(true)}
        >
          New Device
        </Button>
      </div>
      <Table
        columns={columns}
        dataSource={devices}
        rowKey="id"
        loading={loading}
        pagination={false}
      />
      <CreateDeviceModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
      />
    </div>
  );
}
```

- [ ] **Step 3: Update index.tsx**

Replace `frontend/src/pages/Devices/index.tsx`:

```tsx
import { Typography } from "antd";
import { DeviceList } from "./DeviceList";

export default function DevicesPage() {
  return (
    <div>
      <Typography.Title level={2}>Device Instances</Typography.Title>
      <DeviceList />
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Devices/
git commit -m "feat: add device list page with create modal"
```

---

### Task 13: Create Device Detail Page & Update Routes

**Files:**
- Create: `frontend/src/pages/Devices/DeviceDetail.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create DeviceDetail page**

Create `frontend/src/pages/Devices/DeviceDetail.tsx`:

```tsx
import { Badge, Button, Card, Descriptions, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { RegisterValue } from "../../types";
import { useDeviceStore } from "../../stores/deviceStore";

const STATUS_CONFIG: Record<string, { status: "success" | "default" | "error"; text: string }> = {
  running: { status: "success", text: "Running" },
  stopped: { status: "default", text: "Stopped" },
  error: { status: "error", text: "Error" },
};

const registerColumns: ColumnsType<RegisterValue> = [
  { title: "Name", dataIndex: "name", key: "name" },
  { title: "Address", dataIndex: "address", key: "address", align: "center" },
  {
    title: "FC",
    dataIndex: "function_code",
    key: "function_code",
    align: "center",
    render: (v: number) => `FC${String(v).padStart(2, "0")}`,
  },
  { title: "Data Type", dataIndex: "data_type", key: "data_type" },
  { title: "Byte Order", dataIndex: "byte_order", key: "byte_order" },
  {
    title: "Scale",
    dataIndex: "scale_factor",
    key: "scale_factor",
    align: "center",
  },
  { title: "Unit", dataIndex: "unit", key: "unit" },
  {
    title: "Value",
    dataIndex: "value",
    key: "value",
    align: "center",
    render: (v: number | null) => (v !== null ? v : "—"),
  },
];

export default function DeviceDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentDevice, loading, fetchDevice, clearCurrentDevice } =
    useDeviceStore();

  useEffect(() => {
    if (id) {
      fetchDevice(id);
    }
    return () => clearCurrentDevice();
  }, [id, fetchDevice, clearCurrentDevice]);

  if (!currentDevice && !loading) {
    return <Typography.Text>Device not found</Typography.Text>;
  }

  const statusConfig =
    STATUS_CONFIG[currentDevice?.status ?? "stopped"] ?? STATUS_CONFIG.stopped;

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button onClick={() => navigate("/devices")}>Back to List</Button>
      </Space>

      <Typography.Title level={2}>{currentDevice?.name}</Typography.Title>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={2}>
          <Descriptions.Item label="Slave ID">
            {currentDevice?.slave_id}
          </Descriptions.Item>
          <Descriptions.Item label="Template">
            {currentDevice?.template_name}
          </Descriptions.Item>
          <Descriptions.Item label="Port">
            {currentDevice?.port}
          </Descriptions.Item>
          <Descriptions.Item label="Status">
            <Badge status={statusConfig.status} text={statusConfig.text} />
          </Descriptions.Item>
          <Descriptions.Item label="Description" span={2}>
            {currentDevice?.description ?? "—"}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="Register Map">
        <Table
          columns={registerColumns}
          dataSource={currentDevice?.registers ?? []}
          rowKey="name"
          loading={loading}
          pagination={false}
          size="small"
        />
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Update App.tsx**

In `frontend/src/App.tsx`, add import:

```typescript
import DeviceDetail from "./pages/Devices/DeviceDetail";
```

Add route before the `/devices` route:

```tsx
<Route path="/devices/:id" element={<DeviceDetail />} />
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Devices/DeviceDetail.tsx frontend/src/App.tsx
git commit -m "feat: add device detail page with register list"
```

---

## Chunk 5: Documentation & Verification

### Task 14: Update Project Documentation

**Files:**
- Modify: `CHANGELOG.md`, `docs/database-schema.md`, `docs/api-reference.md`, `docs/development-phases.md`, `docs/development-log.md`

- [ ] **Step 1: Update all docs**

- CHANGELOG.md: Add Phase 3 items under `## [Unreleased]`
- database-schema.md: Add `device_instances` table
- api-reference.md: Add all `/api/v1/devices` endpoints
- development-phases.md: Mark Milestone 3.1 and 3.2 as `[x]`, Phase 3 status → `✅`
- development-log.md: Add Phase 3 entry

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md docs/
git commit -m "docs: update project docs for Phase 3 completion"
```

---

### Task 15: Full System Verification

- [ ] **Step 1: Run backend tests**

Run: `cd backend && POSTGRES_PORT=5434 python3.12 -m pytest -v`
Expected: All tests PASS.

- [ ] **Step 2: Run frontend build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.
