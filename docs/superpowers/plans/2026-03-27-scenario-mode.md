# Scenario Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a scenario system for coordinated multi-register anomaly sequences with visual timeline editor, reusable templates, and built-in presets.

**Architecture:** New `scenarios` + `scenario_steps` tables with CRUD API. In-memory `ScenarioRunner` drives timeline execution via existing `AnomalyInjector`. Frontend adds Scenarios page with drag-and-drop timeline editor plus execution card on Device Detail.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, React 18, TypeScript, Ant Design 5, Zustand

---

## File Structure

### Backend — New Files
- `backend/app/models/scenario.py` — Scenario + ScenarioStep ORM models
- `backend/app/schemas/scenario.py` — Pydantic request/response schemas
- `backend/app/services/scenario_service.py` — CRUD + validation logic
- `backend/app/services/scenario_runner.py` — In-memory executor (asyncio)
- `backend/app/api/routes/scenarios.py` — CRUD + execution API routes
- `backend/app/seed/scenarios/` — Directory for built-in scenario JSON files
- `backend/app/seed/scenarios/three_phase_power_outage.json`
- `backend/app/seed/scenarios/three_phase_voltage_instability.json`
- `backend/app/seed/scenarios/solar_inverter_fault.json`
- `backend/tests/test_scenarios.py` — Scenario CRUD + execution tests

### Backend — Modified Files
- `backend/app/main.py` — Register scenario routes, seed scenarios, init runner
- `backend/app/seed/loader.py` — Add `seed_builtin_scenarios()`
- `backend/app/services/device_service.py` — Stop scenario on device stop
- `backend/tests/conftest.py` — Add scenario tables to TRUNCATE

### Frontend — New Files
- `frontend/src/types/scenario.ts` — TypeScript interfaces
- `frontend/src/services/scenarioApi.ts` — API client
- `frontend/src/stores/scenarioStore.ts` — Zustand store
- `frontend/src/pages/Scenarios/index.tsx` — Page entry (re-exports ScenarioList)
- `frontend/src/pages/Scenarios/ScenarioList.tsx` — List page
- `frontend/src/pages/Scenarios/ScenarioEditor.tsx` — Editor page
- `frontend/src/pages/Scenarios/TimelineEditor.tsx` — Timeline visualization
- `frontend/src/pages/Scenarios/TimelineBlock.tsx` — Draggable step block
- `frontend/src/pages/Scenarios/StepPopover.tsx` — Step edit popover
- `frontend/src/pages/Devices/ScenarioCard.tsx` — Execution card

### Frontend — Modified Files
- `frontend/src/App.tsx` — Add scenario routes
- `frontend/src/layouts/MainLayout.tsx` — Add Scenarios sidebar item

---

### Task 1: DB Models + Migration

**Files:**
- Create: `backend/app/models/scenario.py`
- Modify: `backend/tests/conftest.py:41-45`

- [ ] **Step 1: Create Scenario and ScenarioStep ORM models**

Create `backend/app/models/scenario.py`:

```python
"""ORM models for scenario system."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Scenario(Base):
    """A reusable scenario definition bound to a device template."""

    __tablename__ = "scenarios"
    __table_args__ = (
        UniqueConstraint("template_id", "name", name="uq_scenario_template_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_templates.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    total_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    steps: Mapped[list["ScenarioStep"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan",
        order_by="ScenarioStep.sort_order",
    )


class ScenarioStep(Base):
    """A single anomaly step within a scenario timeline."""

    __tablename__ = "scenario_steps"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    register_name: Mapped[str] = mapped_column(String(100), nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(50), nullable=False)
    anomaly_params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    trigger_at_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    scenario: Mapped["Scenario"] = relationship(back_populates="steps")
```

- [ ] **Step 2: Create Alembic migration**

Run: `cd backend && alembic revision --autogenerate -m "add scenarios and scenario_steps tables"`

Then: `cd backend && alembic upgrade head`

- [ ] **Step 3: Update test conftest to truncate new tables**

In `backend/tests/conftest.py`, update the TRUNCATE statement to include `scenarios, scenario_steps`:

```python
        await conn.execute(text(
            "TRUNCATE device_templates, register_definitions, device_instances, "
            "simulation_configs, anomaly_schedules, simulation_profiles, "
            "mqtt_broker_settings, mqtt_publish_configs, "
            "scenarios, scenario_steps CASCADE"
        ))
```

- [ ] **Step 4: Verify migration works**

Run: `cd backend && python -c "from app.models.scenario import Scenario, ScenarioStep; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/scenario.py backend/alembic/versions/ backend/tests/conftest.py
git commit -m "feat: add scenarios and scenario_steps DB models and migration"
```

---

### Task 2: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/scenario.py`

- [ ] **Step 1: Create scenario schemas**

Create `backend/app/schemas/scenario.py`:

```python
"""Pydantic schemas for scenario system."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


VALID_ANOMALY_TYPES = {"spike", "drift", "flatline", "out_of_range", "data_loss"}


class ScenarioStepCreate(BaseModel):
    """Schema for creating/updating a scenario step."""

    register_name: str
    anomaly_type: str
    anomaly_params: dict = {}
    trigger_at_seconds: int
    duration_seconds: int
    sort_order: int = 0

    @field_validator("anomaly_type")
    @classmethod
    def validate_anomaly_type(cls, v: str) -> str:
        if v not in VALID_ANOMALY_TYPES:
            raise ValueError(f"Invalid anomaly type: {v}. Must be one of {VALID_ANOMALY_TYPES}")
        return v

    @field_validator("trigger_at_seconds")
    @classmethod
    def validate_trigger_at(cls, v: int) -> int:
        if v < 0:
            raise ValueError("trigger_at_seconds must be >= 0")
        return v

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("duration_seconds must be > 0")
        return v


class ScenarioCreate(BaseModel):
    """Schema for creating a scenario."""

    template_id: UUID
    name: str
    description: str | None = None
    steps: list[ScenarioStepCreate]


class ScenarioUpdate(BaseModel):
    """Schema for updating a scenario (full replace of steps)."""

    name: str
    description: str | None = None
    steps: list[ScenarioStepCreate]


class ScenarioStepResponse(BaseModel):
    """Schema for a step in responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    register_name: str
    anomaly_type: str
    anomaly_params: dict
    trigger_at_seconds: int
    duration_seconds: int
    sort_order: int


class ScenarioSummary(BaseModel):
    """Schema for scenario list items."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    template_name: str
    name: str
    description: str | None
    is_builtin: bool
    total_duration_seconds: int
    created_at: datetime
    updated_at: datetime


class ScenarioDetail(ScenarioSummary):
    """Schema for scenario with steps."""

    steps: list[ScenarioStepResponse]


class ScenarioExport(BaseModel):
    """Schema for JSON export/import."""

    name: str
    description: str | None = None
    template_name: str
    steps: list[ScenarioStepCreate]


class ActiveStepStatus(BaseModel):
    """Status of a currently active step during execution."""

    register_name: str
    anomaly_type: str
    remaining_seconds: int


class ScenarioExecutionStatus(BaseModel):
    """Status of a running scenario on a device."""

    scenario_id: UUID
    scenario_name: str
    status: str  # "running" | "completed"
    elapsed_seconds: int
    total_duration_seconds: int
    active_steps: list[ActiveStepStatus]
```

- [ ] **Step 2: Verify import**

Run: `cd backend && python -c "from app.schemas.scenario import ScenarioCreate, ScenarioDetail, ScenarioExecutionStatus; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/scenario.py
git commit -m "feat: add scenario Pydantic schemas"
```

---

### Task 3: Scenario CRUD Service

**Files:**
- Create: `backend/app/services/scenario_service.py`
- Test: `backend/tests/test_scenarios.py`

- [ ] **Step 1: Write CRUD tests**

Create `backend/tests/test_scenarios.py`:

