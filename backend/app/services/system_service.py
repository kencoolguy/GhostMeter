"""System-level service for config export/import."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.anomaly import AnomalySchedule
from app.models.device import DeviceInstance
from app.models.simulation import SimulationConfig
from app.models.template import DeviceTemplate
from app.schemas.system import (
    AnomalyScheduleExport,
    DeviceExport,
    RegisterExport,
    SimulationConfigExport,
    SystemExport,
    TemplateExport,
)


async def export_system(session: AsyncSession) -> SystemExport:
    """Export full system config as a snapshot."""
    # Templates with registers
    stmt = select(DeviceTemplate).options(selectinload(DeviceTemplate.registers))
    result = await session.execute(stmt)
    templates = result.scalars().all()

    template_exports = []
    for t in templates:
        template_exports.append(
            TemplateExport(
                name=t.name,
                protocol=t.protocol,
                description=t.description,
                is_builtin=t.is_builtin,
                registers=[
                    RegisterExport(
                        name=r.name,
                        address=r.address,
                        function_code=r.function_code,
                        data_type=r.data_type,
                        byte_order=r.byte_order,
                        scale_factor=r.scale_factor,
                        unit=r.unit,
                        description=r.description,
                        sort_order=r.sort_order,
                    )
                    for r in t.registers
                ],
            )
        )

    # Devices — build id→name map for later use
    stmt = (
        select(DeviceInstance, DeviceTemplate.name)
        .join(DeviceTemplate, DeviceInstance.template_id == DeviceTemplate.id)
    )
    result = await session.execute(stmt)
    rows = result.all()

    device_id_to_name: dict[uuid.UUID, str] = {}
    device_exports = []
    for device, template_name in rows:
        device_id_to_name[device.id] = device.name
        device_exports.append(
            DeviceExport(
                name=device.name,
                template_name=template_name,
                slave_id=device.slave_id,
                port=device.port,
                description=device.description,
            )
        )

    # Simulation configs
    stmt = select(SimulationConfig)
    result = await session.execute(stmt)
    sim_configs = result.scalars().all()

    sim_exports = []
    for sc in sim_configs:
        device_name = device_id_to_name.get(sc.device_id)
        if device_name is None:
            continue
        sim_exports.append(
            SimulationConfigExport(
                device_name=device_name,
                register_name=sc.register_name,
                data_mode=sc.data_mode,
                mode_params=sc.mode_params,
                is_enabled=sc.is_enabled,
                update_interval_ms=sc.update_interval_ms,
            )
        )

    # Anomaly schedules
    stmt = select(AnomalySchedule)
    result = await session.execute(stmt)
    schedules = result.scalars().all()

    schedule_exports = []
    for s in schedules:
        device_name = device_id_to_name.get(s.device_id)
        if device_name is None:
            continue
        schedule_exports.append(
            AnomalyScheduleExport(
                device_name=device_name,
                register_name=s.register_name,
                anomaly_type=s.anomaly_type,
                anomaly_params=s.anomaly_params,
                trigger_after_seconds=s.trigger_after_seconds,
                duration_seconds=s.duration_seconds,
                is_enabled=s.is_enabled,
            )
        )

    return SystemExport(
        version="1.0",
        exported_at=datetime.now(UTC).isoformat(),
        templates=template_exports,
        devices=device_exports,
        simulation_configs=sim_exports,
        anomaly_schedules=schedule_exports,
    )
