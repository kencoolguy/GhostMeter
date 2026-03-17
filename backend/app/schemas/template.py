from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


# --- Data type → register count mapping ---

DATA_TYPE_REGISTER_COUNT: dict[str, int] = {
    "int16": 1,
    "uint16": 1,
    "int32": 2,
    "uint32": 2,
    "float32": 2,
    "float64": 4,
}

VALID_DATA_TYPES = set(DATA_TYPE_REGISTER_COUNT.keys())

VALID_BYTE_ORDERS = {
    "big_endian",
    "little_endian",
    "big_endian_word_swap",
    "little_endian_word_swap",
}

VALID_FUNCTION_CODES = {3, 4}


# --- Request Schemas ---

class RegisterDefinitionCreate(BaseModel):
    """Schema for creating a register definition."""

    name: str
    address: int
    function_code: int = 3
    data_type: str
    byte_order: str = "big_endian"
    scale_factor: float = 1.0
    unit: str | None = None
    description: str | None = None
    sort_order: int = 0

    @field_validator("data_type")
    @classmethod
    def validate_data_type(cls, v: str) -> str:
        if v not in VALID_DATA_TYPES:
            raise ValueError(
                f"Invalid data_type '{v}'. Must be one of: {sorted(VALID_DATA_TYPES)}"
            )
        return v

    @field_validator("byte_order")
    @classmethod
    def validate_byte_order(cls, v: str) -> str:
        if v not in VALID_BYTE_ORDERS:
            raise ValueError(
                f"Invalid byte_order '{v}'. Must be one of: {sorted(VALID_BYTE_ORDERS)}"
            )
        return v

    @field_validator("function_code")
    @classmethod
    def validate_function_code(cls, v: int) -> int:
        if v not in VALID_FUNCTION_CODES:
            raise ValueError(
                f"Invalid function_code {v}. Must be one of: {sorted(VALID_FUNCTION_CODES)}"
            )
        return v

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Address must be >= 0")
        return v


class TemplateCreate(BaseModel):
    """Schema for creating a device template."""

    name: str
    protocol: str = "modbus_tcp"
    description: str | None = None
    registers: list[RegisterDefinitionCreate]

    @field_validator("registers")
    @classmethod
    def validate_registers_not_empty(
        cls, v: list[RegisterDefinitionCreate],
    ) -> list[RegisterDefinitionCreate]:
        if not v:
            raise ValueError("Template must have at least one register")
        return v


class TemplateUpdate(BaseModel):
    """Schema for updating a device template (full replacement)."""

    name: str
    protocol: str = "modbus_tcp"
    description: str | None = None
    registers: list[RegisterDefinitionCreate]

    @field_validator("registers")
    @classmethod
    def validate_registers_not_empty(
        cls, v: list[RegisterDefinitionCreate],
    ) -> list[RegisterDefinitionCreate]:
        if not v:
            raise ValueError("Template must have at least one register")
        return v


class TemplateClone(BaseModel):
    """Schema for cloning a template."""

    new_name: str | None = None


# --- Response Schemas ---

class RegisterDefinitionResponse(BaseModel):
    """Schema for register definition in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    address: int
    function_code: int
    data_type: str
    byte_order: str
    scale_factor: float
    unit: str | None
    description: str | None
    sort_order: int


class TemplateSummary(BaseModel):
    """Schema for template list items (without full registers)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    protocol: str
    description: str | None
    is_builtin: bool
    register_count: int
    created_at: datetime
    updated_at: datetime


class TemplateDetail(BaseModel):
    """Schema for full template detail (with registers)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    protocol: str
    description: str | None
    is_builtin: bool
    registers: list[RegisterDefinitionResponse]
    created_at: datetime
    updated_at: datetime