```python
"""Tests for scenario CRUD and execution."""

from httpx import AsyncClient

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


async def create_template(client: AsyncClient) -> dict:
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["data"]


def make_scenario_payload(template_id: str) -> dict:
    return {
        "template_id": template_id,
        "name": "Test Scenario",
        "description": "A test scenario",
        "steps": [
            {
                "register_name": "voltage",
                "anomaly_type": "out_of_range",
                "anomaly_params": {"value": 0},
                "trigger_at_seconds": 0,
                "duration_seconds": 10,
                "sort_order": 0,
            },
            {
                "register_name": "current",
                "anomaly_type": "flatline",
                "anomaly_params": {"value": 0},
                "trigger_at_seconds": 5,
                "duration_seconds": 10,
                "sort_order": 1,
            },
        ],
    }


class TestScenarioCRUD:
    async def test_create_scenario(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        resp = await client.post("/api/v1/scenarios", json=payload)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Test Scenario"
        assert data["total_duration_seconds"] == 15  # max(0+10, 5+10)
        assert len(data["steps"]) == 2

    async def test_list_scenarios(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        await client.post("/api/v1/scenarios", json=payload)
        resp = await client.get("/api/v1/scenarios")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    async def test_list_scenarios_filter_by_template(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        await client.post("/api/v1/scenarios", json=payload)
        resp = await client.get(f"/api/v1/scenarios?template_id={template['id']}")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1
        # Non-existent template returns empty
        resp2 = await client.get("/api/v1/scenarios?template_id=00000000-0000-0000-0000-000000000000")
        assert resp2.status_code == 200
        assert len(resp2.json()["data"]) == 0

    async def test_get_scenario_detail(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        create_resp = await client.post("/api/v1/scenarios", json=payload)
        scenario_id = create_resp.json()["data"]["id"]
        resp = await client.get(f"/api/v1/scenarios/{scenario_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Test Scenario"
        assert len(data["steps"]) == 2

    async def test_update_scenario(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        create_resp = await client.post("/api/v1/scenarios", json=payload)
        scenario_id = create_resp.json()["data"]["id"]
        update_payload = {
            "name": "Updated Scenario",
            "description": "Updated",
            "steps": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "spike",
                    "anomaly_params": {"probability": 0.8, "multiplier": 1.5},
                    "trigger_at_seconds": 0,
                    "duration_seconds": 20,
                    "sort_order": 0,
                },
            ],
        }
        resp = await client.put(f"/api/v1/scenarios/{scenario_id}", json=update_payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Updated Scenario"
        assert data["total_duration_seconds"] == 20
        assert len(data["steps"]) == 1

    async def test_delete_scenario(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        create_resp = await client.post("/api/v1/scenarios", json=payload)
        scenario_id = create_resp.json()["data"]["id"]
        resp = await client.delete(f"/api/v1/scenarios/{scenario_id}")
        assert resp.status_code == 200
        # Verify gone
        resp2 = await client.get(f"/api/v1/scenarios/{scenario_id}")
        assert resp2.status_code == 404

    async def test_invalid_register_name_rejected(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = {
            "template_id": template["id"],
            "name": "Bad Scenario",
            "steps": [
                {
                    "register_name": "nonexistent_register",
                    "anomaly_type": "spike",
                    "anomaly_params": {},
                    "trigger_at_seconds": 0,
                    "duration_seconds": 10,
                },
            ],
        }
        resp = await client.post("/api/v1/scenarios", json=payload)
        assert resp.status_code == 422

    async def test_overlapping_steps_rejected(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = {
            "template_id": template["id"],
            "name": "Overlap Scenario",
            "steps": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "spike",
                    "anomaly_params": {},
                    "trigger_at_seconds": 0,
                    "duration_seconds": 20,
                },
                {
                    "register_name": "voltage",
                    "anomaly_type": "drift",
                    "anomaly_params": {},
                    "trigger_at_seconds": 10,
                    "duration_seconds": 15,
                },
            ],
        }
        resp = await client.post("/api/v1/scenarios", json=payload)
        assert resp.status_code == 422

    async def test_export_scenario(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        create_resp = await client.post("/api/v1/scenarios", json=payload)
        scenario_id = create_resp.json()["data"]["id"]
        resp = await client.post(f"/api/v1/scenarios/{scenario_id}/export")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Test Scenario"
        assert data["template_name"] == "Test Meter"
        assert len(data["steps"]) == 2

    async def test_import_scenario(self, client: AsyncClient) -> None:
        template = await create_template(client)
        import_payload = {
            "name": "Imported Scenario",
            "template_name": "Test Meter",
            "steps": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "out_of_range",
                    "anomaly_params": {"value": 0},
                    "trigger_at_seconds": 0,
                    "duration_seconds": 10,
                },
            ],
        }
        resp = await client.post("/api/v1/scenarios/import", json=import_payload)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Imported Scenario"
        assert data["template_id"] == template["id"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_scenarios.py -v --no-header -q 2>&1 | head -20`
Expected: FAIL (no routes registered)

- [ ] **Step 3: Create scenario service**

Create `backend/app/services/scenario_service.py`:

```python
"""Scenario CRUD service layer."""

import logging
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.scenario import Scenario, ScenarioStep
from app.models.template import DeviceTemplate
from app.schemas.scenario import ScenarioCreate, ScenarioExport, ScenarioStepCreate, ScenarioUpdate

logger = logging.getLogger(__name__)


async def _get_template_or_404(
    session: AsyncSession, template_id: uuid.UUID,
) -> DeviceTemplate:
    """Get template with registers or raise 404."""
    stmt = (
        select(DeviceTemplate)
        .options(selectinload(DeviceTemplate.registers))
        .where(DeviceTemplate.id == template_id)
    )
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundException(detail="Template not found", error_code="TEMPLATE_NOT_FOUND")
    return template


async def _get_scenario_or_404(
    session: AsyncSession, scenario_id: uuid.UUID,
) -> Scenario:
    """Get scenario with steps or raise 404."""
    stmt = (
        select(Scenario)
        .options(selectinload(Scenario.steps))
        .where(Scenario.id == scenario_id)
    )
    result = await session.execute(stmt)
    scenario = result.scalar_one_or_none()
    if scenario is None:
        raise NotFoundException(detail="Scenario not found", error_code="SCENARIO_NOT_FOUND")
    return scenario


def _validate_steps(
    steps: list[ScenarioStepCreate],
    register_names: set[str],
) -> None:
    """Validate register names exist and no time overlaps per register."""
    for step in steps:
        if step.register_name not in register_names:
            raise ValidationException(
                f"Register '{step.register_name}' not found in template"
            )

    # Check time overlaps per register
    by_register: dict[str, list[ScenarioStepCreate]] = defaultdict(list)
    for step in steps:
        by_register[step.register_name].append(step)

    for reg_name, reg_steps in by_register.items():
        sorted_steps = sorted(reg_steps, key=lambda s: s.trigger_at_seconds)
        for i in range(len(sorted_steps) - 1):
            end_a = sorted_steps[i].trigger_at_seconds + sorted_steps[i].duration_seconds
            start_b = sorted_steps[i + 1].trigger_at_seconds
            if end_a > start_b:
                raise ValidationException(
                    f"Overlapping steps on register '{reg_name}': "
                    f"step ending at {end_a}s overlaps step starting at {start_b}s"
                )


def _compute_total_duration(steps: list[ScenarioStepCreate]) -> int:
    """Compute total scenario duration from steps."""
    if not steps:
        return 0
    return max(s.trigger_at_seconds + s.duration_seconds for s in steps)


def _scenario_to_summary(scenario: Scenario, template_name: str) -> dict:
    """Convert scenario ORM to summary dict."""
    return {
        "id": scenario.id,
        "template_id": scenario.template_id,
        "template_name": template_name,
        "name": scenario.name,
        "description": scenario.description,
        "is_builtin": scenario.is_builtin,
        "total_duration_seconds": scenario.total_duration_seconds,
        "created_at": scenario.created_at,
        "updated_at": scenario.updated_at,
    }


def _scenario_to_detail(scenario: Scenario, template_name: str) -> dict:
    """Convert scenario ORM to detail dict with steps."""
    result = _scenario_to_summary(scenario, template_name)
    result["steps"] = [
        {
            "id": step.id,
            "register_name": step.register_name,
            "anomaly_type": step.anomaly_type,
            "anomaly_params": step.anomaly_params,
            "trigger_at_seconds": step.trigger_at_seconds,
            "duration_seconds": step.duration_seconds,
            "sort_order": step.sort_order,
        }
        for step in scenario.steps
    ]
    return result


async def list_scenarios(
    session: AsyncSession,
    template_id: uuid.UUID | None = None,
) -> list[dict]:
    """List scenarios with optional template filter."""
    stmt = (
        select(Scenario, DeviceTemplate.name.label("template_name"))
        .join(DeviceTemplate, Scenario.template_id == DeviceTemplate.id)
        .order_by(Scenario.created_at)
    )
    if template_id is not None:
        stmt = stmt.where(Scenario.template_id == template_id)
    result = await session.execute(stmt)
    return [_scenario_to_summary(row.Scenario, row.template_name) for row in result.all()]


async def get_scenario(session: AsyncSession, scenario_id: uuid.UUID) -> dict:
    """Get scenario detail with steps."""
    scenario = await _get_scenario_or_404(session, scenario_id)
    template = await _get_template_or_404(session, scenario.template_id)
    return _scenario_to_detail(scenario, template.name)


async def create_scenario(
    session: AsyncSession, data: ScenarioCreate, is_builtin: bool = False,
) -> dict:
    """Create a new scenario with steps."""
    template = await _get_template_or_404(session, data.template_id)
    register_names = {r.name for r in template.registers}
    _validate_steps(data.steps, register_names)

    scenario = Scenario(
        template_id=data.template_id,
        name=data.name,
        description=data.description,
        is_builtin=is_builtin,
        total_duration_seconds=_compute_total_duration(data.steps),
    )
    session.add(scenario)
    await session.flush()

    for step_data in data.steps:
        step = ScenarioStep(
            scenario_id=scenario.id,
            register_name=step_data.register_name,
            anomaly_type=step_data.anomaly_type,
            anomaly_params=step_data.anomaly_params,
            trigger_at_seconds=step_data.trigger_at_seconds,
            duration_seconds=step_data.duration_seconds,
            sort_order=step_data.sort_order,
        )
        session.add(step)

    await session.commit()
    await session.refresh(scenario, ["steps"])
    return _scenario_to_detail(scenario, template.name)


async def update_scenario(
    session: AsyncSession, scenario_id: uuid.UUID, data: ScenarioUpdate,
) -> dict:
    """Update scenario (full replace of steps)."""
    scenario = await _get_scenario_or_404(session, scenario_id)
    if scenario.is_builtin:
        raise ConflictException(
            detail="Built-in scenarios cannot be modified",
            error_code="BUILTIN_PROTECTED",
        )

    template = await _get_template_or_404(session, scenario.template_id)
    register_names = {r.name for r in template.registers}
    _validate_steps(data.steps, register_names)

    scenario.name = data.name
    scenario.description = data.description
    scenario.total_duration_seconds = _compute_total_duration(data.steps)

    # Delete old steps
    for step in list(scenario.steps):
        await session.delete(step)
    await session.flush()

    # Create new steps
    for step_data in data.steps:
        step = ScenarioStep(
            scenario_id=scenario.id,
            register_name=step_data.register_name,
            anomaly_type=step_data.anomaly_type,
            anomaly_params=step_data.anomaly_params,
            trigger_at_seconds=step_data.trigger_at_seconds,
            duration_seconds=step_data.duration_seconds,
            sort_order=step_data.sort_order,
        )
        session.add(step)

    await session.commit()
    await session.refresh(scenario, ["steps"])
    return _scenario_to_detail(scenario, template.name)


async def delete_scenario(session: AsyncSession, scenario_id: uuid.UUID) -> None:
    """Delete a scenario."""
    scenario = await _get_scenario_or_404(session, scenario_id)
    if scenario.is_builtin:
        raise ConflictException(
            detail="Built-in scenarios cannot be deleted",
            error_code="BUILTIN_PROTECTED",
        )
    await session.delete(scenario)
    await session.commit()


async def export_scenario(session: AsyncSession, scenario_id: uuid.UUID) -> dict:
    """Export scenario as portable JSON."""
    scenario = await _get_scenario_or_404(session, scenario_id)
    template = await _get_template_or_404(session, scenario.template_id)
    return {
        "name": scenario.name,
        "description": scenario.description,
        "template_name": template.name,
        "steps": [
            {
                "register_name": step.register_name,
                "anomaly_type": step.anomaly_type,
                "anomaly_params": step.anomaly_params,
                "trigger_at_seconds": step.trigger_at_seconds,
                "duration_seconds": step.duration_seconds,
                "sort_order": step.sort_order,
            }
            for step in scenario.steps
        ],
    }


async def import_scenario(session: AsyncSession, data: ScenarioExport) -> dict:
    """Import scenario from JSON, resolving template_name to template_id."""
    stmt = select(DeviceTemplate).where(DeviceTemplate.name == data.template_name)
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundException(
            detail=f"Template '{data.template_name}' not found",
            error_code="TEMPLATE_NOT_FOUND",
        )

    create_data = ScenarioCreate(
        template_id=template.id,
        name=data.name,
        description=data.description,
        steps=data.steps,
    )
    return await create_scenario(session, create_data)
```

