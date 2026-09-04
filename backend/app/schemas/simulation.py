"""Pydantic schemas for simulation configuration API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.simulation.aggregate import AGGREGATE_OPS, DEFAULT_ON_MISSING, ON_MISSING_MODES

VALID_DATA_MODES = {"static", "random", "daily_curve", "computed", "accumulator", "aggregate"}
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

    @model_validator(mode="after")
    def validate_aggregate_params(self) -> "SimulationConfigCreate":
        """Structural checks for ``aggregate`` mode_params (op / sources / on_missing).

        Existence of the referenced devices and registers, plus cycle detection,
        need the DB and live in ``simulation_service``. Rejecting shape errors
        here returns a 422 at the API boundary instead of a silent 0.0 in the
        engine.
        """
        if self.data_mode != "aggregate":
            return self
        params = self.mode_params

        op = params.setdefault("op", "sum")
        if op not in AGGREGATE_OPS:
            raise ValueError(f"aggregate op must be one of {list(AGGREGATE_OPS)}")

        sources = params.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError("aggregate sources must be a non-empty list of device names/ids")
        if not all(isinstance(s, str) and s.strip() for s in sources):
            raise ValueError("aggregate sources must be non-empty strings")
        if len(set(sources)) != len(sources):
            raise ValueError("aggregate sources must not contain duplicates")

        register = params.get("register")
        if register is not None and (not isinstance(register, str) or not register.strip()):
            raise ValueError("aggregate register must be a non-empty string when given")

        weight_register = params.get("weight_register")
        if op == "weighted_avg":
            if not isinstance(weight_register, str) or not weight_register.strip():
                raise ValueError("aggregate weighted_avg requires a weight_register")
        elif weight_register is not None:
            raise ValueError("aggregate weight_register is only valid with op weighted_avg")

        on_missing = params.setdefault("on_missing", DEFAULT_ON_MISSING)
        if on_missing not in ON_MISSING_MODES:
            raise ValueError(f"aggregate on_missing must be one of {list(ON_MISSING_MODES)}")
        return self


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

    @model_validator(mode="after")
    def validate_params(self) -> "FaultConfigSet":
        """Validate fault_type-specific params so malformed input is rejected with a
        422 at the API boundary instead of raising deep inside a protocol adapter."""
        if self.fault_type == "delay" and "delay_ms" in self.params:
            try:
                delay_ms = int(self.params["delay_ms"])
            except (TypeError, ValueError):
                raise ValueError("delay_ms must be an integer number of milliseconds")
            if delay_ms < 0:
                raise ValueError("delay_ms must be >= 0")
            self.params["delay_ms"] = delay_ms
        if self.fault_type == "intermittent" and "failure_rate" in self.params:
            try:
                rate = float(self.params["failure_rate"])
            except (TypeError, ValueError):
                raise ValueError("failure_rate must be a number between 0.0 and 1.0")
            if not 0.0 <= rate <= 1.0:
                raise ValueError("failure_rate must be between 0.0 and 1.0")
            self.params["failure_rate"] = rate
        return self


class FaultConfigResponse(BaseModel):
    """Schema for fault state in API responses."""

    fault_type: str
    params: dict[str, Any]
