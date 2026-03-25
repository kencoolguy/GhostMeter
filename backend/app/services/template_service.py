import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app.models.device import DeviceInstance
from app.models.template import DeviceTemplate, RegisterDefinition
from app.schemas.template import (
    DATA_TYPE_REGISTER_COUNT,
    RegisterDefinitionCreate,
    TemplateClone,
    TemplateCreate,
    TemplateUpdate,
)

logger = logging.getLogger(__name__)


def _validate_no_address_overlap(
    registers: list[RegisterDefinitionCreate],
) -> None:
    """Validate that register address ranges do not overlap within the same function_code.

    Each register occupies [address, address + register_count - 1] inclusive.
    Raises ValidationException if any two registers overlap.
    """
    by_fc: dict[int, list[tuple[str, int, int]]] = {}
    for reg in registers:
        count = DATA_TYPE_REGISTER_COUNT[reg.data_type]
        start = reg.address
        end = reg.address + count - 1
        by_fc.setdefault(reg.function_code, []).append((reg.name, start, end))

    for fc, ranges in by_fc.items():
        sorted_ranges = sorted(ranges, key=lambda r: r[1])
        for i in range(len(sorted_ranges) - 1):
            name_a, _, end_a = sorted_ranges[i]
            name_b, start_b, _ = sorted_ranges[i + 1]
            if end_a >= start_b:
                raise ValidationException(
                    f"Register address overlap: '{name_a}' and '{name_b}' "
                    f"overlap in FC{fc}"
                )


def _build_registers(
    data_registers: list[RegisterDefinitionCreate],
) -> list[RegisterDefinition]:
    """Build RegisterDefinition ORM objects from schema data."""
    return [
        RegisterDefinition(
            name=reg.name,
            address=reg.address,
            function_code=reg.function_code,
            data_type=reg.data_type,
            byte_order=reg.byte_order,
            scale_factor=reg.scale_factor,
            unit=reg.unit,
            description=reg.description,
            sort_order=reg.sort_order,
            oid=reg.oid,
        )
        for reg in data_registers
    ]


async def list_templates(session: AsyncSession) -> list[dict]:
    """List all templates with register count."""
    stmt = (
        select(
            DeviceTemplate,
            func.count(RegisterDefinition.id).label("register_count"),
        )
        .outerjoin(RegisterDefinition)
        .group_by(DeviceTemplate.id)
        .order_by(DeviceTemplate.created_at)
    )
    result = await session.execute(stmt)
    rows = result.all()
    return [
        {
            "id": row.DeviceTemplate.id,
            "name": row.DeviceTemplate.name,
            "protocol": row.DeviceTemplate.protocol,
            "description": row.DeviceTemplate.description,
            "is_builtin": row.DeviceTemplate.is_builtin,
            "register_count": row.register_count,
            "created_at": row.DeviceTemplate.created_at,
            "updated_at": row.DeviceTemplate.updated_at,
        }
        for row in rows
    ]


async def get_template(session: AsyncSession, template_id: uuid.UUID) -> DeviceTemplate:
    """Get a single template with all registers."""
    stmt = (
        select(DeviceTemplate)
        .options(selectinload(DeviceTemplate.registers))
        .where(DeviceTemplate.id == template_id)
    )
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundException(detail="Template not found", error_code="TEMPLATE_NOT_FOUND")
    return template


async def create_template(
    session: AsyncSession,
    data: TemplateCreate,
    is_builtin: bool = False,
) -> DeviceTemplate:
    """Create a new template with registers."""
    # Skip address overlap validation for non-Modbus protocols (e.g. SNMP uses address as index)
    if data.protocol == "modbus_tcp":
        _validate_no_address_overlap(data.registers)

    # Check for duplicate name before hitting DB constraint
    existing = await session.execute(
        select(DeviceTemplate).where(DeviceTemplate.name == data.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise ValidationException(
            f"Template with name '{data.name}' already exists"
        )

    template = DeviceTemplate(
        name=data.name,
        protocol=data.protocol,
        description=data.description,
        is_builtin=is_builtin,
    )
    template.registers = _build_registers(data.registers)

    session.add(template)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValidationException(f"Database constraint violation: {e}") from e
    await session.refresh(template)

    return await get_template(session, template.id)


async def update_template(
    session: AsyncSession,
    template_id: uuid.UUID,
    data: TemplateUpdate,
) -> DeviceTemplate:
    """Update a template, replacing all registers."""
    template = await get_template(session, template_id)

    if template.is_builtin:
        raise ForbiddenException(
            detail="Built-in templates cannot be modified",
            error_code="BUILTIN_TEMPLATE_IMMUTABLE",
        )

    if data.protocol == "modbus_tcp":
        _validate_no_address_overlap(data.registers)

    template.name = data.name
    template.protocol = data.protocol
    template.description = data.description

    # Replace registers wholesale — flush deletes before inserting new ones
    # to avoid unique constraint violations on (template_id, address, function_code)
    template.registers.clear()
    await session.flush()
    template.registers = _build_registers(data.registers)

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise ValidationException(f"Database constraint violation: {e}") from e

    return await get_template(session, template.id)


async def delete_template(
    session: AsyncSession,
    template_id: uuid.UUID,
) -> None:
    """Delete a template and its registers."""
    template = await get_template(session, template_id)

    # Check if template is in use by devices
    device_count = await session.scalar(
        select(func.count(DeviceInstance.id))
        .where(DeviceInstance.template_id == template_id)
    )
    if device_count > 0:
        raise ConflictException(
            detail=f"Template is in use by {device_count} device(s)",
            error_code="TEMPLATE_IN_USE",
        )

    if template.is_builtin:
        raise ForbiddenException(
            detail="Built-in templates cannot be deleted",
            error_code="BUILTIN_TEMPLATE_IMMUTABLE",
        )

    await session.delete(template)
    await session.commit()


async def clone_template(
    session: AsyncSession,
    template_id: uuid.UUID,
    data: TemplateClone,
) -> DeviceTemplate:
    """Clone a template with a new name."""
    source = await get_template(session, template_id)

    new_name = data.new_name or f"Copy of {source.name}"

    clone_data = TemplateCreate(
        name=new_name,
        protocol=source.protocol,
        description=source.description,
        registers=[
            RegisterDefinitionCreate(
                name=reg.name,
                address=reg.address,
                function_code=reg.function_code,
                data_type=reg.data_type,
                byte_order=reg.byte_order,
                scale_factor=reg.scale_factor,
                unit=reg.unit,
                description=reg.description,
                sort_order=reg.sort_order,
            )
            for reg in source.registers
        ],
    )
    return await create_template(session, clone_data, is_builtin=False)


async def export_template(
    session: AsyncSession,
    template_id: uuid.UUID,
) -> dict:
    """Export a template as a JSON-serializable dict (no id fields)."""
    template = await get_template(session, template_id)
    return {
        "name": template.name,
        "protocol": template.protocol,
        "description": template.description,
        "registers": [
            {
                "name": reg.name,
                "address": reg.address,
                "function_code": reg.function_code,
                "data_type": reg.data_type,
                "byte_order": reg.byte_order,
                "scale_factor": reg.scale_factor,
                "unit": reg.unit,
                "description": reg.description,
                "sort_order": reg.sort_order,
            }
            for reg in template.registers
        ],
    }


async def import_template(
    session: AsyncSession,
    data: TemplateCreate,
) -> DeviceTemplate:
    """Import a template from JSON data. Name conflicts raise 422."""
    return await create_template(session, data, is_builtin=False)
