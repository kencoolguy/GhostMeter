# Phase 5.2–7 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete all remaining GhostMeter phases — anomaly injection engine, fault integration, simulation frontend, real-time monitor dashboard, and system finalization.

**Architecture:** Layered approach building on existing simulation engine. Anomaly injection inserts between DataGenerator and ProtocolAdapter. Fault interception hooks into Modbus request handler. WebSocket broadcasts aggregated state every second. Frontend uses Ant Design + Zustand + Recharts.

**Tech Stack:** Python 3.12, FastAPI, pymodbus 3.12.1, SQLAlchemy 2.0, Alembic, React 18, TypeScript, Ant Design 5, Zustand, Recharts

**Spec:** `docs/superpowers/specs/2026-03-18-phase5-7-remaining-design.md`

---

## Chunk 1: Phase 5.2 — Anomaly Injection Engine (Backend)

### Task 1: AnomalySchedule DB Model + Migration

**Files:**
- Create: `backend/app/models/anomaly.py`
- Modify: `backend/app/models/__init__.py` (register model for Alembic discovery)
- Modify: `backend/tests/conftest.py:41-43` (add table to TRUNCATE)

- [ ] **Step 1: Create the ORM model**

Create `backend/app/models/anomaly.py`:

```python
"""ORM model for anomaly injection schedules."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class AnomalySchedule(Base):
    """Scheduled anomaly injection for a device register."""

    __tablename__ = "anomaly_schedules"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "register_name", "trigger_after_seconds",
            name="uq_anomaly_schedule_device_register_trigger",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_instances.id", ondelete="CASCADE"), nullable=False
    )
    register_name: Mapped[str] = mapped_column(String(100), nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(20), nullable=False)
    anomaly_params: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    trigger_after_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
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
```

- [ ] **Step 2: Register model in models/__init__.py for Alembic discovery**

In `backend/app/models/__init__.py`, add:

```python
from app.models.anomaly import AnomalySchedule
```

Add `"AnomalySchedule"` to `__all__`.

- [ ] **Step 3: Create Alembic migration**

Run: `cd backend && alembic revision --autogenerate -m "add anomaly_schedules table"`

Verify the generated migration creates the `anomaly_schedules` table with the unique constraint.

- [ ] **Step 4: Apply migration**

Run: `cd backend && alembic upgrade head`
Expected: Migration applies successfully.

- [ ] **Step 5: Update conftest.py TRUNCATE statement**

In `backend/tests/conftest.py:41-43`, add `anomaly_schedules` to the TRUNCATE list:

```python
await conn.execute(text(
    "TRUNCATE device_templates, register_definitions, device_instances, "
    "simulation_configs, anomaly_schedules CASCADE"
))
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/anomaly.py backend/app/models/__init__.py backend/alembic/versions/ backend/tests/conftest.py
git commit -m "feat: add anomaly_schedules DB model and migration"
```

---

### Task 2: Anomaly Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/anomaly.py`

- [ ] **Step 1: Create schemas**

Create `backend/app/schemas/anomaly.py`:

```python
"""Pydantic schemas for anomaly injection API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


VALID_ANOMALY_TYPES = {"spike", "drift", "flatline", "out_of_range", "data_loss"}

# Required params per anomaly type
_REQUIRED_PARAMS: dict[str, list[str]] = {
    "spike": ["multiplier", "probability"],
    "drift": ["drift_per_second", "max_drift"],
    "flatline": [],  # value is optional
    "out_of_range": ["value"],
    "data_loss": [],
}


class AnomalyInjectRequest(BaseModel):
    """Schema for real-time anomaly injection (in-memory)."""

    register_name: str
    anomaly_type: str
    anomaly_params: dict[str, Any] = {}

    @field_validator("anomaly_type")
    @classmethod
    def validate_anomaly_type(cls, v: str) -> str:
        if v not in VALID_ANOMALY_TYPES:
            raise ValueError(f"anomaly_type must be one of {VALID_ANOMALY_TYPES}")
        return v

    @model_validator(mode="after")
    def validate_params(self) -> "AnomalyInjectRequest":
        required = _REQUIRED_PARAMS.get(self.anomaly_type, [])
        for param in required:
            if param not in self.anomaly_params:
                raise ValueError(
                    f"anomaly_type '{self.anomaly_type}' requires param '{param}'"
                )
        # Validate param ranges
        if self.anomaly_type == "spike":
            if self.anomaly_params["multiplier"] <= 0:
                raise ValueError("multiplier must be > 0")
            prob = self.anomaly_params["probability"]
            if not 0 <= prob <= 1:
                raise ValueError("probability must be between 0 and 1")
        elif self.anomaly_type == "drift":
            if self.anomaly_params["max_drift"] <= 0:
                raise ValueError("max_drift must be > 0")
        return self


class AnomalyActiveResponse(BaseModel):
    """Response for an active (real-time) anomaly."""

    register_name: str
    anomaly_type: str
    anomaly_params: dict[str, Any]


class AnomalyScheduleCreate(BaseModel):
    """Schema for a single anomaly schedule entry."""

    register_name: str
    anomaly_type: str
    anomaly_params: dict[str, Any] = {}
    trigger_after_seconds: int
    duration_seconds: int
    is_enabled: bool = True

    @field_validator("anomaly_type")
    @classmethod
    def validate_anomaly_type(cls, v: str) -> str:
        if v not in VALID_ANOMALY_TYPES:
            raise ValueError(f"anomaly_type must be one of {VALID_ANOMALY_TYPES}")
        return v

    @field_validator("trigger_after_seconds")
    @classmethod
    def validate_trigger(cls, v: int) -> int:
        if v < 0:
            raise ValueError("trigger_after_seconds must be >= 0")
        return v

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("duration_seconds must be > 0")
        return v

    @model_validator(mode="after")
    def validate_params(self) -> "AnomalyScheduleCreate":
        required = _REQUIRED_PARAMS.get(self.anomaly_type, [])
        for param in required:
            if param not in self.anomaly_params:
                raise ValueError(
                    f"anomaly_type '{self.anomaly_type}' requires param '{param}'"
                )
        # Validate param ranges (same rules as AnomalyInjectRequest)
        if self.anomaly_type == "spike":
            if self.anomaly_params["multiplier"] <= 0:
                raise ValueError("multiplier must be > 0")
            prob = self.anomaly_params["probability"]
            if not 0 <= prob <= 1:
                raise ValueError("probability must be between 0 and 1")
        elif self.anomaly_type == "drift":
            if self.anomaly_params["max_drift"] <= 0:
                raise ValueError("max_drift must be > 0")
        return self


class AnomalyScheduleBatchSet(BaseModel):
    """Schema for batch setting anomaly schedules."""

    schedules: list[AnomalyScheduleCreate]


class AnomalyScheduleResponse(BaseModel):
    """Response for a persisted anomaly schedule."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    device_id: UUID
    register_name: str
    anomaly_type: str
    anomaly_params: dict[str, Any]
    trigger_after_seconds: int
    duration_seconds: int
    is_enabled: bool
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 2: Verify schemas parse correctly**

Run: `cd backend && python -c "from app.schemas.anomaly import AnomalyInjectRequest; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/anomaly.py
git commit -m "feat: add anomaly injection Pydantic schemas with param validation"
```

---

### Task 3: AnomalyInjector Core Logic

**Files:**
- Create: `backend/app/simulation/anomaly_injector.py`
- Create: `backend/tests/test_anomaly_injector.py`
- Modify: `backend/app/simulation/__init__.py`

- [ ] **Step 1: Write unit tests for anomaly injection logic**

Create `backend/tests/test_anomaly_injector.py`:

```python
"""Unit tests for AnomalyInjector."""