- [ ] **Step 4: Create API routes**

Create `backend/app/api/routes/scenarios.py`:

```python
"""API routes for scenario management."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiResponse
from app.schemas.scenario import (
    ScenarioCreate,
    ScenarioDetail,
    ScenarioExport,
    ScenarioSummary,
    ScenarioUpdate,
)
from app.services import scenario_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[ScenarioSummary]])
async def list_scenarios(
    template_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[ScenarioSummary]]:
    """List all scenarios, optionally filtered by template."""
    scenarios = await scenario_service.list_scenarios(session, template_id)
    return ApiResponse(data=[ScenarioSummary(**s) for s in scenarios])


@router.get("/{scenario_id}", response_model=ApiResponse[ScenarioDetail])
async def get_scenario(
    scenario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ScenarioDetail]:
    """Get scenario with all steps."""
    scenario = await scenario_service.get_scenario(session, scenario_id)
    return ApiResponse(data=ScenarioDetail(**scenario))


@router.post("", response_model=ApiResponse[ScenarioDetail], status_code=201)
async def create_scenario(
    data: ScenarioCreate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ScenarioDetail]:
    """Create a new scenario with steps."""
    scenario = await scenario_service.create_scenario(session, data)
    return ApiResponse(data=ScenarioDetail(**scenario))


@router.put("/{scenario_id}", response_model=ApiResponse[ScenarioDetail])
async def update_scenario(
    scenario_id: uuid.UUID,
    data: ScenarioUpdate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ScenarioDetail]:
    """Update scenario (full replace of steps)."""
    scenario = await scenario_service.update_scenario(session, scenario_id, data)
    return ApiResponse(data=ScenarioDetail(**scenario))


@router.delete("/{scenario_id}", response_model=ApiResponse[None])
async def delete_scenario(
    scenario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete a scenario (403 for built-in)."""
    await scenario_service.delete_scenario(session, scenario_id)
    return ApiResponse(data=None, message="Scenario deleted")


@router.post("/{scenario_id}/export", response_model=ApiResponse[ScenarioExport])
async def export_scenario(
    scenario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ScenarioExport]:
    """Export scenario as portable JSON."""
    data = await scenario_service.export_scenario(session, scenario_id)
    return ApiResponse(data=ScenarioExport(**data))


@router.post("/import", response_model=ApiResponse[ScenarioDetail], status_code=201)
async def import_scenario(
    data: ScenarioExport,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ScenarioDetail]:
    """Import scenario from JSON."""
    scenario = await scenario_service.import_scenario(session, data)
    return ApiResponse(data=ScenarioDetail(**scenario))
```

- [ ] **Step 5: Register routes in main.py**

In `backend/app/main.py`, add import and route registration:

Add to imports:
```python
from app.api.routes.scenarios import router as scenarios_router
```

Add to API router section (after the mqtt_router line):
```python
api_v1_router.include_router(scenarios_router, prefix="/scenarios", tags=["scenarios"])
```

- [ ] **Step 6: Run tests**

Run: `cd backend && python -m pytest tests/test_scenarios.py -v`
Expected: All 10 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/scenario_service.py backend/app/api/routes/scenarios.py backend/app/main.py backend/tests/test_scenarios.py
git commit -m "feat: add scenario CRUD service and API routes"
```

---

### Task 4: ScenarioRunner (In-Memory Executor)

**Files:**
- Create: `backend/app/services/scenario_runner.py`
- Modify: `backend/app/api/routes/scenarios.py` (add execution endpoints)
- Modify: `backend/app/services/device_service.py` (stop scenario on device stop)
- Test: `backend/tests/test_scenarios.py` (add execution tests)

- [ ] **Step 1: Write execution tests**

Add to `backend/tests/test_scenarios.py`:

```python
import asyncio


async def create_device(client: AsyncClient, template_id: str, name: str = "Test Device", slave_id: int = 1) -> dict:
    resp = await client.post("/api/v1/devices", json={
        "template_id": template_id,
        "name": name,
        "slave_id": slave_id,
    })
    assert resp.status_code == 201
    return resp.json()["data"]


