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
from app.simulation.aggregate import (
    DeviceDirectory,
    find_cycle,
    format_cycle,
    load_aggregate_dependencies,
    load_device_directory,
)

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


async def _validate_aggregate_configs(
    session: AsyncSession,
    device_id: uuid.UUID,
    configs: list[SimulationConfigCreate],
    *,
    replace_all: bool,
) -> None:
    """Semantic validation for ``aggregate`` configs (needs the DB).

    Checks that every source reference resolves to exactly one existing device
    other than this one, that each source's template actually has the
    aggregated ``register`` (and ``weight_register``), and that the resulting
    dependency graph has no cycle. Raises ``ValidationException`` (422) so a
    typo surfaces at save time instead of as a silent 0.0 in the engine.

    ``replace_all`` says whether ``configs`` replaces the device's whole config
    set (PUT) or upserts single registers (PATCH-style) for the cycle check.
    """
    aggregate_configs = [c for c in configs if c.data_mode == "aggregate"]
    if not aggregate_configs:
        return

    directory: DeviceDirectory = await load_device_directory(session)
    register_names_cache: dict[uuid.UUID, set[str]] = {}

    async def _registers_of(template_id: uuid.UUID) -> set[str]:
        if template_id not in register_names_cache:
            register_names_cache[template_id] = await _get_template_register_names(
                session, template_id,
            )
        return register_names_cache[template_id]

    new_sources: set[uuid.UUID] = set()
    for cfg in aggregate_configs:
        register = cfg.mode_params.get("register") or cfg.register_name
        weight_register = cfg.mode_params.get("weight_register")
        for ref in cfg.mode_params["sources"]:
            try:
                source_id = directory.resolve(ref)
            except ValueError as e:
                raise ValidationException(f"Register '{cfg.register_name}': {e}") from None
            if source_id == device_id:
                raise ValidationException(
                    f"Register '{cfg.register_name}': aggregate source '{ref}' "
                    "is the device itself"
                )
            source_registers = await _registers_of(directory.by_id[source_id].template_id)
            for name in (register, weight_register):
                if name and name not in source_registers:
                    raise ValidationException(
                        f"Register '{cfg.register_name}': aggregate source '{ref}' "
                        f"has no register '{name}'"
                    )
            new_sources.add(source_id)

    deps = await load_aggregate_dependencies(session, directory)
    if replace_all:
        deps[device_id] = new_sources
    else:
        # Upsert: this device's other aggregate registers keep their sources, but the
        # registers being replaced must contribute only their *new* sources.
        replaced = {c.register_name for c in configs}
        stmt = select(SimulationConfig).where(
            SimulationConfig.device_id == device_id,
            SimulationConfig.data_mode == "aggregate",
            SimulationConfig.is_enabled.is_(True),
            SimulationConfig.register_name.not_in(replaced),
        )
        result = await session.execute(stmt)
        kept: set[uuid.UUID] = set(new_sources)
        for existing in result.scalars().all():
            for ref in existing.mode_params.get("sources") or []:
                try:
                    kept.add(directory.resolve(str(ref)))
                except ValueError:
                    continue  # stale reference — the engine treats it as missing
        deps[device_id] = kept

    cycle = find_cycle(deps, device_id)
    if cycle is not None:
        raise ValidationException(
            f"Aggregate dependency cycle: {format_cycle(cycle, directory)}"
        )


async def _reload_if_running(device_id: uuid.UUID) -> None:
    """Reload simulation engine if the device is currently running."""
    if simulation_engine.is_device_simulating(device_id):
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

    await _validate_aggregate_configs(session, device_id, data.configs, replace_all=True)

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

    await _validate_aggregate_configs(
        session, device_id, [config_data], replace_all=False,
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