import uuid

import pytest

from app.simulation.anomaly_injector import AnomalyInjector, AnomalyState


@pytest.fixture
def injector() -> AnomalyInjector:
    return AnomalyInjector()


@pytest.fixture
def device_id() -> uuid.UUID:
    return uuid.uuid4()


class TestInjectAndApply:
    def test_no_anomaly_returns_original(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        result = injector.apply(device_id, "voltage", 230.0, 10.0)
        assert result == 230.0

    def test_flatline_with_explicit_value(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "flatline", {"value": 200.0})
        result = injector.apply(device_id, "voltage", 230.0, 10.0)
        assert result == 200.0

    def test_flatline_freezes_at_current(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "flatline", {})
        # First call captures value
        result1 = injector.apply(device_id, "voltage", 230.0, 10.0)
        assert result1 == 230.0
        # Second call returns frozen value even if input changes
        result2 = injector.apply(device_id, "voltage", 240.0, 11.0)
        assert result2 == 230.0

    def test_out_of_range(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "out_of_range", {"value": 999.0})
        result = injector.apply(device_id, "voltage", 230.0, 10.0)
        assert result == 999.0

    def test_data_loss(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "data_loss", {})
        result = injector.apply(device_id, "voltage", 230.0, 10.0)
        assert result == 0.0

    def test_spike_with_probability_1(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(
            device_id, "voltage", "spike",
            {"multiplier": 3.0, "probability": 1.0},
        )
        result = injector.apply(device_id, "voltage", 100.0, 10.0)
        assert result == 300.0

    def test_spike_with_probability_0(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(
            device_id, "voltage", "spike",
            {"multiplier": 3.0, "probability": 0.0},
        )
        result = injector.apply(device_id, "voltage", 100.0, 10.0)
        assert result == 100.0

    def test_drift_accumulates(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(
            device_id, "voltage", "drift",
            {"drift_per_second": 1.0, "max_drift": 50.0},
        )
        # At elapsed=10s (activated_at=10s), drift starts from 0
        result_at_10 = injector.apply(device_id, "voltage", 230.0, 10.0)
        assert result_at_10 == 230.0  # 0 seconds of drift
        # At elapsed=15s, 5 seconds of drift
        result_at_15 = injector.apply(device_id, "voltage", 230.0, 15.0)
        assert result_at_15 == 235.0

    def test_drift_capped_at_max(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(
            device_id, "voltage", "drift",
            {"drift_per_second": 10.0, "max_drift": 5.0},
        )
        injector.apply(device_id, "voltage", 230.0, 10.0)  # activate
        result = injector.apply(device_id, "voltage", 230.0, 20.0)  # 10s * 10 = 100, capped at 5
        assert result == 235.0


class TestRemoveAndClear:
    def test_remove_specific_register(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "data_loss", {})
        injector.inject(device_id, "current", "data_loss", {})
        injector.remove(device_id, "voltage")
        assert injector.apply(device_id, "voltage", 230.0, 10.0) == 230.0
        assert injector.apply(device_id, "current", 15.0, 10.0) == 0.0

    def test_clear_device(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "data_loss", {})
        injector.inject(device_id, "current", "data_loss", {})
        injector.clear_device(device_id)
        assert injector.apply(device_id, "voltage", 230.0, 10.0) == 230.0
        assert injector.apply(device_id, "current", 15.0, 10.0) == 15.0

    def test_get_active_anomalies(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.inject(device_id, "voltage", "spike", {"multiplier": 2.0, "probability": 1.0})
        active = injector.get_active(device_id)
        assert len(active) == 1
        assert "voltage" in active
        assert active["voltage"].anomaly_type == "spike"

    def test_get_active_empty(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        active = injector.get_active(device_id)
        assert active == {}


class TestScheduleChecking:
    def test_schedule_activates_in_window(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.load_schedules(device_id, [
            {
                "register_name": "voltage",
                "anomaly_type": "data_loss",
                "anomaly_params": {},
                "trigger_after_seconds": 100,
                "duration_seconds": 60,
            },
        ])
        # Before window
        result_50 = injector.apply(device_id, "voltage", 230.0, 50.0)
        assert result_50 == 230.0
        # Inside window
        result_120 = injector.apply(device_id, "voltage", 230.0, 120.0)
        assert result_120 == 0.0
        # After window
        result_170 = injector.apply(device_id, "voltage", 230.0, 170.0)
        assert result_170 == 230.0

    def test_realtime_takes_precedence_over_schedule(
        self, injector: AnomalyInjector, device_id: uuid.UUID
    ) -> None:
        injector.load_schedules(device_id, [
            {
                "register_name": "voltage",
                "anomaly_type": "data_loss",
                "anomaly_params": {},
                "trigger_after_seconds": 0,
                "duration_seconds": 9999,
            },
        ])
        # Real-time overrides schedule
        injector.inject(device_id, "voltage", "out_of_range", {"value": 999.0})
        result = injector.apply(device_id, "voltage", 230.0, 50.0)
        assert result == 999.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_anomaly_injector.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement AnomalyInjector**

Create `backend/app/simulation/anomaly_injector.py`:

```python
"""Anomaly injection engine — applies anomalies to generated register values."""

import logging
import random
from dataclasses import dataclass, field
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class AnomalyState:
    """State of an active anomaly on a register."""

    anomaly_type: str
    params: dict
    activated_at: float = 0.0  # elapsed_seconds when activated
    frozen_value: float | None = None  # for flatline without explicit value


@dataclass
class ScheduleEntry:
    """A loaded schedule entry (in-memory representation)."""

    register_name: str
    anomaly_type: str
    anomaly_params: dict
    trigger_after_seconds: int
    duration_seconds: int


class AnomalyInjector:
    """Manages per-device anomaly state and applies anomalies to values."""

    def __init__(self) -> None:
        # Real-time anomalies: device_id → register_name → AnomalyState
        self._active: dict[UUID, dict[str, AnomalyState]] = {}
        # Loaded schedules: device_id → list of ScheduleEntry
        self._schedules: dict[UUID, list[ScheduleEntry]] = {}
        # Schedule-activated anomalies (tracked separately from real-time)
        self._scheduled_active: dict[UUID, dict[str, AnomalyState]] = {}

    def inject(
        self,
        device_id: UUID,
        register_name: str,
        anomaly_type: str,
        params: dict,
    ) -> None:
        """Inject a real-time anomaly on a register (immediate, in-memory)."""
        if device_id not in self._active:
            self._active[device_id] = {}
        self._active[device_id][register_name] = AnomalyState(
            anomaly_type=anomaly_type,
            params=params,
        )
        logger.info(
            "Anomaly injected: device=%s register=%s type=%s",
            device_id, register_name, anomaly_type,
        )

    def remove(self, device_id: UUID, register_name: str) -> None:
        """Remove a real-time anomaly from a specific register."""
        if device_id in self._active:
            self._active[device_id].pop(register_name, None)

    def clear_realtime(self, device_id: UUID) -> None:
        """Clear only real-time anomalies (not schedules)."""
        self._active.pop(device_id, None)

    def clear_device(self, device_id: UUID) -> None:
        """Clear all state for a device (real-time + schedules). Used on device stop."""
        self._active.pop(device_id, None)
        self._schedules.pop(device_id, None)
        self._scheduled_active.pop(device_id, None)

    def get_active(self, device_id: UUID) -> dict[str, AnomalyState]:
        """Get all active real-time anomalies for a device."""
        return dict(self._active.get(device_id, {}))

    def load_schedules(self, device_id: UUID, schedules: list[dict]) -> None:
        """Load schedule entries for a device (called on device start)."""
        self._schedules[device_id] = [
            ScheduleEntry(
                register_name=s["register_name"],
                anomaly_type=s["anomaly_type"],
                anomaly_params=s["anomaly_params"],
                trigger_after_seconds=s["trigger_after_seconds"],
                duration_seconds=s["duration_seconds"],
            )
            for s in schedules
        ]
        self._scheduled_active.pop(device_id, None)

    def apply(
        self,
        device_id: UUID,
        register_name: str,
        value: float,
        elapsed_seconds: float,
    ) -> float:
        """Apply anomaly to a value. Returns modified or original value."""
        # Real-time anomaly takes precedence
        rt_anomalies = self._active.get(device_id, {})
        if register_name in rt_anomalies:
            return self._apply_anomaly(
                rt_anomalies[register_name], value, elapsed_seconds,
            )

        # Check scheduled anomalies
        self._update_scheduled_anomalies(device_id, register_name, elapsed_seconds)
        sched_anomalies = self._scheduled_active.get(device_id, {})
        if register_name in sched_anomalies:
            return self._apply_anomaly(
                sched_anomalies[register_name], value, elapsed_seconds,
            )

        return value

    def _update_scheduled_anomalies(
        self,
        device_id: UUID,
        register_name: str,
        elapsed_seconds: float,
    ) -> None:
        """Activate/deactivate scheduled anomalies based on elapsed time."""
        schedules = self._schedules.get(device_id, [])
        if not schedules:
            return

        if device_id not in self._scheduled_active:
            self._scheduled_active[device_id] = {}

        # Find matching schedule for this register
        active_schedule = None
        for sched in schedules:
            if sched.register_name != register_name:
                continue
            start = sched.trigger_after_seconds
            end = start + sched.duration_seconds
            if start <= elapsed_seconds < end:
                active_schedule = sched
                break

        if active_schedule is not None:
            # Activate if not already active
            if register_name not in self._scheduled_active[device_id]:
                self._scheduled_active[device_id][register_name] = AnomalyState(
                    anomaly_type=active_schedule.anomaly_type,
                    params=active_schedule.anomaly_params,
                    activated_at=elapsed_seconds,
                )
        else:
            # Deactivate if outside window
            self._scheduled_active.get(device_id, {}).pop(register_name, None)

    def _apply_anomaly(
        self,
        state: AnomalyState,
        value: float,
        elapsed_seconds: float,
    ) -> float:
        """Apply a specific anomaly to a value."""
        match state.anomaly_type:
            case "spike":
                prob = float(state.params.get("probability", 0.1))
                mult = float(state.params.get("multiplier", 2.0))
                if random.random() < prob:
                    return value * mult
                return value

            case "drift":
                drift_rate = float(state.params["drift_per_second"])
                max_drift = float(state.params["max_drift"])
                time_since = elapsed_seconds - state.activated_at
                drift = drift_rate * time_since
                # Clamp to max_drift (handle both positive and negative)
                if abs(drift) > abs(max_drift):
                    drift = max_drift if drift_rate >= 0 else -max_drift
                return value + drift

            case "flatline":
                if "value" in state.params:
                    return float(state.params["value"])
                if state.frozen_value is None:
                    state.frozen_value = value
                return state.frozen_value

            case "out_of_range":
                return float(state.params["value"])

            case "data_loss":
                return 0.0

            case _:
                return value

    def clear_all(self) -> None:
        """Clear all state (used during shutdown)."""
        self._active.clear()
        self._schedules.clear()
        self._scheduled_active.clear()
```

- [ ] **Step 4: Update `simulation/__init__.py` with singleton**

Add to `backend/app/simulation/__init__.py`:

```python
from app.simulation.anomaly_injector import AnomalyInjector

anomaly_injector = AnomalyInjector()
```

Update `__all__` to include `"anomaly_injector"` and `"AnomalyInjector"`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_anomaly_injector.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/simulation/anomaly_injector.py backend/app/simulation/__init__.py backend/tests/test_anomaly_injector.py
git commit -m "feat: add AnomalyInjector core logic with schedule support"
```

---

### Task 4: Anomaly Service Layer

**Files:**
- Create: `backend/app/services/anomaly_service.py`

- [ ] **Step 1: Create anomaly service**

Create `backend/app/services/anomaly_service.py`. Follow the exact pattern from `simulation_service.py` — use `_get_device_or_404`, `_get_template_register_names`, and overlap validation:

```python
"""CRUD service for anomaly schedules + real-time anomaly control."""

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import NotFoundException, ValidationException
from app.models.anomaly import AnomalySchedule
from app.models.device import DeviceInstance
from app.models.template import DeviceTemplate
from app.schemas.anomaly import (
    AnomalyInjectRequest,
    AnomalyScheduleBatchSet,
)
from app.simulation import anomaly_injector

logger = logging.getLogger(__name__)


async def _get_device_or_404(
    session: AsyncSession, device_id: uuid.UUID,
) -> DeviceInstance:
    """Get device or raise 404."""
    stmt = select(DeviceInstance).where(DeviceInstance.id == device_id)
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()
    if device is None:
        raise NotFoundException(
            detail="Device not found", error_code="DEVICE_NOT_FOUND"
        )
    return device


async def _get_template_register_names(
    session: AsyncSession, template_id: uuid.UUID,
) -> set[str]:
    """Get valid register names for a template."""
    stmt = (
        select(DeviceTemplate)
        .options(selectinload(DeviceTemplate.registers))
        .where(DeviceTemplate.id == template_id)
    )
    result = await session.execute(stmt)
    template = result.scalar_one()
    return {reg.name for reg in template.registers}


def _check_overlap(schedules: list, register_name: str) -> None:
    """Check for overlapping time windows for the same register. Raise 422 if found."""
    same_reg = [
        s for s in schedules if s.register_name == register_name
    ]
    for i, a in enumerate(same_reg):
        a_start = a.trigger_after_seconds
        a_end = a_start + a.duration_seconds
        for b in same_reg[i + 1:]:
            b_start = b.trigger_after_seconds
            b_end = b_start + b.duration_seconds
            if a_start < b_end and b_start < a_end:
                raise ValidationException(
                    f"Overlapping schedule for register '{register_name}': "
                    f"[{a_start}s–{a_end}s) and [{b_start}s–{b_end}s)"
                )


# --- Real-time anomaly control ---


def inject_anomaly(device_id: uuid.UUID, data: AnomalyInjectRequest) -> None:
    """Inject a real-time anomaly (in-memory)."""
    anomaly_injector.inject(
        device_id, data.register_name, data.anomaly_type, data.anomaly_params,
    )


def get_active_anomalies(device_id: uuid.UUID) -> dict:
    """Get all active real-time anomalies."""
    return anomaly_injector.get_active(device_id)


def remove_anomaly(device_id: uuid.UUID, register_name: str) -> None:
    """Remove a specific real-time anomaly."""
    anomaly_injector.remove(device_id, register_name)


def clear_anomalies(device_id: uuid.UUID) -> None:
    """Clear all real-time anomalies for a device (does NOT clear schedules)."""
    anomaly_injector.clear_realtime(device_id)


# --- Schedule CRUD ---


async def get_schedules(
    session: AsyncSession, device_id: uuid.UUID,
) -> list[AnomalySchedule]:
    """List all anomaly schedules for a device."""
    await _get_device_or_404(session, device_id)
    stmt = (
        select(AnomalySchedule)
        .where(AnomalySchedule.device_id == device_id)
        .order_by(AnomalySchedule.trigger_after_seconds)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def set_schedules(
    session: AsyncSession,
    device_id: uuid.UUID,
    data: AnomalyScheduleBatchSet,
) -> list[AnomalySchedule]:
    """Replace all anomaly schedules for a device."""
    device = await _get_device_or_404(session, device_id)
    valid_names = await _get_template_register_names(session, device.template_id)

    # Validate register names
    for sched in data.schedules:
        if sched.register_name not in valid_names:
            raise ValidationException(
                f"Register '{sched.register_name}' not found in device template"
            )

    # Check for overlapping windows per register
    register_names = {s.register_name for s in data.schedules}
    for name in register_names:
        _check_overlap(data.schedules, name)

    # Delete existing schedules
    await session.execute(
        delete(AnomalySchedule).where(AnomalySchedule.device_id == device_id)
    )

    # Create new schedules
    new_schedules = []
    for sched in data.schedules:
        db_sched = AnomalySchedule(
            device_id=device_id,
            register_name=sched.register_name,
            anomaly_type=sched.anomaly_type,
            anomaly_params=sched.anomaly_params,
            trigger_after_seconds=sched.trigger_after_seconds,
            duration_seconds=sched.duration_seconds,
            is_enabled=sched.is_enabled,
        )
        session.add(db_sched)
        new_schedules.append(db_sched)

    await session.commit()
    for s in new_schedules:
        await session.refresh(s)

    return new_schedules


async def delete_schedules(
    session: AsyncSession, device_id: uuid.UUID,
) -> None:
    """Delete all anomaly schedules for a device."""
    await _get_device_or_404(session, device_id)
    await session.execute(
        delete(AnomalySchedule).where(AnomalySchedule.device_id == device_id)
    )
    await session.commit()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/anomaly_service.py
git commit -m "feat: add anomaly service layer with overlap validation"
```

---

### Task 5: Anomaly API Routes

**Files:**
- Create: `backend/app/api/routes/anomaly.py`
- Modify: `backend/app/main.py:99` (register router)

- [ ] **Step 1: Create API routes**

Create `backend/app/api/routes/anomaly.py`:

```python
"""API routes for anomaly injection and schedule management."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.anomaly import (
    AnomalyActiveResponse,
    AnomalyInjectRequest,
    AnomalyScheduleBatchSet,
    AnomalyScheduleResponse,
)
from app.schemas.common import ApiResponse
from app.services import anomaly_service

router = APIRouter()


# --- Real-time Anomaly Control ---


@router.post(
    "/{device_id}/anomaly",
    response_model=ApiResponse[AnomalyActiveResponse],
)
async def inject_anomaly(
    device_id: uuid.UUID,
    data: AnomalyInjectRequest,
) -> ApiResponse[AnomalyActiveResponse]:
    """Inject a real-time anomaly on a register (in-memory, immediate)."""
    anomaly_service.inject_anomaly(device_id, data)
    return ApiResponse(
        data=AnomalyActiveResponse(
            register_name=data.register_name,
            anomaly_type=data.anomaly_type,
            anomaly_params=data.anomaly_params,
        )
    )


@router.get(
    "/{device_id}/anomaly",
    response_model=ApiResponse[list[AnomalyActiveResponse]],
)
async def get_active_anomalies(
    device_id: uuid.UUID,
) -> ApiResponse[list[AnomalyActiveResponse]]:
    """List all active real-time anomalies for a device."""
    active = anomaly_service.get_active_anomalies(device_id)
    return ApiResponse(
        data=[
            AnomalyActiveResponse(
                register_name=reg,
                anomaly_type=state.anomaly_type,
                anomaly_params=state.params,
            )
            for reg, state in active.items()
        ]
    )


@router.delete(
    "/{device_id}/anomaly/{register_name}",
    response_model=ApiResponse[None],
)
async def remove_anomaly(
    device_id: uuid.UUID,
    register_name: str,
) -> ApiResponse[None]:
    """Remove a real-time anomaly from a specific register."""
    anomaly_service.remove_anomaly(device_id, register_name)
    return ApiResponse(message="Anomaly removed")


@router.delete(
    "/{device_id}/anomaly",
    response_model=ApiResponse[None],
)
async def clear_anomalies(
    device_id: uuid.UUID,
) -> ApiResponse[None]:
    """Clear all real-time anomalies for a device."""
    anomaly_service.clear_anomalies(device_id)
    return ApiResponse(message="All anomalies cleared")


# --- Schedule Management ---


@router.get(
    "/{device_id}/anomaly/schedules",
    response_model=ApiResponse[list[AnomalyScheduleResponse]],
)
async def get_schedules(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[AnomalyScheduleResponse]]:
    """List all anomaly schedules for a device."""
    schedules = await anomaly_service.get_schedules(session, device_id)
    return ApiResponse(
        data=[AnomalyScheduleResponse.model_validate(s) for s in schedules]
    )


@router.put(
    "/{device_id}/anomaly/schedules",
    response_model=ApiResponse[list[AnomalyScheduleResponse]],
)
async def set_schedules(
    device_id: uuid.UUID,
    data: AnomalyScheduleBatchSet,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[AnomalyScheduleResponse]]:
    """Batch set (replace) all anomaly schedules for a device."""
    schedules = await anomaly_service.set_schedules(session, device_id, data)
    return ApiResponse(
        data=[AnomalyScheduleResponse.model_validate(s) for s in schedules]
    )


@router.delete(
    "/{device_id}/anomaly/schedules",
    response_model=ApiResponse[None],
)
async def delete_schedules(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Clear all anomaly schedules for a device."""
    await anomaly_service.delete_schedules(session, device_id)
    return ApiResponse(message="All schedules deleted")
```

- [ ] **Step 2: Register router in main.py**

In `backend/app/main.py`, add import and router registration after the simulation router:

```python
from app.api.routes.anomaly import router as anomaly_router
```

After line 99, add:
```python
api_v1_router.include_router(anomaly_router, prefix="/devices", tags=["anomaly"])
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/routes/anomaly.py backend/app/main.py
git commit -m "feat: add anomaly injection and schedule API routes"
```

---

### Task 6: Anomaly API Integration Tests

**Files:**
- Create: `backend/tests/test_anomaly_api.py`

- [ ] **Step 1: Write API integration tests**

Create `backend/tests/test_anomaly_api.py`:

```python
"""Integration tests for anomaly injection and schedule API routes."""

import uuid

from httpx import AsyncClient


TEMPLATE_PAYLOAD = {
    "name": "Anomaly Test Meter",
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
        {
            "name": "current",
            "address": 2,
            "function_code": 4,
            "data_type": "float32",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "A",
            "sort_order": 1,
        },
    ],
}


async def _create_device(client: AsyncClient) -> tuple[str, str]:
    """Create template + device, return (template_id, device_id)."""
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    tid = resp.json()["data"]["id"]
    resp = await client.post(
        "/api/v1/devices",
        json={"template_id": tid, "name": "Anomaly Dev", "slave_id": 20},
    )
    assert resp.status_code == 201
    did = resp.json()["data"]["id"]
    return tid, did


class TestRealTimeAnomaly:
    async def test_inject_and_get(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        resp = await client.post(
            f"/api/v1/devices/{did}/anomaly",
            json={
                "register_name": "voltage",
                "anomaly_type": "spike",
                "anomaly_params": {"multiplier": 3.0, "probability": 0.5},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["anomaly_type"] == "spike"

        resp = await client.get(f"/api/v1/devices/{did}/anomaly")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    async def test_remove_specific(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        await client.post(
            f"/api/v1/devices/{did}/anomaly",
            json={"register_name": "voltage", "anomaly_type": "data_loss", "anomaly_params": {}},
        )
        await client.post(
            f"/api/v1/devices/{did}/anomaly",
            json={"register_name": "current", "anomaly_type": "data_loss", "anomaly_params": {}},
        )
        resp = await client.delete(f"/api/v1/devices/{did}/anomaly/voltage")
        assert resp.status_code == 200

        resp = await client.get(f"/api/v1/devices/{did}/anomaly")
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["register_name"] == "current"

    async def test_clear_all(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        await client.post(
            f"/api/v1/devices/{did}/anomaly",
            json={"register_name": "voltage", "anomaly_type": "data_loss", "anomaly_params": {}},
        )
        resp = await client.delete(f"/api/v1/devices/{did}/anomaly")
        assert resp.status_code == 200

        resp = await client.get(f"/api/v1/devices/{did}/anomaly")
        assert resp.json()["data"] == []

    async def test_invalid_anomaly_type(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        resp = await client.post(
            f"/api/v1/devices/{did}/anomaly",
            json={"register_name": "voltage", "anomaly_type": "invalid", "anomaly_params": {}},
        )
        assert resp.status_code == 422

    async def test_spike_missing_params(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        resp = await client.post(
            f"/api/v1/devices/{did}/anomaly",
            json={"register_name": "voltage", "anomaly_type": "spike", "anomaly_params": {}},
        )
        assert resp.status_code == 422


class TestAnomalySchedules:
    async def test_set_and_get_schedules(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        payload = {
            "schedules": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "spike",
                    "anomaly_params": {"multiplier": 3.0, "probability": 0.5},
                    "trigger_after_seconds": 300,
                    "duration_seconds": 60,
                },
            ],
        }
        resp = await client.put(f"/api/v1/devices/{did}/anomaly/schedules", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["register_name"] == "voltage"

        resp = await client.get(f"/api/v1/devices/{did}/anomaly/schedules")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    async def test_replace_schedules(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        payload1 = {
            "schedules": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "data_loss",
                    "anomaly_params": {},
                    "trigger_after_seconds": 100,
                    "duration_seconds": 30,
                },
            ],
        }
        await client.put(f"/api/v1/devices/{did}/anomaly/schedules", json=payload1)

        payload2 = {
            "schedules": [
                {
                    "register_name": "current",
                    "anomaly_type": "flatline",
                    "anomaly_params": {"value": 0.0},
                    "trigger_after_seconds": 200,
                    "duration_seconds": 60,
                },
            ],
        }
        resp = await client.put(f"/api/v1/devices/{did}/anomaly/schedules", json=payload2)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["register_name"] == "current"

    async def test_overlapping_schedules_rejected(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        payload = {
            "schedules": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "data_loss",
                    "anomaly_params": {},
                    "trigger_after_seconds": 100,
                    "duration_seconds": 60,
                },
                {
                    "register_name": "voltage",
                    "anomaly_type": "spike",
                    "anomaly_params": {"multiplier": 2.0, "probability": 1.0},
                    "trigger_after_seconds": 130,
                    "duration_seconds": 60,
                },
            ],
        }
        resp = await client.put(f"/api/v1/devices/{did}/anomaly/schedules", json=payload)
        assert resp.status_code == 422

    async def test_invalid_register_name(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        payload = {
            "schedules": [
                {
                    "register_name": "nonexistent",
                    "anomaly_type": "data_loss",
                    "anomaly_params": {},
                    "trigger_after_seconds": 100,
                    "duration_seconds": 30,
                },
            ],
        }
        resp = await client.put(f"/api/v1/devices/{did}/anomaly/schedules", json=payload)
        assert resp.status_code == 422

    async def test_delete_schedules(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        payload = {
            "schedules": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "data_loss",
                    "anomaly_params": {},
                    "trigger_after_seconds": 100,
                    "duration_seconds": 30,
                },
            ],
        }
        await client.put(f"/api/v1/devices/{did}/anomaly/schedules", json=payload)

        resp = await client.delete(f"/api/v1/devices/{did}/anomaly/schedules")
        assert resp.status_code == 200

        resp = await client.get(f"/api/v1/devices/{did}/anomaly/schedules")
        assert resp.json()["data"] == []

    async def test_nonexistent_device(self, client: AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/devices/{fake_id}/anomaly/schedules")
        assert resp.status_code == 404
```

- [ ] **Step 2: Run tests**

Run: `cd backend && pytest tests/test_anomaly_api.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_anomaly_api.py
git commit -m "test: add anomaly API integration tests"
```

---

### Task 7: Integrate AnomalyInjector into SimulationEngine

**Files:**
- Modify: `backend/app/simulation/engine.py:17,37-39,61-70,142-143,176-184`

- [ ] **Step 1: Modify engine.py**

**Circular import note:** `engine.py` is imported by `simulation/__init__.py`, so it cannot import from `app.simulation` at module level. Use lazy import inside methods that need the singleton.

Changes to make:

**1. In `__init__`**, add instance state for current values:
```python
self._device_values: dict[UUID, dict[str, float]] = {}
```

**2. In `_run_device()`**, at the top (after `adapter = ...`, line 147), add lazy import:
```python
from app.simulation import anomaly_injector
```

**3. In `_run_device()`**, replace `current_values: dict[str, float] = {}` (line 143) with:
```python
self._device_values[device_id] = {}
```

Replace all `current_values[` with `self._device_values[device_id][` in the loop body (lines 167, 184).

Also update the `GeneratorContext` construction (line 167):
```python
current_values=self._device_values[device_id],
```

**4. In the inner loop**, after `generated = self._data_generator.generate(...)` (line 177-179), add:
```python
generated = anomaly_injector.apply(
    device_id, config.register_name, generated,
    context.elapsed_seconds,
)
```

**5. In `stop_device()`** (after line 70), add:
```python
self._device_values.pop(device_id, None)
```

**6. In `shutdown()`** (after line 84), add:
```python
self._device_values.clear()
```

**7. Add public accessor** (new method):
```python
def get_current_values(self, device_id: UUID) -> dict[str, float]:
    """Get last generated values for a device (for monitoring)."""
    return dict(self._device_values.get(device_id, {}))
```

- [ ] **Step 2: Run all existing tests**

Run: `cd backend && pytest -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 3: Commit**

```bash
git add backend/app/simulation/engine.py
git commit -m "feat: integrate anomaly injector into simulation engine loop"
```

---

### Task 8: Load Schedules on Device Start

**Files:**
- Modify: `backend/app/simulation/engine.py` (`start_device` method)

- [ ] **Step 1: Load schedules from DB when starting device**

In `start_device()`, after loading configs (line 47), load anomaly schedules from DB and pass to anomaly_injector:

```python
async def start_device(self, device_id: UUID) -> None:
    """Start simulation for a device."""
    if device_id in self._device_tasks:
        logger.warning("Simulation already running for device %s", device_id)
        return

    configs, register_map, device_protocol = await self._load_device_data(device_id)

    if not configs:
        logger.info("No simulation configs for device %s, skipping", device_id)
        return

    # Load anomaly schedules
    schedules = await self._load_anomaly_schedules(device_id)
    from app.simulation import anomaly_injector
    anomaly_injector.load_schedules(device_id, schedules)

    interval = min(c.update_interval_ms for c in configs) / 1000.0
    task = asyncio.create_task(
        self._run_device(device_id, configs, register_map, device_protocol, interval),
        name=f"sim-{device_id}",
    )
    self._device_tasks[device_id] = task
    logger.info("Simulation started for device %s (interval=%.1fs)", device_id, interval)
```

Add the `_load_anomaly_schedules` method:

```python
async def _load_anomaly_schedules(self, device_id: UUID) -> list[dict]:
    """Load enabled anomaly schedules from DB."""
    async with async_session_factory() as session:
        from app.models.anomaly import AnomalySchedule
        stmt = select(AnomalySchedule).where(
            AnomalySchedule.device_id == device_id,
            AnomalySchedule.is_enabled.is_(True),
        )
        result = await session.execute(stmt)
        schedules = result.scalars().all()
        return [
            {
                "register_name": s.register_name,
                "anomaly_type": s.anomaly_type,
                "anomaly_params": s.anomaly_params,
                "trigger_after_seconds": s.trigger_after_seconds,
                "duration_seconds": s.duration_seconds,
            }
            for s in schedules
        ]
```

In `stop_device()`, also clear anomaly state:
```python
from app.simulation import anomaly_injector
anomaly_injector.clear_device(device_id)
```

- [ ] **Step 2: Run all tests**

Run: `cd backend && pytest -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app/simulation/engine.py
git commit -m "feat: load anomaly schedules on device start, clear on stop"
```

---

## Chunk 2: Phase 5.3 — Fault Integration + Integration Tests

### Task 9: Hook Fault Interception into Modbus Adapter

**Files:**
- Modify: `backend/app/protocols/modbus_tcp.py`

**pymodbus 3.12.1 interception mechanism (verified):**

`ModbusTcpServer` accepts `trace_pdu: Callable[[bool, ModbusPDU], ModbusPDU]` which is called on both send (bool=True) and receive (bool=False). The callback can **modify** the PDU by returning a different one.

However, `trace_pdu` cannot suppress responses entirely (needed for timeout). The actual request processing happens in `ServerRequestHandler.handle_request()` (in `pymodbus/server/requesthandler.py:79`), which calls `self.server_send(response, addr)`. `server_send` skips sending if the PDU is falsy (line 111-112).

**Approach:** Use `trace_pdu` for delay/exception faults (modify outgoing PDU), and for timeout/intermittent (suppress response), we need to intercept at a deeper level. Since `trace_pdu` is called inside `pdu_send` which is called by `server_send`, and `server_send` skips on falsy PDU, returning `None` from `trace_pdu(True, pdu)` would cause the frame builder to fail.

**Best approach: Override the server context's datastore access.** Create a fault-aware wrapper around `ModbusServerContext` that intercepts before the request is even processed:

- [ ] **Step 1: Create fault-aware trace_pdu callback**

Add to `modbus_tcp.py`:

```python
import asyncio
import random
import time

from pymodbus.pdu import ExceptionResponse
from pymodbus.constants import ExcCodes


class ModbusTcpAdapter:
    # ... existing code ...

    def _create_trace_pdu(self):
        """Create a trace_pdu callback for fault interception.

        trace_pdu signature: (sending: bool, pdu: ModbusPDU) -> ModbusPDU
        - sending=False: incoming request (can modify before processing)
        - sending=True: outgoing response (can replace with exception)
        """
        def trace_pdu(sending: bool, pdu):
            if not sending:
                # Incoming request — record for stats tracking
                return pdu

            # Outgoing response — apply faults
            dev_id = self._slave_to_device.get(pdu.dev_id)
            if dev_id is None:
                return pdu

            from app.simulation import fault_simulator
            fault = fault_simulator.get_fault(dev_id)
            if fault is None:
                return pdu

            match fault.fault_type:
                case "delay":
                    delay_ms = fault.params.get("delay_ms", 500)
                    time.sleep(delay_ms / 1000.0)  # Blocking sleep in sync callback
                    return pdu

                case "timeout":
                    # Return None-like — but trace_pdu must return a PDU.
                    # Instead, replace with an exception that pymodbus will
                    # handle. For true timeout, we'll use the dev_id skip approach.
                    return None  # server_send skips if pdu is falsy

                case "exception":
                    exc_code = fault.params.get("exception_code", ExcCodes.DEVICE_FAILURE)
                    return ExceptionResponse(pdu.function_code, exc_code)

                case "intermittent":
                    rate = fault.params.get("failure_rate", 0.5)
                    if random.random() < rate:
                        return None  # suppress response
                    return pdu

            return pdu

        return trace_pdu
```

**Note on `trace_pdu` returning None:** Looking at pymodbus source, `pdu_send` calls `self.framer.buildFrame(self.trace_pdu(True, pdu))`. If trace_pdu returns None, `buildFrame` will fail. For timeout/intermittent suppression, a different approach is needed.

**Revised approach — use `trace_pdu` for delay/exception, and modify the server context for timeout/intermittent:**

For timeout and intermittent faults, temporarily remove the slave from the context so `ServerRequestHandler.handle_request()` raises `NoSuchIdException`, which (with `ignore_missing_devices=True`) causes the server to silently ignore the request — the client times out.

```python
def _create_trace_pdu(self):
    """Fault interception via trace_pdu (for delay and exception faults)."""
    def trace_pdu(sending: bool, pdu):
        if not sending:
            # Incoming request — check for timeout/intermittent faults
            dev_id = self._slave_to_device.get(pdu.dev_id)
            if dev_id is not None:
                from app.simulation import fault_simulator
                fault = fault_simulator.get_fault(dev_id)
                if fault:
                    if fault.fault_type == "timeout":
                        # Remove slave temporarily so server ignores request
                        self._suppress_slave(pdu.dev_id)
                    elif fault.fault_type == "intermittent":
                        rate = fault.params.get("failure_rate", 0.5)
                        if random.random() < rate:
                            self._suppress_slave(pdu.dev_id)
            return pdu

        # Outgoing response — apply delay/exception faults
        dev_id = self._slave_to_device.get(pdu.dev_id)
        if dev_id is None:
            return pdu

        from app.simulation import fault_simulator
        fault = fault_simulator.get_fault(dev_id)
        if fault is None:
            return pdu

        if fault.fault_type == "delay":
            delay_ms = fault.params.get("delay_ms", 500)
            time.sleep(delay_ms / 1000.0)
        elif fault.fault_type == "exception":
            exc_code = fault.params.get("exception_code", ExcCodes.DEVICE_FAILURE)
            return ExceptionResponse(pdu.function_code, exc_code)

        return pdu

    return trace_pdu

def _suppress_slave(self, slave_id: int) -> None:
    """Temporarily remove a slave from the context to simulate no-response.
    Restore it after a short delay using asyncio."""
    if self._context and slave_id in self._slave_contexts:
        ctx = self._slave_contexts[slave_id]
        # Remove from server context
        self._context.remove(slave_id)
        # Schedule restoration
        async def _restore():
            await asyncio.sleep(0.1)
            if slave_id in self._slave_contexts:
                self._context[slave_id] = ctx
        try:
            asyncio.get_event_loop().create_task(_restore())
        except RuntimeError:
            pass  # No event loop — edge case in tests
```

- [ ] **Step 2: Update ModbusTcpServer creation to pass trace_pdu**

In the `start()` method of `ModbusTcpAdapter`, pass the trace_pdu callback:

```python
async def start(self) -> None:
    self._context = ModbusServerContext(devices={}, single=False)
    self._server = ModbusTcpServer(
        context=self._context,
        address=(self._host, self._port),
        ignore_missing_devices=True,
        trace_pdu=self._create_trace_pdu(),
    )
    self._server_task = asyncio.create_task(self._server.serve_forever())
    await asyncio.sleep(0.1)
```

- [ ] **Step 3: Run existing tests to ensure no regressions**

Run: `cd backend && pytest -v`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/protocols/modbus_tcp.py
git commit -m "feat: hook fault interception into Modbus TCP via trace_pdu"
```

---

### Task 10: Modbus Integration Tests

**Files:**
- Create: `backend/tests/test_modbus_integration.py`

- [ ] **Step 1: Write integration tests**

Create `backend/tests/test_modbus_integration.py`:

```python
"""Integration tests: Modbus TCP server with fault injection.

Starts a real Modbus TCP server, registers a slave with static data,
and uses pymodbus AsyncModbusTcpClient to verify fault behaviors.
"""

import asyncio
import struct
import time
import uuid

import pytest
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusIOException

from app.protocols.modbus_tcp import ModbusTcpAdapter
from app.simulation.fault_simulator import FaultConfig, FaultSimulator

TEST_PORT = 15502
SLAVE_ID = 1


@pytest.fixture
async def modbus_env():
    """Start Modbus adapter with one slave and static register data."""
    adapter = ModbusTcpAdapter(host="127.0.0.1", port=TEST_PORT)
    fault_sim = FaultSimulator()

    await adapter.start()

    # Register a slave with known register data
    device_id = uuid.uuid4()
    registers = [
        {"name": "voltage", "address": 0, "function_code": 4,
         "data_type": "float32", "byte_order": "big_endian"},
    ]
    await adapter.add_device(device_id, SLAVE_ID, registers)

    # Write a known value (230.0 as float32 = 0x4366_0000)
    await adapter.update_register(
        device_id, 0, 4, 230.0, "float32", "big_endian",
    )

    yield adapter, fault_sim, device_id

    fault_sim.clear_all()
    await adapter.stop()


@pytest.fixture
async def client():
    """Create a Modbus TCP client."""
    c = AsyncModbusTcpClient("127.0.0.1", port=TEST_PORT, timeout=3)
    await c.connect()
    yield c
    c.close()


class TestNormalRead:
    async def test_read_returns_correct_value(self, modbus_env, client) -> None:
        """Client reads the static value written to the datastore."""
        result = await client.read_input_registers(0, 2, slave=SLAVE_ID)
        assert not result.isError(), f"Modbus error: {result}"
        # Decode float32 from two 16-bit registers
        raw = struct.pack(">HH", result.registers[0], result.registers[1])
        value = struct.unpack(">f", raw)[0]
        assert abs(value - 230.0) < 0.01


class TestDelayFault:
    async def test_response_delayed(self, modbus_env, client) -> None:
        """Delay fault adds latency to response."""
        _, fault_sim, device_id = modbus_env
        fault_sim.set_fault(device_id, FaultConfig("delay", {"delay_ms": 500}))

        start = time.monotonic()
        result = await client.read_input_registers(0, 2, slave=SLAVE_ID)
        elapsed_ms = (time.monotonic() - start) * 1000

        assert not result.isError()
        assert elapsed_ms >= 450, f"Expected >= 450ms, got {elapsed_ms:.0f}ms"


class TestTimeoutFault:
    async def test_client_times_out(self, modbus_env, client) -> None:
        """Timeout fault causes no response — client times out."""
        _, fault_sim, device_id = modbus_env
        fault_sim.set_fault(device_id, FaultConfig("timeout", {}))

        # Use short timeout client
        short_client = AsyncModbusTcpClient(
            "127.0.0.1", port=TEST_PORT, timeout=1,
        )
        await short_client.connect()
        try:
            result = await short_client.read_input_registers(0, 2, slave=SLAVE_ID)
            # pymodbus returns error result on timeout
            assert result.isError()
        except (ModbusIOException, asyncio.TimeoutError):
            pass  # Expected
        finally:
            short_client.close()


class TestExceptionFault:
    async def test_returns_modbus_exception(self, modbus_env, client) -> None:
        """Exception fault returns a Modbus exception code."""
        _, fault_sim, device_id = modbus_env
        fault_sim.set_fault(
            device_id,
            FaultConfig("exception", {"exception_code": 0x02}),
        )

        result = await client.read_input_registers(0, 2, slave=SLAVE_ID)
        assert result.isError()
        assert result.exception_code == 0x02


class TestIntermittentFault:
    async def test_partial_failure(self, modbus_env, client) -> None:
        """Intermittent fault fails at approximately the configured rate."""
        _, fault_sim, device_id = modbus_env
        fault_sim.set_fault(
            device_id,
            FaultConfig("intermittent", {"failure_rate": 0.5}),
        )

        errors = 0
        total = 50
        for _ in range(total):
            try:
                result = await client.read_input_registers(0, 2, slave=SLAVE_ID)
                if result.isError():
                    errors += 1
            except (ModbusIOException, asyncio.TimeoutError):
                errors += 1

        # With 50% rate, expect 15-85% failure (wide margin for randomness)
        error_rate = errors / total
        assert 0.15 <= error_rate <= 0.85, (
            f"Expected ~50% failure, got {error_rate:.0%} ({errors}/{total})"
        )


class TestClearFault:
    async def test_normal_after_clear(self, modbus_env, client) -> None:
        """Clearing fault restores normal read behavior."""
        _, fault_sim, device_id = modbus_env

        # Set and clear fault
        fault_sim.set_fault(device_id, FaultConfig("exception", {"exception_code": 0x02}))
        fault_sim.clear_fault(device_id)

        result = await client.read_input_registers(0, 2, slave=SLAVE_ID)
        assert not result.isError()
```

- [ ] **Step 2: Run integration tests**

Run: `cd backend && pytest tests/test_modbus_integration.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_modbus_integration.py
git commit -m "test: add Modbus TCP integration tests for all fault types"
```

---

## Chunk 3: Phase 5.4 — Simulation Frontend

### Task 11: Frontend TypeScript Types + API Services

**Files:**
- Create: `frontend/src/types/simulation.ts`
- Create: `frontend/src/services/simulationApi.ts`
- Create: `frontend/src/services/anomalyApi.ts`
- Create: `frontend/src/services/faultApi.ts`

- [ ] **Step 1: Create TypeScript interfaces**

Create `frontend/src/types/simulation.ts` with all request/response types for simulation config, anomaly, and fault APIs. Follow the pattern in `frontend/src/types/device.ts`.

- [ ] **Step 2: Create API service files**

Create the three API service files following the pattern in `frontend/src/services/deviceApi.ts`:
- `simulationApi.ts` — getConfigs, setConfigs, patchConfig, deleteConfigs
- `anomalyApi.ts` — inject, getActive, remove, clearAll, getSchedules, setSchedules, deleteSchedules
- `faultApi.ts` — setFault, getFault, clearFault

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/simulation.ts frontend/src/services/simulationApi.ts frontend/src/services/anomalyApi.ts frontend/src/services/faultApi.ts
git commit -m "feat: add simulation/anomaly/fault TypeScript types and API services"
```

---

### Task 12: Simulation Zustand Store

**Files:**
- Create: `frontend/src/stores/simulationStore.ts`

- [ ] **Step 1: Create store**

Create `frontend/src/stores/simulationStore.ts` with Zustand. State includes: selected device ID, simulation configs, active anomalies, anomaly schedules, current fault. Actions: fetch/save configs, inject/remove anomalies, set/clear fault, fetch/save schedules.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/stores/simulationStore.ts
git commit -m "feat: add simulation Zustand store"
```

---

### Task 13: DataModeTab Component

**Files:**
- Create: `frontend/src/pages/Simulation/DataModeTab.tsx`

- [ ] **Step 1: Build DataModeTab**

Ant Design Table with one row per register. Columns: Register Name, Data Mode (Select), Parameters (dynamic form based on mode), Enabled (Switch), Interval (InputNumber). "Save All" button at bottom.

Dynamic params form: switch on data_mode to render appropriate form fields (static→value, random→base+amplitude+distribution, etc.).

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Simulation/DataModeTab.tsx
git commit -m "feat: add DataModeTab component for simulation config"
```

---

### Task 14: AnomalyTab Component

**Files:**
- Create: `frontend/src/pages/Simulation/AnomalyTab.tsx`

- [ ] **Step 1: Build AnomalyTab**

Two sections:
1. **Real-time Injection**: Form (register select, anomaly type select, dynamic params) + "Inject" button. Active anomalies table with "Remove" action.
2. **Schedule Management**: Editable table with "Add Row", "Save All", "Clear All".

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Simulation/AnomalyTab.tsx
git commit -m "feat: add AnomalyTab component for injection and schedules"
```

---

### Task 15: FaultTab Component

**Files:**
- Create: `frontend/src/pages/Simulation/FaultTab.tsx`

- [ ] **Step 1: Build FaultTab**

Device-level fault control: fault type select, dynamic params form, "Set Fault" button, current fault display with "Clear" button.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Simulation/FaultTab.tsx
git commit -m "feat: add FaultTab component for fault control"
```

---

### Task 16: SimulationPage Assembly

**Files:**
- Modify: `frontend/src/pages/Simulation/index.tsx`

- [ ] **Step 1: Replace placeholder with full page**

Device selector (Ant Design Select) at top + Ant Design Tabs with three tabs (Data Mode, Anomaly, Fault). Load device list on mount, fetch configs/anomalies/fault when device is selected.

- [ ] **Step 2: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Simulation/
git commit -m "feat: complete Simulation page with Data Mode, Anomaly, and Fault tabs"
```

---

## Chunk 4: Phase 6 — Real-time Monitor Dashboard

### Task 17: Communication Statistics in Modbus Adapter

**Files:**
- Modify: `backend/app/protocols/modbus_tcp.py`

- [ ] **Step 1: Add DeviceStats tracking**

Add `DeviceStats` dataclass and `_device_stats` dict to `ModbusTcpAdapter`. Increment counters in the request handler. Add `get_stats(device_id)` and `reset_stats(device_id)` public methods. Clear stats on device removal.

- [ ] **Step 2: Commit**

```bash
git add backend/app/protocols/modbus_tcp.py
git commit -m "feat: add per-device communication statistics tracking"
```

---

### Task 18: MonitorService + Event Log

**Files:**
- Create: `backend/app/services/monitor_service.py`

- [ ] **Step 1: Create MonitorService**

Module-level singleton. Contains:
- `_event_log: deque[EventLogEntry]` (maxlen=100)
- `log_event(device_id, device_name, event_type, detail)` — append to deque
- `get_events() -> list[EventLogEntry]` — return list copy
- `get_monitor_data()` — aggregate data from simulation_engine, anomaly_injector, fault_simulator, and protocol_manager for all running devices

- [ ] **Step 2: Add event logging calls to device_service**

In `device_service.py`, call `monitor_service.log_event()` on device start/stop.

- [ ] **Step 3: Add event logging calls to anomaly and fault routes**

In `anomaly.py` routes, log inject/remove/clear events.
In `simulation.py` routes, log fault set/clear events.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/monitor_service.py backend/app/services/device_service.py backend/app/api/routes/anomaly.py backend/app/api/routes/simulation.py
git commit -m "feat: add MonitorService with event log and data aggregation"
```

---

### Task 19: WebSocket Endpoint

**Files:**
- Create: `backend/app/api/websocket.py`
- Modify: `backend/app/main.py` (register WS route)

- [ ] **Step 1: Create WebSocket handler**

`backend/app/api/websocket.py`:
- `WebSocket /ws/monitor` endpoint
- Maintain set of connected clients
- Background task: every 1 second, call `monitor_service.get_monitor_data()`, broadcast JSON to all clients
- Handle disconnect gracefully

- [ ] **Step 2: Register in main.py**

Add the WebSocket route to the FastAPI app (at root level, not under api_v1_router).

- [ ] **Step 3: Add shutdown cleanup in lifespan**

In `lifespan()`, add WebSocket broadcast task cancellation before simulation engine shutdown.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/websocket.py backend/app/main.py
git commit -m "feat: add WebSocket /ws/monitor endpoint with 1s broadcast"
```

---

### Task 20: Monitor Frontend — useWebSocket Hook + Store

**Files:**
- Create: `frontend/src/hooks/useWebSocket.ts`
- Create: `frontend/src/stores/monitorStore.ts`

- [ ] **Step 1: Create useWebSocket hook**

Connect on mount, parse JSON messages, reconnect with exponential backoff on disconnect, cleanup on unmount.

- [ ] **Step 2: Create monitorStore**

Zustand store: `devices` (from WS), `events` (from WS), `registerHistory` (rolling buffer per device+register, max 300 points). Update on each WS message.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useWebSocket.ts frontend/src/stores/monitorStore.ts
git commit -m "feat: add WebSocket hook and monitor Zustand store"
```

---

### Task 21: Monitor Dashboard Page

**Files:**
- Create: `frontend/src/pages/Monitor/index.tsx`
- Create: `frontend/src/pages/Monitor/DeviceCardGrid.tsx`
- Create: `frontend/src/pages/Monitor/DeviceDetailPanel.tsx`
- Create: `frontend/src/pages/Monitor/RegisterChart.tsx`
- Create: `frontend/src/pages/Monitor/EventLog.tsx`

- [ ] **Step 1: Build DeviceCardGrid**

Grid of cards, one per device. Status dot (green/gray/red), name, slave_id, key metrics, anomaly/fault badges.

- [ ] **Step 2: Build DeviceDetailPanel**

Shown on card click. Register table (live), RegisterChart (Recharts LineChart, 5-min rolling), stats summary, anomaly/fault badges.

- [ ] **Step 3: Build RegisterChart**

Recharts `<LineChart>` rendering from `monitorStore.registerHistory`. X-axis: time, Y-axis: value. Auto-scroll.

- [ ] **Step 4: Build EventLog**

Scrollable list of recent events from monitorStore.events.

- [ ] **Step 5: Assemble MonitorPage**

Layout: DeviceCardGrid top, DeviceDetailPanel bottom (conditional), EventLog as collapsible panel.

- [ ] **Step 6: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Monitor/
git commit -m "feat: complete Monitor Dashboard with cards, charts, and event log"
```

---

## Chunk 5: Phase 7 — System Finalization

### Task 22: Docker Compose Production Config

**Files:**
- Modify: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Update docker-compose.yml**

Add health checks, restart policies, named volumes, env_file reference.

- [ ] **Step 2: Create .env.example**

All configurable variables with descriptions.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "chore: add production Docker Compose config and .env.example"
```

---

### Task 23: README Quick Start

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Add Quick Start section (clone → .env → docker compose up → open browser), Data Collector Integration section (Modbus TCP + REST API pointers).

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README with quick start and data collector integration guide"
```

---

### Task 24: Ruff Configuration + GitHub Actions CI

**Files:**
- Create: `backend/pyproject.toml` (or update if exists)
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Add ruff config**

Create/update `backend/pyproject.toml` with `[tool.ruff]` section (line-length=100, target=py312, select E/F/W/I).

- [ ] **Step 2: Verify ruff passes**

Run: `cd backend && pip install ruff && ruff check .`
Expected: No errors (or fix any that appear).

- [ ] **Step 3: Create CI workflow**

`.github/workflows/ci.yml`: trigger on push to dev/main and PR to main. Backend job (Python 3.12, postgres service, ruff + pytest). Frontend job (Node 20, tsc --noEmit, npm run build).

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml .github/workflows/ci.yml
git commit -m "chore: add ruff config and GitHub Actions CI pipeline"
```

---

### Task 25: Update Development Phases + Phase 8

**Files:**
- Modify: `docs/development-phases.md`

- [ ] **Step 1: Update phase statuses**

Mark Phase 5 as ✅ Complete, Phase 6 as ✅ Complete, Phase 7 as ✅ Complete. Add Phase 8 (Post-MVP) section listing deferred items.

- [ ] **Step 2: Commit**

```bash
git add docs/development-phases.md
git commit -m "docs: update development phases — mark 5-7 complete, add Phase 8 roadmap"
```
