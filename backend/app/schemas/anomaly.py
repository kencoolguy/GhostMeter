"""Pydantic schemas for anomaly injection API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


VALID_ANOMALY_TYPES = {"spike", "drift", "flatline", "out_of_range", "data_loss"}

_REQUIRED_PARAMS: dict[str, list[str]] = {
    "spike": ["multiplier", "probability"],
    "drift": ["drift_per_second", "max_drift"],
    "flatline": [],
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
