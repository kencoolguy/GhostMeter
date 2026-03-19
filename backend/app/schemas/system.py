"""Pydantic schemas for system config export/import."""

from typing import Any

from pydantic import BaseModel, field_validator


class RegisterExport(BaseModel):
    """Register definition in export format (no IDs)."""

    name: str
    address: int
    function_code: int
    data_type: str
    byte_order: str
    scale_factor: float
    unit: str | None = None
    description: str | None = None
    sort_order: int = 0


class TemplateExport(BaseModel):
    """Template in export format (no IDs)."""

    name: str
    protocol: str
    description: str | None = None
    is_builtin: bool
    registers: list[RegisterExport]


class DeviceExport(BaseModel):
    """Device instance in export format (references template by name)."""

    name: str
    template_name: str
    slave_id: int
    port: int = 502
    description: str | None = None


class SimulationConfigExport(BaseModel):
    """Simulation config in export format (references device by name)."""

    device_name: str
    register_name: str
    data_mode: str
    mode_params: dict[str, Any] = {}
    is_enabled: bool = True
    update_interval_ms: int = 1000


class AnomalyScheduleExport(BaseModel):
    """Anomaly schedule in export format (references device by name)."""

    device_name: str
    register_name: str
    anomaly_type: str
    anomaly_params: dict[str, Any] = {}
    trigger_after_seconds: int
    duration_seconds: int
    is_enabled: bool = True


class SystemExport(BaseModel):
    """Full system snapshot for export."""

    version: str = "1.0"
    exported_at: str
    templates: list[TemplateExport]
    devices: list[DeviceExport]
    simulation_configs: list[SimulationConfigExport]
    anomaly_schedules: list[AnomalyScheduleExport]


class SystemImport(BaseModel):
    """Full system snapshot for import."""

    version: str
    templates: list[TemplateExport] = []
    devices: list[DeviceExport] = []
    simulation_configs: list[SimulationConfigExport] = []
    anomaly_schedules: list[AnomalyScheduleExport] = []

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if v != "1.0":
            raise ValueError(f"Unsupported export version '{v}'. Only '1.0' is supported.")
        return v


class ImportResult(BaseModel):
    """Result summary of an import operation."""

    templates_created: int = 0
    templates_updated: int = 0
    templates_skipped: int = 0
    devices_created: int = 0
    devices_updated: int = 0
    simulation_configs_set: int = 0
    anomaly_schedules_set: int = 0
