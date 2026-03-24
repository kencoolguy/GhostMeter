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
