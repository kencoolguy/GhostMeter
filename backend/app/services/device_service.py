import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ConflictException, NotFoundException, ValidationException
from app.protocols import protocol_manager
from app.protocols.base import RegisterInfo
from app.services import mqtt_service, simulation_profile_service
from app.simulation import simulation_engine
from app.models.device import DeviceInstance
from app.models.mqtt import MqttPublishConfig
from app.models.template import DeviceTemplate
from app.schemas.device import (
    DeviceBatchCreate,
    DeviceCreate,
    DeviceUpdate,
    RegisterValue,
)

logger = logging.getLogger(__name__)


async def _get_device_raw(
    session: AsyncSession, device_id: uuid.UUID,
) -> DeviceInstance:
    """Get device ORM object or raise 404."""
    stmt = select(DeviceInstance).where(DeviceInstance.id == device_id)
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()
    if device is None:
        raise NotFoundException(
            detail="Device not found", error_code="DEVICE_NOT_FOUND"
        )
    return device


async def _check_slave_id_available(
    session: AsyncSession,
    slave_id: int,
    port: int,
    exclude_device_id: uuid.UUID | None = None,
) -> None:
    """Raise 422 if slave_id is already in use on this port."""
    stmt = select(DeviceInstance).where(
        DeviceInstance.slave_id == slave_id,
        DeviceInstance.port == port,
    )
    if exclude_device_id:
        stmt = stmt.where(DeviceInstance.id != exclude_device_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise ValidationException(
            f"Slave ID {slave_id} is already in use on port {port}"
        )


async def _get_template_or_404(
    session: AsyncSession, template_id: uuid.UUID,
) -> DeviceTemplate:
    """Get template or raise 404."""
    stmt = (
        select(DeviceTemplate)
        .options(selectinload(DeviceTemplate.registers))
        .where(DeviceTemplate.id == template_id)
    )
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundException(
            detail="Template not found", error_code="TEMPLATE_NOT_FOUND"
        )
    return template


def _device_to_summary(
    device: DeviceInstance,
    template_name: str,
    mqtt_publishing: bool = False,
) -> dict:
    """Convert device ORM to summary dict."""
    return {
        "id": device.id,
        "template_id": device.template_id,
        "template_name": template_name,
        "name": device.name,
        "slave_id": device.slave_id,
        "status": device.status,
        "port": device.port,
        "description": device.description,
        "mqtt_publishing": mqtt_publishing,
        "created_at": device.created_at,
        "updated_at": device.updated_at,
    }


async def _resolve_and_apply_profile(
    session: AsyncSession,
    device_id: uuid.UUID,
    template_id: uuid.UUID,
    data: DeviceCreate | DeviceBatchCreate,
) -> None:
    """Resolve the profile to apply and expand into simulation_configs."""
    profile = None

    if "profile_id" in data.model_fields_set:
        if data.profile_id is not None:
            profile = await simulation_profile_service.get_profile(
                session, data.profile_id,
            )
            if profile.template_id != template_id:
                raise ValidationException(
                    "Profile does not belong to the device's template"
                )
    else:
        profile = await simulation_profile_service.get_default_profile(
            session, template_id,
        )

    if profile is not None:
        await simulation_profile_service.apply_profile_to_device(
            session, profile, device_id,
        )


async def list_devices(session: AsyncSession) -> list[dict]:
    """List all devices with template name and MQTT publishing status."""
    stmt = (
        select(
            DeviceInstance,
            DeviceTemplate.name.label("template_name"),
            MqttPublishConfig.enabled.label("mqtt_enabled"),
        )
        .join(DeviceTemplate, DeviceInstance.template_id == DeviceTemplate.id)
        .outerjoin(
            MqttPublishConfig,
            DeviceInstance.id == MqttPublishConfig.device_id,
        )
        .order_by(DeviceInstance.created_at)
    )
    result = await session.execute(stmt)
    return [
        _device_to_summary(
            row.DeviceInstance,
            row.template_name,
            mqtt_publishing=bool(row.mqtt_enabled),
        )
        for row in result.all()
    ]


async def get_device(session: AsyncSession, device_id: uuid.UUID) -> dict:
    """Get a single device with template name."""
    stmt = (
        select(DeviceInstance, DeviceTemplate.name.label("template_name"))
        .join(DeviceTemplate, DeviceInstance.template_id == DeviceTemplate.id)
        .where(DeviceInstance.id == device_id)
    )
    result = await session.execute(stmt)
    row = result.one_or_none()
    if row is None:
        raise NotFoundException(
            detail="Device not found", error_code="DEVICE_NOT_FOUND"
        )
    return _device_to_summary(row.DeviceInstance, row.template_name)


async def get_device_detail(session: AsyncSession, device_id: uuid.UUID) -> dict:
    """Get device with template registers (value=None)."""
    device_data = await get_device(session, device_id)

    # Get template registers
    template = await _get_template_or_404(session, device_data["template_id"])
    registers = [
        RegisterValue(
            name=reg.name,
            address=reg.address,
            function_code=reg.function_code,
            data_type=reg.data_type,
            byte_order=reg.byte_order,
            scale_factor=reg.scale_factor,
            unit=reg.unit,
            description=reg.description,
            oid=reg.oid,
            value=None,
        ).model_dump()
        for reg in template.registers
    ]

    return {**device_data, "registers": registers}


async def create_device(
    session: AsyncSession, data: DeviceCreate,
) -> dict:
    """Create a single device."""
    await _get_template_or_404(session, data.template_id)
    await _check_slave_id_available(session, data.slave_id, data.port)

    device = DeviceInstance(
        template_id=data.template_id,
        name=data.name,
        slave_id=data.slave_id,
        port=data.port,
        description=data.description,
    )
    session.add(device)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValidationException(f"Database constraint violation: {e}") from e
    await session.refresh(device)

    await _resolve_and_apply_profile(session, device.id, data.template_id, data)
    await session.commit()

    return await get_device(session, device.id)


async def batch_create_devices(
    session: AsyncSession, data: DeviceBatchCreate,
) -> list[dict]:
    """Batch create devices. Atomic — all or nothing."""
    if data.slave_id_start > data.slave_id_end:
        raise ValidationException("slave_id_start must be <= slave_id_end")

    count = data.slave_id_end - data.slave_id_start + 1
    if count > 50:
        raise ValidationException("Batch create limited to 50 devices")

    template = await _get_template_or_404(session, data.template_id)

    # Check all slave IDs are available
    for sid in range(data.slave_id_start, data.slave_id_end + 1):
        await _check_slave_id_available(session, sid, data.port)

    # Build name prefix
    prefix = data.name_prefix or template.name

    devices = []
    for sid in range(data.slave_id_start, data.slave_id_end + 1):
        if data.name_prefix:
            name = f"{prefix} {sid}"
        else:
            name = f"{prefix} - Slave {sid}"

        if len(name) > 200:
            raise ValidationException(
                f"Generated name '{name}' exceeds 200 character limit"
            )

        device = DeviceInstance(
            template_id=data.template_id,
            name=name,
            slave_id=sid,
            port=data.port,
            description=data.description,
        )
        session.add(device)
        devices.append(device)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValidationException(f"Database constraint violation: {e}") from e

    # Refresh and apply profiles
    result = []
    for device in devices:
        await session.refresh(device)
        await _resolve_and_apply_profile(session, device.id, data.template_id, data)
    await session.commit()

    for device in devices:
        result.append(await get_device(session, device.id))
    return result


async def update_device(
    session: AsyncSession, device_id: uuid.UUID, data: DeviceUpdate,
) -> dict:
    """Update a device. Running devices cannot be updated."""
    device = await _get_device_raw(session, device_id)

    if device.status == "running":
        raise ConflictException(
            detail="Cannot update a running device",
            error_code="DEVICE_RUNNING",
        )

    await _check_slave_id_available(
        session, data.slave_id, data.port, exclude_device_id=device_id
    )

    device.name = data.name
    device.slave_id = data.slave_id
    device.port = data.port
    device.description = data.description

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValidationException(f"Database constraint violation: {e}") from e

    return await get_device(session, device.id)


async def delete_device(
    session: AsyncSession, device_id: uuid.UUID,
) -> None:
    """Delete a device. Running devices cannot be deleted."""
    device = await _get_device_raw(session, device_id)

    if device.status == "running":
        raise ConflictException(
            detail="Cannot delete a running device",
            error_code="DEVICE_RUNNING",
        )

    await session.delete(device)
    await session.commit()


async def start_device(
    session: AsyncSession, device_id: uuid.UUID,
) -> dict:
    """Start a device (stopped → running). Registers slave in protocol adapter."""
    device = await _get_device_raw(session, device_id)

    if device.status != "stopped":
        raise ConflictException(
            detail=f"Device is already {device.status}",
            error_code="INVALID_STATE_TRANSITION",
        )

    # Load template with registers for protocol adapter
    template = await _get_template_or_404(session, device.template_id)
    register_infos = [
        RegisterInfo(
            address=reg.address,
            function_code=reg.function_code,
            data_type=reg.data_type,
            byte_order=reg.byte_order,
            oid=reg.oid,
        )
        for reg in template.registers
    ]

    # Register device in protocol adapter
    if protocol_manager.is_running:
        try:
            await protocol_manager.add_device(
                template.protocol, device.id, device.slave_id, register_infos,
            )
        except Exception as e:
            device.status = "error"
            await session.commit()
            raise ConflictException(
                detail=f"Failed to start device: {e}",
                error_code="PROTOCOL_ERROR",
            ) from e

    # Start simulation engine for this device
    if protocol_manager.is_running:
        try:
            await simulation_engine.start_device(device.id)
        except Exception as e:
            logger.error("Failed to start simulation for device %s: %s", device_id, e)

    # Set SNMP register names if applicable
    if template.protocol == "snmp":
        try:
            snmp_adapter = protocol_manager.get_adapter("snmp")
            oid_to_name = {
                reg.oid: reg.name
                for reg in template.registers
                if reg.oid
            }
            snmp_adapter.set_register_names(device.id, oid_to_name)  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("Failed to set SNMP register names: %s", e)

    # Auto-start MQTT publishing if configured and enabled
    try:
        mqtt_config = await mqtt_service.get_publish_config(session, device.id)
        if mqtt_config and mqtt_config.enabled:
            mqtt_adapter = protocol_manager.get_adapter("mqtt")
            mqtt_adapter.set_device_meta(  # type: ignore[attr-defined]
                device.id, device.name, device.slave_id,
                template.name,
            )
            await mqtt_adapter.start_publishing(device.id, mqtt_config)  # type: ignore[attr-defined]
    except Exception as e:
        logger.warning("Failed to start MQTT publishing for device %s: %s", device_id, e)

    device.status = "running"
    await session.commit()

    from app.services.monitor_service import monitor_service
    monitor_service.log_event(
        device.id, device.name, "device_start", f"Device started (slave {device.slave_id})",
    )

    return await get_device(session, device.id)


async def stop_device(
    session: AsyncSession, device_id: uuid.UUID,
) -> dict:
    """Stop a device (running/error → stopped). Unregisters slave from protocol adapter."""
    device = await _get_device_raw(session, device_id)

    if device.status == "stopped":
        raise ConflictException(
            detail="Device is already stopped",
            error_code="INVALID_STATE_TRANSITION",
        )

    # Stop MQTT publishing (best-effort)
    try:
        mqtt_adapter = protocol_manager.get_adapter("mqtt")
        await mqtt_adapter.stop_publishing(device.id)  # type: ignore[attr-defined]
    except Exception:
        pass

    # Stop scenario if running (best-effort)
    try:
        from app.api.routes.scenarios import runner as scenario_runner
        await scenario_runner.stop(device.id)
    except Exception:
        pass

    # Stop simulation engine for this device
    try:
        await simulation_engine.stop_device(device.id)
    except Exception as e:
        logger.warning("Failed to stop simulation for device %s: %s", device_id, e)

    # Unregister device from protocol adapter (best-effort for error state)
    if protocol_manager.is_running:
        template = await _get_template_or_404(session, device.template_id)
        try:
            await protocol_manager.remove_device(template.protocol, device.id)
        except Exception:
            logger.warning("Failed to remove device %s from adapter", device_id)

    device.status = "stopped"
    await session.commit()

    from app.services.monitor_service import monitor_service
    monitor_service.log_event(
        device.id, device.name, "device_stop", "Device stopped",
    )

    return await get_device(session, device.id)


async def _batch_device_action(
    session: AsyncSession,
    device_ids: list[uuid.UUID] | None,
    skip_status: str,
    action_fn,
    default_filter=None,
    action_name: str = "action",
) -> dict:
    """Generic batch device operation. Skips devices with skip_status."""
    if device_ids:
        stmt = select(DeviceInstance).where(DeviceInstance.id.in_(device_ids))
    elif default_filter is not None:
        stmt = select(DeviceInstance).where(default_filter)
    else:
        stmt = select(DeviceInstance)
    result = await session.execute(stmt)
    devices = list(result.scalars().all())

    success_count = 0
    skipped_count = 0
    error_count = 0

    for device in devices:
        if device.status == skip_status:
            skipped_count += 1
            continue
        try:
            await action_fn(session, device.id)
            success_count += 1
        except Exception as e:
            logger.warning("Batch %s failed for device %s: %s", action_name, device.id, e)
            error_count += 1

    return {
        "success_count": success_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
    }


async def batch_start_devices(
    session: AsyncSession, device_ids: list[uuid.UUID] | None = None,
) -> dict:
    """Start multiple devices. Skips non-stopped devices."""
    return await _batch_device_action(
        session, device_ids,
        skip_status="running",
        action_fn=start_device,
        default_filter=DeviceInstance.status == "stopped",
        action_name="start",
    )


async def batch_stop_devices(
    session: AsyncSession, device_ids: list[uuid.UUID] | None = None,
) -> dict:
    """Stop multiple devices. Skips already-stopped devices."""
    return await _batch_device_action(
        session, device_ids,
        skip_status="stopped",
        action_fn=stop_device,
        default_filter=DeviceInstance.status != "stopped",
        action_name="stop",
    )


async def batch_delete_devices(
    session: AsyncSession, device_ids: list[uuid.UUID],
) -> dict:
    """Delete multiple devices. Skips running devices."""
    return await _batch_device_action(
        session, device_ids,
        skip_status="running",
        action_fn=delete_device,
        action_name="delete",
    )


async def get_device_registers(
    session: AsyncSession, device_id: uuid.UUID,
) -> list[dict]:
    """Get register definitions for a device (value=None in Phase 3)."""
    device_data = await get_device(session, device_id)
    template = await _get_template_or_404(session, device_data["template_id"])
    return [
        RegisterValue(
            name=reg.name,
            address=reg.address,
            function_code=reg.function_code,
            data_type=reg.data_type,
            byte_order=reg.byte_order,
            scale_factor=reg.scale_factor,
            unit=reg.unit,
            description=reg.description,
            oid=reg.oid,
            value=None,
        ).model_dump()
        for reg in template.registers
    ]
