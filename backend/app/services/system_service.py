"""System-level service for config export/import."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ValidationException
from app.models.anomaly import AnomalySchedule
from app.models.device import DeviceInstance
from app.models.simulation import SimulationConfig
from app.models.template import DeviceTemplate, RegisterDefinition
from app.schemas.system import (
    AnomalyScheduleExport,
    DeviceExport,
    ImportResult,
    RegisterExport,
    SimulationConfigExport,
    SystemExport,
    SystemImport,
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


async def import_system(session: AsyncSession, data: SystemImport) -> ImportResult:
    """Import full system config from a snapshot. All-or-nothing transaction."""
    result = ImportResult()

    # Step 1: Import templates
    template_name_to_id: dict[str, uuid.UUID] = {}

    # Load existing templates for upsert lookup
    stmt = select(DeviceTemplate).options(selectinload(DeviceTemplate.registers))
    existing = await session.execute(stmt)
    existing_templates = {t.name: t for t in existing.scalars().all()}

    for t_export in data.templates:
        if t_export.is_builtin:
            result.templates_skipped += 1
            # Still map the name→id for device resolution
            if t_export.name in existing_templates:
                template_name_to_id[t_export.name] = existing_templates[t_export.name].id
            continue

        if t_export.name in existing_templates:
            # Update existing template
            existing_t = existing_templates[t_export.name]
            existing_t.protocol = t_export.protocol
            existing_t.description = t_export.description

            # Replace registers: delete old, add new
            await session.execute(
                delete(RegisterDefinition).where(
                    RegisterDefinition.template_id == existing_t.id
                )
            )
            for r in t_export.registers:
                session.add(
                    RegisterDefinition(
                        template_id=existing_t.id,
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
                )
            template_name_to_id[t_export.name] = existing_t.id
            result.templates_updated += 1
        else:
            # Create new template
            new_t = DeviceTemplate(
                name=t_export.name,
                protocol=t_export.protocol,
                description=t_export.description,
                is_builtin=False,
            )
            session.add(new_t)
            await session.flush()  # Get the ID

            for r in t_export.registers:
                session.add(
                    RegisterDefinition(
                        template_id=new_t.id,
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
                )
            template_name_to_id[t_export.name] = new_t.id
            result.templates_created += 1

    # Also map existing built-in templates not in export
    for name, t in existing_templates.items():
        if name not in template_name_to_id:
            template_name_to_id[name] = t.id

    await session.flush()

    # Step 2: Import devices
    device_name_to_id: dict[str, uuid.UUID] = {}

    # Load existing devices for upsert lookup
    stmt = select(DeviceInstance)
    existing = await session.execute(stmt)
    existing_devices = {(d.slave_id, d.port): d for d in existing.scalars().all()}

    for d_export in data.devices:
        template_id = template_name_to_id.get(d_export.template_name)
        if template_id is None:
            raise ValidationException(
                detail=f"Device '{d_export.name}' references unknown template "
                f"'{d_export.template_name}'"
            )

        key = (d_export.slave_id, d_export.port)
        if key in existing_devices:
            # Update existing device
            existing_d = existing_devices[key]
            existing_d.name = d_export.name
            existing_d.template_id = template_id
            existing_d.description = d_export.description
            if existing_d.status == "running":
                existing_d.status = "stopped"
            device_name_to_id[d_export.name] = existing_d.id
            result.devices_updated += 1
        else:
            # Create new device
            new_d = DeviceInstance(
                name=d_export.name,
                template_id=template_id,
                slave_id=d_export.slave_id,
                port=d_export.port,
                description=d_export.description,
                status="stopped",
            )
            session.add(new_d)
            await session.flush()
            device_name_to_id[d_export.name] = new_d.id
            result.devices_created += 1

    await session.flush()

    # Also map existing devices not in import
    for key, d in existing_devices.items():
        if d.name not in device_name_to_id:
            device_name_to_id[d.name] = d.id

    # Step 3: Import simulation configs (delete once per device, then insert all)
    sim_devices_cleared: set[str] = set()
    for sc_export in data.simulation_configs:
        device_id = device_name_to_id.get(sc_export.device_name)
        if device_id is None:
            continue

        if sc_export.device_name not in sim_devices_cleared:
            await session.execute(
                delete(SimulationConfig).where(SimulationConfig.device_id == device_id)
            )
            sim_devices_cleared.add(sc_export.device_name)

        session.add(
            SimulationConfig(
                device_id=device_id,
                register_name=sc_export.register_name,
                data_mode=sc_export.data_mode,
                mode_params=sc_export.mode_params,
                is_enabled=sc_export.is_enabled,
                update_interval_ms=sc_export.update_interval_ms,
            )
        )
        result.simulation_configs_set += 1

    # Step 4: Import anomaly schedules
    sched_devices_cleared: set[str] = set()
    for s_export in data.anomaly_schedules:
        device_id = device_name_to_id.get(s_export.device_name)
        if device_id is None:
            continue

        if s_export.device_name not in sched_devices_cleared:
            await session.execute(
                delete(AnomalySchedule).where(AnomalySchedule.device_id == device_id)
            )
            sched_devices_cleared.add(s_export.device_name)

        session.add(
            AnomalySchedule(
                device_id=device_id,
                register_name=s_export.register_name,
                anomaly_type=s_export.anomaly_type,
                anomaly_params=s_export.anomaly_params,
                trigger_after_seconds=s_export.trigger_after_seconds,
                duration_seconds=s_export.duration_seconds,
                is_enabled=s_export.is_enabled,
            )
        )
        result.anomaly_schedules_set += 1

    await session.commit()
    return result
