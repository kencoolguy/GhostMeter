"""CRUD service for simulation configurations."""

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import NotFoundException, ValidationException
from app.models.device import DeviceInstance
from app.models.simulation import SimulationConfig
from app.models.template import DeviceTemplate
from app.schemas.simulation import SimulationConfigBatchSet, SimulationConfigCreate
from app.simulation import simulation_engine

logger = logging.getLogger(__name__)


async def _get_device_or_404(session: AsyncSession, device_id: uuid.UUID) -> DeviceInstance:
    """Get device ORM object or raise 404."""
    stmt = select(DeviceInstance).where(DeviceInstance.id == device_id)
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()
    if device is None:
        raise NotFoundException(
            detail="Device not found", error_code="DEVICE_NOT_FOUND"
        )
    return device


async def _get_template_register_names(
    session: AsyncSession, template_id: uuid.UUID,
) -> set[str]:
    """Get all register names for a template."""
    stmt = (
        select(DeviceTemplate)
        .options(selectinload(DeviceTemplate.registers))
        .where(DeviceTemplate.id == template_id)
    )
    result = await session.execute(stmt)
    template = result.scalar_one()
    return {reg.name for reg in template.registers}


async def _reload_if_running(device_id: uuid.UUID) -> None:
    """Reload simulation engine if the device is currently running."""
    if device_id in simulation_engine._device_tasks:
        await simulation_engine.reload_device(device_id)
        logger.info("Reloaded simulation for running device %s", device_id)


async def get_simulation_configs(
    session: AsyncSession, device_id: uuid.UUID,
) -> list[SimulationConfig]:
    """List all simulation configs for a device."""
    await _get_device_or_404(session, device_id)

    stmt = (
        select(SimulationConfig)
        .where(SimulationConfig.device_id == device_id)
        .order_by(SimulationConfig.register_name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def set_simulation_configs(
    session: AsyncSession,
    device_id: uuid.UUID,
    data: SimulationConfigBatchSet,
) -> list[SimulationConfig]:
    """Replace all simulation configs for a device."""
    device = await _get_device_or_404(session, device_id)
    valid_names = await _get_template_register_names(session, device.template_id)

    # Validate register names
    for cfg in data.configs:
        if cfg.register_name not in valid_names:
            raise ValidationException(
                f"Register '{cfg.register_name}' not found in device template"
            )

    # Check for duplicate register names in the request
    seen: set[str] = set()
    for cfg in data.configs:
        if cfg.register_name in seen:
            raise ValidationException(
                f"Duplicate register_name '{cfg.register_name}' in request"
            )
        seen.add(cfg.register_name)

    # Delete existing configs
    await session.execute(
        delete(SimulationConfig).where(SimulationConfig.device_id == device_id)
    )

    # Create new configs
    new_configs = []
    for cfg in data.configs:
        sim_config = SimulationConfig(
            device_id=device_id,
            register_name=cfg.register_name,
            data_mode=cfg.data_mode,
            mode_params=cfg.mode_params,
            is_enabled=cfg.is_enabled,
            update_interval_ms=cfg.update_interval_ms,
        )
        session.add(sim_config)
        new_configs.append(sim_config)

    await session.commit()

    # Refresh to get DB-generated fields
    for cfg in new_configs:
        await session.refresh(cfg)

    await _reload_if_running(device_id)
    return new_configs


async def update_simulation_config(
    session: AsyncSession,
    device_id: uuid.UUID,
    register_name: str,
    config_data: SimulationConfigCreate,
) -> SimulationConfig:
    """Upsert a single register's simulation config."""
    device = await _get_device_or_404(session, device_id)
    valid_names = await _get_template_register_names(session, device.template_id)

    if register_name not in valid_names:
        raise ValidationException(
            f"Register '{register_name}' not found in device template"
        )

    # Find existing config
    stmt = select(SimulationConfig).where(
        SimulationConfig.device_id == device_id,
        SimulationConfig.register_name == register_name,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.data_mode = config_data.data_mode
        existing.mode_params = config_data.mode_params
        existing.is_enabled = config_data.is_enabled
        existing.update_interval_ms = config_data.update_interval_ms
    else:
        existing = SimulationConfig(
            device_id=device_id,
            register_name=register_name,
            data_mode=config_data.data_mode,
            mode_params=config_data.mode_params,
            is_enabled=config_data.is_enabled,
            update_interval_ms=config_data.update_interval_ms,
        )
        session.add(existing)

    await session.commit()
    await session.refresh(existing)

    await _reload_if_running(device_id)
    return existing


async def delete_simulation_configs(
    session: AsyncSession, device_id: uuid.UUID,
) -> None:
    """Delete all simulation configs for a device."""
    await _get_device_or_404(session, device_id)

    await session.execute(
        delete(SimulationConfig).where(SimulationConfig.device_id == device_id)
    )
    await session.commit()

    await _reload_if_running(device_id)