class TestScenarioExecution:
    async def test_start_scenario_requires_running_device(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        payload = make_scenario_payload(template["id"])
        create_resp = await client.post("/api/v1/scenarios", json=payload)
        scenario_id = create_resp.json()["data"]["id"]

        # Device is stopped — should fail
        resp = await client.post(f"/api/v1/devices/{device['id']}/scenario/{scenario_id}/start")
        assert resp.status_code == 409

    async def test_start_scenario_template_mismatch_rejected(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])

        # Create another template
        other_template_payload = {**TEMPLATE_PAYLOAD, "name": "Other Meter"}
        other_resp = await client.post("/api/v1/templates", json=other_template_payload)
        other_template_id = other_resp.json()["data"]["id"]

        # Scenario bound to other template
        payload = make_scenario_payload(other_template_id)
        create_resp = await client.post("/api/v1/scenarios", json=payload)
        scenario_id = create_resp.json()["data"]["id"]

        resp = await client.post(f"/api/v1/devices/{device['id']}/scenario/{scenario_id}/start")
        assert resp.status_code == 409

    async def test_get_status_no_scenario_returns_404(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        resp = await client.get(f"/api/v1/devices/{device['id']}/scenario/status")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_scenarios.py::TestScenarioExecution -v --no-header -q 2>&1 | head -15`
Expected: FAIL (no execution endpoints)

- [ ] **Step 3: Create ScenarioRunner**

Create `backend/app/services/scenario_runner.py`:

```python
"""In-memory scenario executor — drives timeline via AnomalyInjector."""

import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

from app.simulation.anomaly_injector import AnomalyInjector

logger = logging.getLogger(__name__)


@dataclass
class StepInfo:
    """Immutable step info for the runner."""

    register_name: str
    anomaly_type: str
    anomaly_params: dict
    trigger_at_seconds: int
    duration_seconds: int


@dataclass
class RunningScenario:
    """State of a currently running scenario on a device."""

    scenario_id: UUID
    scenario_name: str
    total_duration_seconds: int
    steps: list[StepInfo]
    started_at: float = 0.0
    status: str = "running"
    active_anomalies: set[str] = field(default_factory=set)
    task: asyncio.Task | None = None


class ScenarioRunner:
    """Manages scenario execution across devices."""

    def __init__(self, anomaly_injector: AnomalyInjector) -> None:
        self._running: dict[UUID, RunningScenario] = {}
        self._injector = anomaly_injector

    async def start(
        self,
        device_id: UUID,
        scenario_id: UUID,
        scenario_name: str,
        total_duration_seconds: int,
        steps: list[StepInfo],
    ) -> None:
        """Start executing a scenario on a device."""
        if device_id in self._running:
            raise RuntimeError(f"Device {device_id} already has a running scenario")

        loop = asyncio.get_event_loop()
        running = RunningScenario(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            total_duration_seconds=total_duration_seconds,
            steps=steps,
            started_at=loop.time(),
        )
        self._running[device_id] = running
        running.task = asyncio.create_task(self._drive_timeline(device_id, running))
        logger.info(
            "Scenario '%s' started on device %s (%d steps, %ds total)",
            scenario_name, device_id, len(steps), total_duration_seconds,
        )

    async def stop(self, device_id: UUID) -> None:
        """Stop a running scenario and clear all injected anomalies."""
        running = self._running.pop(device_id, None)
        if running is None:
            return
        if running.task and not running.task.done():
            running.task.cancel()
            try:
                await running.task
            except asyncio.CancelledError:
                pass
        # Clear all anomalies injected by this scenario
        for register_name in list(running.active_anomalies):
            self._injector.remove(device_id, register_name)
        running.active_anomalies.clear()
        running.status = "completed"
        logger.info("Scenario '%s' stopped on device %s", running.scenario_name, device_id)

    def get_status(self, device_id: UUID) -> dict | None:
        """Get execution status for a device. Returns None if no scenario running."""
        running = self._running.get(device_id)
        if running is None:
            return None

        loop = asyncio.get_event_loop()
        elapsed = int(loop.time() - running.started_at)

        active_steps = []
        for step in running.steps:
            end_at = step.trigger_at_seconds + step.duration_seconds
            if step.trigger_at_seconds <= elapsed < end_at:
                active_steps.append({
                    "register_name": step.register_name,
                    "anomaly_type": step.anomaly_type,
                    "remaining_seconds": max(0, end_at - elapsed),
                })

        return {
            "scenario_id": running.scenario_id,
            "scenario_name": running.scenario_name,
            "status": running.status,
            "elapsed_seconds": min(elapsed, running.total_duration_seconds),
            "total_duration_seconds": running.total_duration_seconds,
            "active_steps": active_steps,
        }

    async def _drive_timeline(self, device_id: UUID, running: RunningScenario) -> None:
        """Asyncio task that drives scenario execution."""
        loop = asyncio.get_event_loop()
        triggered: set[int] = set()  # indices of steps already triggered

        try:
            while True:
                elapsed = loop.time() - running.started_at

                # Activate steps that should start
                for i, step in enumerate(running.steps):
                    if i not in triggered and elapsed >= step.trigger_at_seconds:
                        self._injector.inject(
                            device_id, step.register_name,
                            step.anomaly_type, step.anomaly_params,
                        )
                        running.active_anomalies.add(step.register_name)
                        triggered.add(i)

                # Deactivate steps that should end
                for i, step in enumerate(running.steps):
                    end_at = step.trigger_at_seconds + step.duration_seconds
                    if i in triggered and elapsed >= end_at and step.register_name in running.active_anomalies:
                        self._injector.remove(device_id, step.register_name)
                        running.active_anomalies.discard(step.register_name)

                # Check if scenario is complete
                if elapsed >= running.total_duration_seconds and not running.active_anomalies:
                    running.status = "completed"
                    self._running.pop(device_id, None)
                    logger.info("Scenario '%s' completed on device %s", running.scenario_name, device_id)
                    break

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            pass  # Cleanup handled by stop()
```

- [ ] **Step 4: Add execution endpoints to routes**

In `backend/app/api/routes/scenarios.py`, add at the top of the file (imports):

```python
from app.schemas.scenario import ScenarioExecutionStatus
from app.services.scenario_runner import ScenarioRunner, StepInfo
from app.simulation import anomaly_injector
```

Add a module-level runner instance (after the `router = APIRouter()` line):

```python
# Execution routes use a separate router mounted under /devices
execution_router = APIRouter()

# Singleton runner — initialized with the global anomaly_injector
runner = ScenarioRunner(anomaly_injector)
```

Add execution endpoints:

```python
@execution_router.post("/{device_id}/scenario/{scenario_id}/start", response_model=ApiResponse[None])
async def start_scenario(
    device_id: uuid.UUID,
    scenario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Start executing a scenario on a device."""
    from app.services import device_service

    # Verify device is running
    device = await device_service.get_device(session, device_id)
    if device["status"] != "running":
        from app.exceptions import ConflictException
        raise ConflictException(
            detail="Device must be running to start a scenario",
            error_code="DEVICE_NOT_RUNNING",
        )

    # Check no scenario already running
    if runner.get_status(device_id) is not None:
        from app.exceptions import ConflictException
        raise ConflictException(
            detail="A scenario is already running on this device",
            error_code="SCENARIO_ALREADY_RUNNING",
        )

    # Get scenario and validate template match
    scenario = await scenario_service.get_scenario(session, scenario_id)
    if scenario["template_id"] != device["template_id"]:
        from app.exceptions import ConflictException
        raise ConflictException(
            detail="Scenario template does not match device template",
            error_code="TEMPLATE_MISMATCH",
        )

    steps = [
        StepInfo(
            register_name=s["register_name"],
            anomaly_type=s["anomaly_type"],
            anomaly_params=s["anomaly_params"],
            trigger_at_seconds=s["trigger_at_seconds"],
            duration_seconds=s["duration_seconds"],
        )
        for s in scenario["steps"]
    ]

    await runner.start(
        device_id, scenario_id,
        scenario["name"], scenario["total_duration_seconds"], steps,
    )
    return ApiResponse(data=None, message="Scenario started")


@execution_router.post("/{device_id}/scenario/stop", response_model=ApiResponse[None])
async def stop_scenario(device_id: uuid.UUID) -> ApiResponse[None]:
    """Stop a running scenario on a device."""
    await runner.stop(device_id)
    return ApiResponse(data=None, message="Scenario stopped")


@execution_router.get("/{device_id}/scenario/status", response_model=ApiResponse[ScenarioExecutionStatus])
async def get_scenario_status(device_id: uuid.UUID) -> ApiResponse[ScenarioExecutionStatus]:
    """Get scenario execution status for a device."""
    status = runner.get_status(device_id)
    if status is None:
        from app.exceptions import NotFoundException
        raise NotFoundException(
            detail="No scenario running on this device",
            error_code="NO_RUNNING_SCENARIO",
        )
    return ApiResponse(data=ScenarioExecutionStatus(**status))
```

- [ ] **Step 5: Register execution router in main.py**

In `backend/app/main.py`, add import:

```python
from app.api.routes.scenarios import execution_router as scenario_execution_router
```

Add route registration (after the scenarios_router line):

```python
api_v1_router.include_router(scenario_execution_router, prefix="/devices", tags=["scenario-execution"])
```

- [ ] **Step 6: Stop scenario on device stop**

In `backend/app/services/device_service.py`, in the `stop_device` function, add scenario stop after the MQTT stop block (around line 430):

```python
    # Stop scenario if running (best-effort)
    try:
        from app.api.routes.scenarios import runner as scenario_runner
        await scenario_runner.stop(device.id)
    except Exception:
        pass
```

- [ ] **Step 7: Run tests**

Run: `cd backend && python -m pytest tests/test_scenarios.py -v`
Expected: All 13 tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/scenario_runner.py backend/app/api/routes/scenarios.py backend/app/main.py backend/app/services/device_service.py backend/tests/test_scenarios.py
git commit -m "feat: add ScenarioRunner and execution API endpoints"
```

---

### Task 5: Seed Built-in Scenarios

**Files:**
- Create: `backend/app/seed/scenarios/three_phase_power_outage.json`
- Create: `backend/app/seed/scenarios/three_phase_voltage_instability.json`
- Create: `backend/app/seed/scenarios/solar_inverter_fault.json`
- Modify: `backend/app/seed/loader.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create seed JSON files**

Create `backend/app/seed/scenarios/three_phase_power_outage.json`:

```json
{
  "template_name": "Three-Phase Power Meter (SDM630)",
  "name": "Power Outage",
  "description": "Simulates complete power loss: voltages drop to zero, followed by currents and power",
  "steps": [
    {"register_name": "voltage_l1", "anomaly_type": "out_of_range", "anomaly_params": {"value": 0}, "trigger_at_seconds": 0, "duration_seconds": 30, "sort_order": 0},
    {"register_name": "voltage_l2", "anomaly_type": "out_of_range", "anomaly_params": {"value": 0}, "trigger_at_seconds": 0, "duration_seconds": 30, "sort_order": 1},
    {"register_name": "voltage_l3", "anomaly_type": "out_of_range", "anomaly_params": {"value": 0}, "trigger_at_seconds": 0, "duration_seconds": 30, "sort_order": 2},
    {"register_name": "current_l1", "anomaly_type": "out_of_range", "anomaly_params": {"value": 0}, "trigger_at_seconds": 2, "duration_seconds": 28, "sort_order": 3},
    {"register_name": "current_l2", "anomaly_type": "out_of_range", "anomaly_params": {"value": 0}, "trigger_at_seconds": 2, "duration_seconds": 28, "sort_order": 4},
    {"register_name": "current_l3", "anomaly_type": "out_of_range", "anomaly_params": {"value": 0}, "trigger_at_seconds": 2, "duration_seconds": 28, "sort_order": 5},
    {"register_name": "total_power", "anomaly_type": "out_of_range", "anomaly_params": {"value": 0}, "trigger_at_seconds": 3, "duration_seconds": 27, "sort_order": 6}
  ]
}
```

Create `backend/app/seed/scenarios/three_phase_voltage_instability.json`:

```json
{
  "template_name": "Three-Phase Power Meter (SDM630)",
  "name": "Voltage Instability",
  "description": "Simulates unstable voltage across three phases with spikes and drift",
  "steps": [
    {"register_name": "voltage_l1", "anomaly_type": "spike", "anomaly_params": {"probability": 0.8, "multiplier": 1.5}, "trigger_at_seconds": 0, "duration_seconds": 15, "sort_order": 0},
    {"register_name": "voltage_l2", "anomaly_type": "drift", "anomaly_params": {"drift_per_second": 2, "max_drift": 30}, "trigger_at_seconds": 5, "duration_seconds": 20, "sort_order": 1},
    {"register_name": "voltage_l3", "anomaly_type": "spike", "anomaly_params": {"probability": 0.6, "multiplier": 2.0}, "trigger_at_seconds": 10, "duration_seconds": 10, "sort_order": 2}
  ]
}
```

Create `backend/app/seed/scenarios/solar_inverter_fault.json`:

```json
{
  "template_name": "Solar Inverter (Fronius Symo)",
  "name": "Fault Disconnect",
  "description": "Simulates inverter fault: AC power drops, DC voltage drifts, efficiency zeroes",
  "steps": [
    {"register_name": "ac_power", "anomaly_type": "flatline", "anomaly_params": {"value": 0}, "trigger_at_seconds": 0, "duration_seconds": 30, "sort_order": 0},
    {"register_name": "dc_voltage", "anomaly_type": "drift", "anomaly_params": {"drift_per_second": -5, "max_drift": -50}, "trigger_at_seconds": 2, "duration_seconds": 28, "sort_order": 1},
    {"register_name": "efficiency", "anomaly_type": "out_of_range", "anomaly_params": {"value": 0}, "trigger_at_seconds": 5, "duration_seconds": 25, "sort_order": 2}
  ]
}
```

- [ ] **Step 2: Add seed_builtin_scenarios to loader**

In `backend/app/seed/loader.py`, add at the end of the file:

```python
SCENARIOS_DIR = SEED_DIR / "scenarios"


async def seed_builtin_scenarios() -> None:
    """Load scenario seed JSON files and create builtin scenarios if they don't exist."""
    if not SCENARIOS_DIR.is_dir():
        logger.info("No scenarios seed directory found at %s", SCENARIOS_DIR)
        return

    from app.models.scenario import Scenario
    from app.schemas.scenario import ScenarioCreate, ScenarioStepCreate
    from app.services import scenario_service

    json_files = sorted(SCENARIOS_DIR.glob("*.json"))

    async with async_session_factory() as session:
        for json_file in json_files:
            try:
                raw = json.loads(json_file.read_text(encoding="utf-8"))
                scenario_name = raw["name"]
                template_name = raw["template_name"]

                # Resolve template
                stmt = select(DeviceTemplate).where(DeviceTemplate.name == template_name)
                result = await session.execute(stmt)
                template = result.scalar_one_or_none()
                if template is None:
                    logger.warning(
                        "Template '%s' not found for scenario seed '%s', skipping",
                        template_name, scenario_name,
                    )
                    continue

                # Check if already exists
                stmt2 = select(Scenario).where(
                    Scenario.template_id == template.id,
                    Scenario.name == scenario_name,
                    Scenario.is_builtin.is_(True),
                )
                result2 = await session.execute(stmt2)
                if result2.scalar_one_or_none() is not None:
                    logger.debug("Builtin scenario '%s' already exists, skipping", scenario_name)
                    continue

                steps = [ScenarioStepCreate(**s) for s in raw["steps"]]
                create_data = ScenarioCreate(
                    template_id=template.id,
                    name=scenario_name,
                    description=raw.get("description"),
                    steps=steps,
                )
                await scenario_service.create_scenario(session, create_data, is_builtin=True)
                logger.info("Seeded builtin scenario: %s", scenario_name)

            except Exception:
                logger.error("Failed to load scenario seed %s", json_file.name, exc_info=True)
```

- [ ] **Step 3: Call seed in main.py lifespan**

In `backend/app/main.py`, add import:

```python
from app.seed.loader import seed_builtin_profiles, seed_builtin_scenarios, seed_builtin_templates
```

(Replace the existing import line that only imports `seed_builtin_profiles, seed_builtin_templates`.)

Add after the profile seed call:

```python
    await seed_builtin_scenarios()
    logger.info("Scenario seed data check complete")
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/seed/scenarios/ backend/app/seed/loader.py backend/app/main.py
git commit -m "feat: add built-in scenario seed data (power outage, voltage instability, inverter fault)"
```

---

### Task 6: Frontend — Types + API Client + Store

**Files:**
- Create: `frontend/src/types/scenario.ts`
- Create: `frontend/src/services/scenarioApi.ts`
- Create: `frontend/src/stores/scenarioStore.ts`

- [ ] **Step 1: Create TypeScript types**

Create `frontend/src/types/scenario.ts`:

```typescript
export interface ScenarioStepCreate {
  register_name: string;
  anomaly_type: string;
  anomaly_params: Record<string, number | string | boolean>;
  trigger_at_seconds: number;
  duration_seconds: number;
  sort_order: number;
}

export interface ScenarioStepResponse extends ScenarioStepCreate {
  id: string;
}

export interface ScenarioSummary {
  id: string;
  template_id: string;
  template_name: string;
  name: string;
  description: string | null;
  is_builtin: boolean;
  total_duration_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface ScenarioDetail extends ScenarioSummary {
  steps: ScenarioStepResponse[];
}

export interface ScenarioCreate {
  template_id: string;
  name: string;
  description?: string | null;
  steps: ScenarioStepCreate[];
}

export interface ScenarioUpdate {
  name: string;
  description?: string | null;
  steps: ScenarioStepCreate[];
}

export interface ScenarioExport {
  name: string;
  description: string | null;
  template_name: string;
  steps: ScenarioStepCreate[];
}

export interface ActiveStepStatus {
  register_name: string;
  anomaly_type: string;
  remaining_seconds: number;
}

export interface ScenarioExecutionStatus {
  scenario_id: string;
  scenario_name: string;
  status: "running" | "completed";
  elapsed_seconds: number;
  total_duration_seconds: number;
  active_steps: ActiveStepStatus[];
}
```

- [ ] **Step 2: Create API client**

Create `frontend/src/services/scenarioApi.ts`:

```typescript
import axios from "axios";
import type { ApiResponse } from "../types";
import type {
  ScenarioCreate,
  ScenarioDetail,
  ScenarioExecutionStatus,
  ScenarioExport,
  ScenarioSummary,
  ScenarioUpdate,
} from "../types/scenario";

const api = axios.create({ baseURL: "/api/v1" });

export const scenarioApi = {
  list: (templateId?: string) =>
    api.get<ApiResponse<ScenarioSummary[]>>("/scenarios", {
      params: templateId ? { template_id: templateId } : undefined,
    }),

  get: (id: string) =>
    api.get<ApiResponse<ScenarioDetail>>(`/scenarios/${id}`),

  create: (data: ScenarioCreate) =>
    api.post<ApiResponse<ScenarioDetail>>("/scenarios", data),

  update: (id: string, data: ScenarioUpdate) =>
    api.put<ApiResponse<ScenarioDetail>>(`/scenarios/${id}`, data),

  delete: (id: string) =>
    api.delete<ApiResponse<null>>(`/scenarios/${id}`),

  export: (id: string) =>
    api.post<ApiResponse<ScenarioExport>>(`/scenarios/${id}/export`),

  import: (data: ScenarioExport) =>
    api.post<ApiResponse<ScenarioDetail>>("/scenarios/import", data),

  startExecution: (deviceId: string, scenarioId: string) =>
    api.post<ApiResponse<null>>(`/devices/${deviceId}/scenario/${scenarioId}/start`),

  stopExecution: (deviceId: string) =>
    api.post<ApiResponse<null>>(`/devices/${deviceId}/scenario/stop`),

  getExecutionStatus: (deviceId: string) =>
    api.get<ApiResponse<ScenarioExecutionStatus>>(`/devices/${deviceId}/scenario/status`),
};
```

- [ ] **Step 3: Create Zustand store**

Create `frontend/src/stores/scenarioStore.ts`:

```typescript
import { message } from "antd";
import { create } from "zustand";
import { scenarioApi } from "../services/scenarioApi";
import type { ScenarioDetail, ScenarioSummary } from "../types/scenario";

interface ScenarioState {
  scenarios: ScenarioSummary[];
  currentScenario: ScenarioDetail | null;
  loading: boolean;
  fetchScenarios: (templateId?: string) => Promise<void>;
  fetchScenario: (id: string) => Promise<void>;
  deleteScenario: (id: string) => Promise<boolean>;
  clearCurrentScenario: () => void;
}

export const useScenarioStore = create<ScenarioState>((set) => ({
  scenarios: [],
  currentScenario: null,
  loading: false,

  fetchScenarios: async (templateId) => {
    set({ loading: true });
    try {
      const resp = await scenarioApi.list(templateId);
      set({ scenarios: resp.data.data ?? [] });
    } catch {
      message.error("Failed to load scenarios");
    } finally {
      set({ loading: false });
    }
  },

  fetchScenario: async (id) => {
    set({ loading: true });
    try {
      const resp = await scenarioApi.get(id);
      set({ currentScenario: resp.data.data ?? null });
    } catch {
      message.error("Failed to load scenario");
    } finally {
      set({ loading: false });
    }
  },

  deleteScenario: async (id) => {
    try {
      await scenarioApi.delete(id);
      message.success("Scenario deleted");
      return true;
    } catch {
      message.error("Failed to delete scenario");
      return false;
    }
  },

  clearCurrentScenario: () => set({ currentScenario: null }),
}));
```

- [ ] **Step 4: Export scenario types from index**

In `frontend/src/types/index.ts`, add:

```typescript
export type { ScenarioSummary, ScenarioDetail } from "./scenario";
```

- [ ] **Step 5: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/scenario.ts frontend/src/types/index.ts frontend/src/services/scenarioApi.ts frontend/src/stores/scenarioStore.ts
git commit -m "feat: add scenario TypeScript types, API client, and Zustand store"
```

---

### Task 7: Frontend — Scenario List Page + Routing

**Files:**
- Create: `frontend/src/pages/Scenarios/index.tsx`
- Create: `frontend/src/pages/Scenarios/ScenarioList.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/layouts/MainLayout.tsx`

- [ ] **Step 1: Create ScenarioList page**

Create `frontend/src/pages/Scenarios/ScenarioList.tsx`:

```tsx
import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  PlusOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { Button, Popconfirm, Space, Table, Tag, Tooltip, Upload, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { scenarioApi } from "../../services/scenarioApi";
import { useScenarioStore } from "../../stores/scenarioStore";
import type { ScenarioSummary } from "../../types/scenario";

export function ScenarioList() {
  const navigate = useNavigate();
  const { scenarios, loading, fetchScenarios, deleteScenario } = useScenarioStore();

  useEffect(() => {
    fetchScenarios();
  }, [fetchScenarios]);

  const handleDelete = async (id: string) => {
    const success = await deleteScenario(id);
    if (success) await fetchScenarios();
  };

  const handleExport = async (id: string, name: string) => {
    try {
      const resp = await scenarioApi.export(id);
      const blob = new Blob([JSON.stringify(resp.data.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${name.replace(/\s+/g, "_").toLowerCase()}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      message.error("Failed to export scenario");
    }
  };

  const handleImport = async (file: File) => {
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      await scenarioApi.import(data);
      message.success("Scenario imported");
      await fetchScenarios();
    } catch {
      message.error("Failed to import scenario");
    }
    return false; // Prevent antd default upload
  };

  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
  };

  const columns: ColumnsType<ScenarioSummary> = [
    {
      title: "Name",
      dataIndex: "name",
      key: "name",
      render: (name: string, record) => (
        <Space>
          <a onClick={() => navigate(`/scenarios/${record.id}`)}>{name}</a>
          {record.is_builtin && <Tag color="blue">Built-in</Tag>}
        </Space>
      ),
    },
    { title: "Template", dataIndex: "template_name", key: "template_name" },
    {
      title: "Duration",
      dataIndex: "total_duration_seconds",
      key: "duration",
      width: 100,
      render: (v: number) => formatDuration(v),
    },
    {
      title: "Actions",
      key: "actions",
      width: 140,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="Edit">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => navigate(`/scenarios/${record.id}`)}
            />
          </Tooltip>
          <Tooltip title="Export">
            <Button
              type="text"
              size="small"
              icon={<DownloadOutlined />}
              onClick={() => handleExport(record.id, record.name)}
            />
          </Tooltip>
          {!record.is_builtin && (
            <Popconfirm title="Delete this scenario?" onConfirm={() => handleDelete(record.id)}>
              <Tooltip title="Delete">
                <Button type="text" size="small" danger icon={<DeleteOutlined />} />
              </Tooltip>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/scenarios/new")}>
            New Scenario
          </Button>
          <Upload accept=".json" showUploadList={false} beforeUpload={handleImport}>
            <Button icon={<UploadOutlined />}>Import</Button>
          </Upload>
        </Space>
      </div>
      <Table
        columns={columns}
        dataSource={scenarios}
        rowKey="id"
        loading={loading}
        pagination={false}
      />
    </div>
  );
}
```

- [ ] **Step 2: Create index.tsx**

Create `frontend/src/pages/Scenarios/index.tsx`:

```tsx
import { ScenarioList } from "./ScenarioList";

export default function ScenariosPage() {
  return <ScenarioList />;
}
```

- [ ] **Step 3: Add routes to App.tsx**

In `frontend/src/App.tsx`, add import:

```typescript
import ScenariosPage from "./pages/Scenarios";
import ScenarioEditor from "./pages/Scenarios/ScenarioEditor";
```

Add routes (after the simulation route):

```tsx
        <Route path="/scenarios/new" element={<ScenarioEditor />} />
        <Route path="/scenarios/:id" element={<ScenarioEditor />} />
        <Route path="/scenarios" element={<ScenariosPage />} />
```

Note: `ScenarioEditor` will be created in Task 8. For now, create a placeholder so the app compiles.

Create `frontend/src/pages/Scenarios/ScenarioEditor.tsx` (placeholder):

```tsx
export default function ScenarioEditor() {
  return <div>Scenario Editor (placeholder)</div>;
}
```

- [ ] **Step 4: Add Scenarios to sidebar**

In `frontend/src/layouts/MainLayout.tsx`, add import:

```typescript
import { ThunderboltOutlined } from "@ant-design/icons";
```

Add to the `menuItems` array (after the Simulation entry):

```typescript
  { key: "/scenarios", icon: <ThunderboltOutlined />, label: "Scenarios" },
```

- [ ] **Step 5: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Scenarios/ frontend/src/App.tsx frontend/src/layouts/MainLayout.tsx
git commit -m "feat: add Scenarios list page with routing and sidebar navigation"
```

---

### Task 8: Frontend — Timeline Editor

**Files:**
- Create: `frontend/src/pages/Scenarios/TimelineEditor.tsx`
- Create: `frontend/src/pages/Scenarios/TimelineBlock.tsx`
- Create: `frontend/src/pages/Scenarios/StepPopover.tsx`
- Rewrite: `frontend/src/pages/Scenarios/ScenarioEditor.tsx`

This is the largest frontend task. The implementer should create all four files and wire them together.

- [ ] **Step 1: Create StepPopover component**

Create `frontend/src/pages/Scenarios/StepPopover.tsx`:

```tsx
import { Button, Form, InputNumber, Select, Space } from "antd";
import type { ScenarioStepCreate } from "../../types/scenario";

const ANOMALY_TYPES = [
  { value: "spike", label: "Spike" },
  { value: "drift", label: "Drift" },
  { value: "flatline", label: "Flatline" },
  { value: "out_of_range", label: "Out of Range" },
  { value: "data_loss", label: "Data Loss" },
];

const ANOMALY_PARAM_FIELDS: Record<string, { label: string; key: string; default: number }[]> = {
  spike: [
    { label: "Probability", key: "probability", default: 0.8 },
    { label: "Multiplier", key: "multiplier", default: 1.5 },
  ],
  drift: [
    { label: "Drift/sec", key: "drift_per_second", default: 2 },
    { label: "Max Drift", key: "max_drift", default: 30 },
  ],
  flatline: [{ label: "Value", key: "value", default: 0 }],
  out_of_range: [{ label: "Value", key: "value", default: 0 }],
  data_loss: [],
};

interface StepPopoverProps {
  registerName: string;
  initialValues?: Partial<ScenarioStepCreate>;
  onSave: (step: ScenarioStepCreate) => void;
  onDelete?: () => void;
  onCancel: () => void;
}

export function StepPopover({ registerName, initialValues, onSave, onDelete, onCancel }: StepPopoverProps) {
  const [form] = Form.useForm();
  const anomalyType = Form.useWatch("anomaly_type", form);

  const handleSave = () => {
    form.validateFields().then((values) => {
      const params: Record<string, number> = {};
      const fields = ANOMALY_PARAM_FIELDS[values.anomaly_type] ?? [];
      for (const f of fields) {
        if (values[f.key] !== undefined) params[f.key] = values[f.key];
      }
      onSave({
        register_name: registerName,
        anomaly_type: values.anomaly_type,
        anomaly_params: params,
        trigger_at_seconds: values.trigger_at_seconds,
        duration_seconds: values.duration_seconds,
        sort_order: 0,
      });
    });
  };

  const paramFields = ANOMALY_PARAM_FIELDS[anomalyType] ?? [];

  return (
    <Form
      form={form}
      layout="vertical"
      size="small"
      style={{ width: 240 }}
      initialValues={{
        anomaly_type: initialValues?.anomaly_type ?? "out_of_range",
        trigger_at_seconds: initialValues?.trigger_at_seconds ?? 0,
        duration_seconds: initialValues?.duration_seconds ?? 10,
        ...initialValues?.anomaly_params,
      }}
    >
      <Form.Item name="anomaly_type" label="Anomaly Type" rules={[{ required: true }]}>
        <Select options={ANOMALY_TYPES} />
      </Form.Item>
      {paramFields.map((f) => (
        <Form.Item key={f.key} name={f.key} label={f.label} rules={[{ required: true }]}>
          <InputNumber style={{ width: "100%" }} step={f.key === "probability" ? 0.1 : 1} />
        </Form.Item>
      ))}
      <Form.Item name="trigger_at_seconds" label="Start (seconds)" rules={[{ required: true }]}>
        <InputNumber min={0} style={{ width: "100%" }} />
      </Form.Item>
      <Form.Item name="duration_seconds" label="Duration (seconds)" rules={[{ required: true }]}>
        <InputNumber min={1} style={{ width: "100%" }} />
      </Form.Item>
      <Space>
        <Button type="primary" onClick={handleSave}>Save</Button>
        {onDelete && <Button danger onClick={onDelete}>Delete</Button>}
        <Button onClick={onCancel}>Cancel</Button>
      </Space>
    </Form>
  );
}
```

- [ ] **Step 2: Create TimelineBlock component**

Create `frontend/src/pages/Scenarios/TimelineBlock.tsx`:

```tsx
import { CloseOutlined } from "@ant-design/icons";
import { Button, Popover, Tooltip } from "antd";
import { useRef, useState } from "react";
import type { ScenarioStepCreate } from "../../types/scenario";
import { StepPopover } from "./StepPopover";

const ANOMALY_COLORS: Record<string, string> = {
  spike: "#fa8c16",
  drift: "#1890ff",
  flatline: "#8c8c8c",
  out_of_range: "#f5222d",
  data_loss: "#722ed1",
};

interface TimelineBlockProps {
  step: ScenarioStepCreate;
  index: number;
  pxPerSecond: number;
  onUpdate: (index: number, step: ScenarioStepCreate) => void;
  onDelete: (index: number) => void;
  readOnly?: boolean;
}

export function TimelineBlock({ step, index, pxPerSecond, onUpdate, onDelete, readOnly }: TimelineBlockProps) {
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [dragging, setDragging] = useState<"move" | "resize-right" | null>(null);
  const dragStartX = useRef(0);
  const dragStartTrigger = useRef(0);
  const dragStartDuration = useRef(0);

  const left = step.trigger_at_seconds * pxPerSecond;
  const width = step.duration_seconds * pxPerSecond;
  const color = ANOMALY_COLORS[step.anomaly_type] ?? "#8c8c8c";

  const handleMouseDown = (e: React.MouseEvent, type: "move" | "resize-right") => {
    if (readOnly) return;
    e.preventDefault();
    e.stopPropagation();
    setDragging(type);
    dragStartX.current = e.clientX;
    dragStartTrigger.current = step.trigger_at_seconds;
    dragStartDuration.current = step.duration_seconds;

    const handleMouseMove = (ev: MouseEvent) => {
      const dx = ev.clientX - dragStartX.current;
      const dSeconds = Math.round(dx / pxPerSecond);
      if (type === "move") {
        const newTrigger = Math.max(0, dragStartTrigger.current + dSeconds);
        onUpdate(index, { ...step, trigger_at_seconds: newTrigger });
      } else {
        const newDuration = Math.max(1, dragStartDuration.current + dSeconds);
        onUpdate(index, { ...step, duration_seconds: newDuration });
      }
    };

    const handleMouseUp = () => {
      setDragging(null);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  return (
    <Popover
      open={popoverOpen && !dragging && !readOnly}
      onOpenChange={(open) => { if (!dragging) setPopoverOpen(open); }}
      trigger="click"
      content={
        <StepPopover
          registerName={step.register_name}
          initialValues={step}
          onSave={(updated) => { onUpdate(index, updated); setPopoverOpen(false); }}
          onDelete={() => { onDelete(index); setPopoverOpen(false); }}
          onCancel={() => setPopoverOpen(false)}
        />
      }
    >
      <Tooltip title={`${step.anomaly_type} (${step.trigger_at_seconds}s–${step.trigger_at_seconds + step.duration_seconds}s)`}>
        <div
          style={{
            position: "absolute",
            left,
            width: Math.max(width, 20),
            height: 28,
            top: 2,
            backgroundColor: color,
            borderRadius: 4,
            cursor: readOnly ? "default" : (dragging === "move" ? "grabbing" : "grab"),
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 4px",
            color: "white",
            fontSize: 11,
            userSelect: "none",
            opacity: dragging ? 0.7 : 1,
          }}
          onMouseDown={(e) => handleMouseDown(e, "move")}
        >
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
            {step.anomaly_type}
          </span>
          {!readOnly && (
            <Button
              type="text"
              size="small"
              icon={<CloseOutlined style={{ color: "white", fontSize: 10 }} />}
              onClick={(e) => { e.stopPropagation(); onDelete(index); }}
              style={{ minWidth: 16, padding: 0 }}
            />
          )}
          {!readOnly && (
            <div
              style={{
                position: "absolute",
                right: 0,
                top: 0,
                bottom: 0,
                width: 6,
                cursor: "ew-resize",
              }}
              onMouseDown={(e) => handleMouseDown(e, "resize-right")}
            />
          )}
        </div>
      </Tooltip>
    </Popover>
  );
}
```

- [ ] **Step 3: Create TimelineEditor component**

Create `frontend/src/pages/Scenarios/TimelineEditor.tsx`:

```tsx
import { MinusOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Popover, Space } from "antd";
import { useState } from "react";
import type { ScenarioStepCreate } from "../../types/scenario";
import { StepPopover } from "./StepPopover";
import { TimelineBlock } from "./TimelineBlock";

interface TimelineEditorProps {
  registerNames: string[];
  steps: ScenarioStepCreate[];
  onChange: (steps: ScenarioStepCreate[]) => void;
  readOnly?: boolean;
}

const MIN_PX_PER_SECOND = 5;
const MAX_PX_PER_SECOND = 40;
const DEFAULT_PX_PER_SECOND = 15;

export function TimelineEditor({ registerNames, steps, onChange, readOnly }: TimelineEditorProps) {
  const [pxPerSecond, setPxPerSecond] = useState(DEFAULT_PX_PER_SECOND);
  const [addPopover, setAddPopover] = useState<{ register: string; triggerAt: number } | null>(null);

  const maxTime = steps.length > 0
    ? Math.max(...steps.map((s) => s.trigger_at_seconds + s.duration_seconds))
    : 30;
  const timelineWidth = Math.max((maxTime + 10) * pxPerSecond, 600);

  const handleUpdate = (index: number, updated: ScenarioStepCreate) => {
    const newSteps = [...steps];
    newSteps[index] = updated;
    onChange(newSteps);
  };

  const handleDelete = (index: number) => {
    onChange(steps.filter((_, i) => i !== index));
  };

  const handleAdd = (step: ScenarioStepCreate) => {
    onChange([...steps, { ...step, sort_order: steps.length }]);
    setAddPopover(null);
  };

  const handleRowClick = (registerName: string, e: React.MouseEvent<HTMLDivElement>) => {
    if (readOnly) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const triggerAt = Math.max(0, Math.round(x / pxPerSecond));
    setAddPopover({ register: registerName, triggerAt });
  };

  // Time axis marks
  const marks: number[] = [];
  const step = pxPerSecond >= 15 ? 5 : 10;
  for (let t = 0; t <= maxTime + 10; t += step) {
    marks.push(t);
  }

  return (
    <div>
      <Space style={{ marginBottom: 8 }}>
        <Button
          size="small"
          icon={<MinusOutlined />}
          onClick={() => setPxPerSecond(Math.max(MIN_PX_PER_SECOND, pxPerSecond - 5))}
        />
        <span style={{ fontSize: 12, color: "#888" }}>{pxPerSecond}px/s</span>
        <Button
          size="small"
          icon={<PlusOutlined />}
          onClick={() => setPxPerSecond(Math.min(MAX_PX_PER_SECOND, pxPerSecond + 5))}
        />
      </Space>

      <div style={{ overflowX: "auto", border: "1px solid #d9d9d9", borderRadius: 4 }}>
        {/* Time axis */}
        <div style={{ position: "relative", height: 24, borderBottom: "1px solid #d9d9d9", marginLeft: 140 }}>
          {marks.map((t) => (
            <span
              key={t}
              style={{
                position: "absolute",
                left: t * pxPerSecond,
                fontSize: 10,
                color: "#888",
                transform: "translateX(-50%)",
                top: 4,
              }}
            >
              {t}s
            </span>
          ))}
        </div>

        {/* Register rows */}
        {registerNames.map((regName) => {
          const regSteps = steps
            .map((s, i) => ({ step: s, index: i }))
            .filter(({ step: s }) => s.register_name === regName);

          return (
            <div
              key={regName}
              style={{
                display: "flex",
                borderBottom: "1px solid #f0f0f0",
                minHeight: 32,
              }}
            >
              <div
                style={{
                  width: 140,
                  minWidth: 140,
                  padding: "4px 8px",
                  fontSize: 12,
                  borderRight: "1px solid #d9d9d9",
                  display: "flex",
                  alignItems: "center",
                  backgroundColor: "#fafafa",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={regName}
              >
                {regName}
              </div>
              <Popover
                open={addPopover?.register === regName}
                onOpenChange={(open) => { if (!open) setAddPopover(null); }}
                trigger="click"
                content={
                  addPopover?.register === regName ? (
                    <StepPopover
                      registerName={regName}
                      initialValues={{ trigger_at_seconds: addPopover.triggerAt }}
                      onSave={handleAdd}
                      onCancel={() => setAddPopover(null)}
                    />
                  ) : null
                }
              >
                <div
                  style={{
                    position: "relative",
                    flex: 1,
                    minWidth: timelineWidth,
                    cursor: readOnly ? "default" : "crosshair",
                  }}
                  onClick={(e) => handleRowClick(regName, e)}
                >
                  {regSteps.map(({ step: s, index: i }) => (
                    <TimelineBlock
                      key={i}
                      step={s}
                      index={i}
                      pxPerSecond={pxPerSecond}
                      onUpdate={handleUpdate}
                      onDelete={handleDelete}
                      readOnly={readOnly}
                    />
                  ))}
                </div>
              </Popover>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Rewrite ScenarioEditor**

Rewrite `frontend/src/pages/Scenarios/ScenarioEditor.tsx`:

```tsx
import { Button, Card, Form, Input, Select, Space, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { scenarioApi } from "../../services/scenarioApi";
import { useScenarioStore } from "../../stores/scenarioStore";
import type { ScenarioStepCreate } from "../../types/scenario";
import type { TemplateSummary } from "../../types/template";
import { TimelineEditor } from "./TimelineEditor";
import axios from "axios";
import type { ApiResponse } from "../../types";

export default function ScenarioEditor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentScenario, fetchScenario, clearCurrentScenario } = useScenarioStore();
  const [form] = Form.useForm();
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [registerNames, setRegisterNames] = useState<string[]>([]);
  const [steps, setSteps] = useState<ScenarioStepCreate[]>([]);
  const [saving, setSaving] = useState(false);

  const isEdit = !!id;
  const isBuiltin = currentScenario?.is_builtin ?? false;

  useEffect(() => {
    // Load templates for dropdown
    axios.get<ApiResponse<TemplateSummary[]>>("/api/v1/templates").then((resp) => {
      setTemplates(resp.data.data ?? []);
    });
    if (id) fetchScenario(id);
    return () => clearCurrentScenario();
  }, [id, fetchScenario, clearCurrentScenario]);

  useEffect(() => {
    if (currentScenario && isEdit) {
      form.setFieldsValue({
        name: currentScenario.name,
        description: currentScenario.description,
        template_id: currentScenario.template_id,
      });
      setSelectedTemplateId(currentScenario.template_id);
      setSteps(
        currentScenario.steps.map((s) => ({
          register_name: s.register_name,
          anomaly_type: s.anomaly_type,
          anomaly_params: s.anomaly_params,
          trigger_at_seconds: s.trigger_at_seconds,
          duration_seconds: s.duration_seconds,
          sort_order: s.sort_order,
        })),
      );
    }
  }, [currentScenario, isEdit, form]);

  useEffect(() => {
    if (selectedTemplateId) {
      // Fetch template detail to get register names
      axios.get<ApiResponse<{ registers: { name: string }[] }>>(`/api/v1/templates/${selectedTemplateId}`).then((resp) => {
        const regs = resp.data.data?.registers ?? [];
        setRegisterNames(regs.map((r) => r.name));
      });
    }
  }, [selectedTemplateId]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const values = await form.validateFields();
      if (isEdit && id) {
        await scenarioApi.update(id, {
          name: values.name,
          description: values.description,
          steps,
        });
        message.success("Scenario updated");
      } else {
        const resp = await scenarioApi.create({
          template_id: values.template_id,
          name: values.name,
          description: values.description,
          steps,
        });
        message.success("Scenario created");
        navigate(`/scenarios/${resp.data.data?.id}`, { replace: true });
      }
    } catch {
      message.error("Failed to save scenario");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button onClick={() => navigate("/scenarios")}>Back to List</Button>
      </Space>

      <Typography.Title level={3}>{isEdit ? "Edit Scenario" : "New Scenario"}</Typography.Title>

      <Card style={{ marginBottom: 16 }}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input disabled={isBuiltin} />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} disabled={isBuiltin} />
          </Form.Item>
          <Form.Item name="template_id" label="Template" rules={[{ required: true }]}>
            <Select
              disabled={isEdit}
              placeholder="Select template"
              onChange={(v) => { setSelectedTemplateId(v); setSteps([]); }}
              options={templates.map((t) => ({ value: t.id, label: t.name }))}
            />
          </Form.Item>
        </Form>
      </Card>

      {registerNames.length > 0 && (
        <Card title="Timeline" style={{ marginBottom: 16 }}>
          <TimelineEditor
            registerNames={registerNames}
            steps={steps}
            onChange={setSteps}
            readOnly={isBuiltin}
          />
        </Card>
      )}

      {!isBuiltin && (
        <Space>
          <Button type="primary" onClick={handleSave} loading={saving}>
            {isEdit ? "Save Changes" : "Create Scenario"}
          </Button>
          <Button onClick={() => navigate("/scenarios")}>Cancel</Button>
        </Space>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Scenarios/
git commit -m "feat: add scenario timeline editor with drag-and-drop blocks"
```

---

### Task 9: Frontend — Scenario Execution Card

**Files:**
- Create: `frontend/src/pages/Devices/ScenarioCard.tsx`
- Modify: `frontend/src/pages/Devices/DeviceDetail.tsx`

- [ ] **Step 1: Create ScenarioCard component**

Create `frontend/src/pages/Devices/ScenarioCard.tsx`:

```tsx
import { PlayCircleOutlined, StopOutlined } from "@ant-design/icons";
import { Badge, Button, Card, List, Progress, Select, Space, Typography, message } from "antd";
import { useCallback, useEffect, useRef, useState } from "react";
import { scenarioApi } from "../../services/scenarioApi";
import type { ScenarioExecutionStatus, ScenarioSummary } from "../../types/scenario";

interface ScenarioCardProps {
  deviceId: string;
  templateId: string;
  deviceStatus: string;
}

export function ScenarioCard({ deviceId, templateId, deviceStatus }: ScenarioCardProps) {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [status, setStatus] = useState<ScenarioExecutionStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    scenarioApi.list(templateId).then((resp) => {
      setScenarios(resp.data.data ?? []);
    });
  }, [templateId]);

  const pollStatus = useCallback(() => {
    scenarioApi.getExecutionStatus(deviceId).then((resp) => {
      const data = resp.data.data;
      if (data) {
        setStatus(data);
        if (data.status === "completed") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }
    }).catch(() => {
      setStatus(null);
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    });
  }, [deviceId]);

  useEffect(() => {
    // Check if scenario is already running on mount
    pollStatus();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [pollStatus]);

  const handleStart = async () => {
    if (!selectedId) return;
    setLoading(true);
    try {
      await scenarioApi.startExecution(deviceId, selectedId);
      message.success("Scenario started");
      // Start polling
      pollRef.current = setInterval(pollStatus, 1000);
      pollStatus();
    } catch {
      message.error("Failed to start scenario");
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await scenarioApi.stopExecution(deviceId);
      message.success("Scenario stopped");
      setStatus(null);
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    } catch {
      message.error("Failed to stop scenario");
    } finally {
      setLoading(false);
    }
  };

  const isRunning = status?.status === "running";
  const isCompleted = status?.status === "completed";
  const percent = status
    ? Math.round((status.elapsed_seconds / status.total_duration_seconds) * 100)
    : 0;

  return (
    <Card
      title={
        <Space>
          <span>Scenario</span>
          {isRunning && <Badge status="processing" text="Running" />}
          {isCompleted && <Badge status="success" text="Completed" />}
        </Space>
      }
      style={{ marginTop: 16 }}
    >
      {isRunning && status ? (
        <div>
          <Typography.Text strong>{status.scenario_name}</Typography.Text>
          <Progress
            percent={percent}
            format={() => `${status.elapsed_seconds}s / ${status.total_duration_seconds}s`}
            style={{ marginTop: 8, marginBottom: 12 }}
          />
          {status.active_steps.length > 0 && (
            <List
              size="small"
              header={<Typography.Text type="secondary">Active Steps</Typography.Text>}
              dataSource={status.active_steps}
              renderItem={(item) => (
                <List.Item>
                  <span>{item.register_name}</span>
                  <Badge color={item.anomaly_type === "spike" ? "orange" : "red"} text={item.anomaly_type} />
                  <Typography.Text type="secondary">{item.remaining_seconds}s remaining</Typography.Text>
                </List.Item>
              )}
              style={{ marginBottom: 12 }}
            />
          )}
          <Button danger type="primary" icon={<StopOutlined />} onClick={handleStop} loading={loading}>
            Stop Scenario
          </Button>
        </div>
      ) : (
        <Space direction="vertical" style={{ width: "100%" }}>
          {isCompleted && (
            <Typography.Text type="success">Scenario completed successfully</Typography.Text>
          )}
          <Select
            placeholder="Select a scenario"
            style={{ width: "100%" }}
            value={selectedId}
            onChange={setSelectedId}
            options={scenarios.map((s) => ({
              value: s.id,
              label: `${s.name} (${s.total_duration_seconds}s)`,
            }))}
          />
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={handleStart}
            loading={loading}
            disabled={!selectedId || deviceStatus !== "running"}
            style={{ backgroundColor: "#52c41a", borderColor: "#52c41a" }}
          >
            {isCompleted ? "Run Again" : "Run Scenario"}
          </Button>
          {deviceStatus !== "running" && (
            <Typography.Text type="secondary">Start the device to run scenarios</Typography.Text>
          )}
        </Space>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Add ScenarioCard to DeviceDetail**

In `frontend/src/pages/Devices/DeviceDetail.tsx`:

Add import:

```typescript
import { ScenarioCard } from "./ScenarioCard";
```

Add the ScenarioCard after the MqttPublishConfig component (after the closing `}` of the MqttPublishConfig block):

```tsx
      {id && currentDevice && (
        <ScenarioCard
          deviceId={id}
          templateId={currentDevice.template_id}
          deviceStatus={currentDevice.status}
        />
      )}
```

- [ ] **Step 3: Verify frontend compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Devices/ScenarioCard.tsx frontend/src/pages/Devices/DeviceDetail.tsx
git commit -m "feat: add scenario execution card to device detail page"
```

---

### Task 10: Final Verification + Docs

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/development-log.md`
- Modify: `docs/development-phases.md`
- Modify: `docs/api-reference.md`
- Modify: `docs/database-schema.md`

- [ ] **Step 1: Run full backend tests**

Run: `cd backend && python -m pytest -v`
Report pass/fail counts. Pre-existing `oid` failures are expected.

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Update CHANGELOG.md**

Add to `## [Unreleased]` section under `### Added`:

```markdown
- Scenario mode: coordinated multi-register anomaly sequences with visual timeline editor
- Scenario CRUD API (`/api/v1/scenarios`) with create, update, delete, export, import
- Scenario execution API: start, stop, status polling per device
- ScenarioRunner: in-memory executor with 1-second tick resolution
- Visual timeline editor: drag-and-drop blocks, zoom, click-to-add, per-register rows
- Built-in scenarios: Power Outage (three-phase), Voltage Instability (three-phase), Fault Disconnect (inverter)
- Scenario execution card in Device Detail page with progress bar and active step display
- Scenarios sidebar navigation and list page
```

- [ ] **Step 4: Update docs/development-phases.md**

Add new milestone under Phase 8:

```markdown
### Milestone 8.5：Scenario Mode ✅
- [x] Scenario + ScenarioStep DB models and migration
- [x] Scenario CRUD service with validation (register name check, overlap detection)
- [x] Scenario API routes (CRUD + export/import)
- [x] ScenarioRunner in-memory executor with AnomalyInjector integration
- [x] Scenario execution API (start/stop/status per device)
- [x] Built-in seed scenarios (3 scenarios for 2 templates)
- [x] Frontend: Scenarios list page with import/export
- [x] Frontend: Timeline editor with drag-and-drop blocks
- [x] Frontend: Scenario execution card in Device Detail
```

- [ ] **Step 5: Update docs/api-reference.md**

Add new section for Scenario API endpoints with request/response schemas.

- [ ] **Step 6: Update docs/database-schema.md**

Add `scenarios` and `scenario_steps` table definitions.

- [ ] **Step 7: Update docs/development-log.md**

Add entry for scenario mode implementation.

- [ ] **Step 8: Commit docs**

```bash
git add CHANGELOG.md docs/
git commit -m "docs: add scenario mode to CHANGELOG, API reference, DB schema, and development phases"
```
