"""Pydantic schemas for scenario mode API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.anomaly import VALID_ANOMALY_TYPES


class ScenarioStepCreate(BaseModel):
    """Schema for creating a single scenario step."""

    register_name: str
    anomaly_type: str
    anomaly_params: dict[str, Any] = {}
    trigger_at_seconds: int
    duration_seconds: int
    sort_order: int = 0

    @field_validator("anomaly_type")
    @classmethod
    def validate_anomaly_type(cls, v: str) -> str:
        if v not in VALID_ANOMALY_TYPES:
            raise ValueError(f"anomaly_type must be one of {VALID_ANOMALY_TYPES}")
        return v

    @field_validator("trigger_at_seconds")
    @classmethod
    def validate_trigger_at_seconds(cls, v: int) -> int:
        if v < 0:
            raise ValueError("trigger_at_seconds must be >= 0")
        return v

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration_seconds(cls, v: int) -> int:
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
    """Schema for updating a scenario."""

    name: str
    description: str | None = None
    steps: list[ScenarioStepCreate]


class ScenarioStepResponse(BaseModel):
    """Response schema for a scenario step."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    register_name: str
    anomaly_type: str
    anomaly_params: dict[str, Any]
    trigger_at_seconds: int
    duration_seconds: int
    sort_order: int


class ScenarioSummary(BaseModel):
    """Summary response for a scenario (list view)."""

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
    """Detail response for a scenario (includes steps)."""

    steps: list[ScenarioStepResponse]


class ScenarioExport(BaseModel):
    """Schema for exporting a scenario as portable JSON."""

    name: str
    description: str | None
    template_name: str
    steps: list[ScenarioStepCreate]


class ActiveStepStatus(BaseModel):
    """Status of a currently active step during execution."""

    register_name: str
    anomaly_type: str
    remaining_seconds: int


class ScenarioExecutionStatus(BaseModel):
    """Real-time execution status of a running scenario."""

    scenario_id: UUID
    scenario_name: str
    status: str
    elapsed_seconds: int
    total_duration_seconds: int
    active_steps: list[ActiveStepStatus]
