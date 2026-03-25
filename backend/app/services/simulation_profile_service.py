"""CRUD service for simulation profiles."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app.models.simulation import SimulationConfig
from app.models.simulation_profile import SimulationProfile
from app.models.template import DeviceTemplate
from app.schemas.simulation_profile import (
    SimulationProfileCreate,
    SimulationProfileUpdate,
)

logger = logging.getLogger(__name__)


async def _get_profile_or_404(
    session: AsyncSession, profile_id: uuid.UUID,
) -> SimulationProfile:
    """Get profile or raise 404."""
    stmt = select(SimulationProfile).where(SimulationProfile.id == profile_id)
    result = await session.execute(stmt)
    profile = result.scalar_one_or_none()
    if profile is None:
        raise NotFoundException(
            detail="Simulation profile not found",
            error_code="PROFILE_NOT_FOUND",
        )
    return profile


async def _get_template_or_404(
    session: AsyncSession, template_id: uuid.UUID,
) -> DeviceTemplate:
    """Get template or raise 404."""
    stmt = select(DeviceTemplate).where(DeviceTemplate.id == template_id)
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundException(
            detail="Template not found", error_code="TEMPLATE_NOT_FOUND"
        )
    return template


async def _commit_or_raise_conflict(
    session: AsyncSession, name: str,
) -> None:
    """Commit and convert unique constraint violations to ConflictException."""
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if "uq_simulation_profile_template_name" in str(e):
            raise ConflictException(
                detail=f"Profile name '{name}' already exists for this template",
                error_code="PROFILE_NAME_CONFLICT",
            ) from e
        raise ValidationException(f"Database constraint violation: {e}") from e


async def _clear_existing_default(
    session: AsyncSession, template_id: uuid.UUID,
) -> None:
    """Clear is_default flag on any existing default profile for this template."""
    stmt = select(SimulationProfile).where(
        SimulationProfile.template_id == template_id,
        SimulationProfile.is_default.is_(True),
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.is_default = False


async def list_profiles(
    session: AsyncSession, template_id: uuid.UUID,
) -> list[SimulationProfile]:
    """List all profiles for a template."""
    await _get_template_or_404(session, template_id)
    stmt = (
        select(SimulationProfile)
        .where(SimulationProfile.template_id == template_id)
        .order_by(SimulationProfile.name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_profile(
    session: AsyncSession, profile_id: uuid.UUID,
) -> SimulationProfile:
    """Get a single profile by ID."""
    return await _get_profile_or_404(session, profile_id)


async def create_profile(
    session: AsyncSession, data: SimulationProfileCreate,
) -> SimulationProfile:
    """Create a new simulation profile."""
    await _get_template_or_404(session, data.template_id)

    if data.is_default:
        await _clear_existing_default(session, data.template_id)

    profile = SimulationProfile(
        template_id=data.template_id,
        name=data.name,
        description=data.description,
        is_default=data.is_default,
        configs=[c.model_dump() for c in data.configs],
    )
    session.add(profile)
    await _commit_or_raise_conflict(session, data.name)
    await session.refresh(profile)
    return profile


async def update_profile(
    session: AsyncSession,
    profile_id: uuid.UUID,
    data: SimulationProfileUpdate,
) -> SimulationProfile:
    """Update a simulation profile."""
    profile = await _get_profile_or_404(session, profile_id)

    if profile.is_builtin and data.configs is not None:
        raise ForbiddenException(
            detail="Cannot modify configs of a built-in profile",
            error_code="BUILTIN_PROFILE_IMMUTABLE",
        )

    if data.name is not None:
        profile.name = data.name
    if data.description is not None:
        profile.description = data.description
    if data.is_default is not None:
        if data.is_default:
            await _clear_existing_default(session, profile.template_id)
        profile.is_default = data.is_default
    if data.configs is not None:
        profile.configs = [c.model_dump() for c in data.configs]

    await _commit_or_raise_conflict(session, data.name or profile.name)
    await session.refresh(profile)
    return profile


async def delete_profile(
    session: AsyncSession, profile_id: uuid.UUID,
) -> None:
    """Delete a simulation profile. Built-in profiles cannot be deleted."""
    profile = await _get_profile_or_404(session, profile_id)
    if profile.is_builtin:
        raise ForbiddenException(
            detail="Cannot delete a built-in profile",
            error_code="BUILTIN_PROFILE_IMMUTABLE",
        )
    await session.delete(profile)
    await session.commit()


async def apply_profile_to_device(
    session: AsyncSession,
    profile: SimulationProfile,
    device_id: uuid.UUID,
) -> None:
    """Expand profile configs into simulation_configs rows for a device."""
    for cfg in profile.configs:
        sim_config = SimulationConfig(
            device_id=device_id,
            register_name=cfg["register_name"],
            data_mode=cfg["data_mode"],
            mode_params=cfg.get("mode_params", {}),
            is_enabled=cfg.get("is_enabled", True),
            update_interval_ms=cfg.get("update_interval_ms", 1000),
        )
        session.add(sim_config)
    await session.flush()


async def export_profile(
    session: AsyncSession, profile_id: uuid.UUID,
) -> dict:
    """Export a profile as a standalone JSON-serializable dict."""
    from sqlalchemy.orm import selectinload

    profile = await _get_profile_or_404(session, profile_id)

    # Get template name for reference
    stmt = select(DeviceTemplate).where(DeviceTemplate.id == profile.template_id)
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    template_name = template.name if template else ""

    return {
        "name": profile.name,
        "description": profile.description,
        "template_name": template_name,
        "configs": profile.configs,
    }


async def generate_blank_profile(
    session: AsyncSession, template_id: uuid.UUID,
) -> dict:
    """Generate a blank profile template JSON from a template's registers."""
    from sqlalchemy.orm import selectinload

    stmt = (
        select(DeviceTemplate)
        .where(DeviceTemplate.id == template_id)
        .options(selectinload(DeviceTemplate.registers))
    )
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundException(
            detail="Template not found", error_code="TEMPLATE_NOT_FOUND",
        )

    configs = []
    for reg in sorted(template.registers, key=lambda r: r.sort_order):
        configs.append({
            "register_name": reg.name,
            "data_mode": "static",
            "mode_params": {},
            "is_enabled": True,
            "update_interval_ms": 1000,
        })

    return {
        "name": "My Profile",
        "description": None,
        "template_name": template.name,
        "configs": configs,
    }


async def import_profile(
    session: AsyncSession, template_id: uuid.UUID, data: dict,
) -> SimulationProfile:
    """Import a profile from an exported JSON dict."""
    name = data.get("name", "").strip()
    if not name:
        raise ValidationException(detail="Profile name is required")

    description = data.get("description")
    configs = data.get("configs", [])
    if not configs:
        raise ValidationException(detail="Profile must have at least one config entry")

    create_data = SimulationProfileCreate(
        template_id=template_id,
        name=name,
        description=description,
        is_default=False,
        configs=configs,
    )
    return await create_profile(session, create_data)


async def get_default_profile(
    session: AsyncSession, template_id: uuid.UUID,
) -> SimulationProfile | None:
    """Get the default profile for a template, if any."""
    stmt = select(SimulationProfile).where(
        SimulationProfile.template_id == template_id,
        SimulationProfile.is_default.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
