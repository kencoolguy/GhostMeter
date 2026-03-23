"""Pydantic schemas for simulation configuration API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


VALID_DATA_MODES = {"static", "random", "daily_curve", "computed", "accumulator"}
VALID_FAULT_TYPES = {"delay", "timeout", "exception", "intermittent"}


class SimulationConfigCreate(BaseModel):
    """Schema for a single register simulation config."""

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


class SimulationConfigBatchSet(BaseModel):
    """Schema for batch setting all simulation configs for a device."""

    configs: list[SimulationConfigCreate]


class SimulationConfigResponse(BaseModel):
    """Schema for a simulation config in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    device_id: UUID
    register_name: str
    data_mode: str
    mode_params: dict[str, Any]
    is_enabled: bool
    update_interval_ms: int
    created_at: datetime
    updated_at: datetime


class FaultConfigSet(BaseModel):
    """Schema for setting a fault on a device."""

    fault_type: str
    params: dict[str, Any] = {}

    @field_validator("fault_type")
    @classmethod
    def validate_fault_type(cls, v: str) -> str:
        if v not in VALID_FAULT_TYPES:
            raise ValueError(f"fault_type must be one of {VALID_FAULT_TYPES}")
        return v


class FaultConfigResponse(BaseModel):
    """Schema for fault state in API responses."""

    fault_type: str
    params: dict[str, Any]
