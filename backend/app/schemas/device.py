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
    profile_id: UUID | None = None  # See model_fields_set for absent vs null

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
    profile_id: UUID | None = None  # See model_fields_set for absent vs null

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
