"""Pydantic schemas for simulation profile API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.simulation import SimulationConfigCreate

# Reuse SimulationConfigCreate — identical fields and validators
ProfileConfigEntry = SimulationConfigCreate


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


class SimulationProfileExport(BaseModel):
    """Schema for profile export/import as standalone JSON file."""

    name: str
    description: str | None = None
    template_name: str = ""
    configs: list[dict[str, Any]]


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
