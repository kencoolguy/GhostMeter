"""Scenario CRUD service layer."""

import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.scenario import Scenario, ScenarioStep
from app.models.template import DeviceTemplate
from app.schemas.scenario import ScenarioCreate, ScenarioExport, ScenarioStepCreate, ScenarioUpdate

logger = logging.getLogger(__name__)


async def _get_template_or_404(
    session: AsyncSession, template_id: uuid.UUID,
) -> DeviceTemplate:
    """Get template with registers or raise 404."""
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


async def _get_scenario_or_404(
    session: AsyncSession, scenario_id: uuid.UUID,
) -> Scenario:
    """Get scenario with steps or raise 404."""
    stmt = (
        select(Scenario)
        .options(selectinload(Scenario.steps))
        .where(Scenario.id == scenario_id)
    )
    result = await session.execute(stmt)
    scenario = result.scalar_one_or_none()
    if scenario is None:
        raise NotFoundException(detail="Scenario not found", error_code="SCENARIO_NOT_FOUND")
    return scenario


def _validate_steps(
    steps: list[ScenarioStepCreate],
    register_names: set[str],
) -> None:
    """Validate register names exist and no time overlaps per register."""
    for step in steps:
        if step.register_name not in register_names:
            raise ValidationException(
                f"Register '{step.register_name}' not found in template"
            )

    # Check time overlaps per register
    by_register: dict[str, list[ScenarioStepCreate]] = defaultdict(list)
    for step in steps:
        by_register[step.register_name].append(step)

    for reg_name, reg_steps in by_register.items():
        sorted_steps = sorted(reg_steps, key=lambda s: s.trigger_at_seconds)
        for i in range(len(sorted_steps) - 1):
            end_a = sorted_steps[i].trigger_at_seconds + sorted_steps[i].duration_seconds
            start_b = sorted_steps[i + 1].trigger_at_seconds
            if end_a > start_b:
                raise ValidationException(
                    f"Overlapping steps on register '{reg_name}': "
                    f"step ending at {end_a}s overlaps step starting at {start_b}s"
                )


def _compute_total_duration(steps: list[ScenarioStepCreate]) -> int:
    """Compute total scenario duration from steps."""
    if not steps:
        return 0
    return max(s.trigger_at_seconds + s.duration_seconds for s in steps)


def _scenario_to_summary(scenario: Scenario, template_name: str) -> dict:
    """Convert scenario ORM to summary dict."""
    return {
        "id": scenario.id,
        "template_id": scenario.template_id,
        "template_name": template_name,
        "name": scenario.name,
        "description": scenario.description,
        "is_builtin": scenario.is_builtin,
        "total_duration_seconds": scenario.total_duration_seconds,
        "created_at": scenario.created_at,
        "updated_at": scenario.updated_at,
    }


def _scenario_to_detail(scenario: Scenario, template_name: str) -> dict:
    """Convert scenario ORM to detail dict with steps."""
    result = _scenario_to_summary(scenario, template_name)
    result["steps"] = [
        {
            "id": step.id,
            "register_name": step.register_name,
            "anomaly_type": step.anomaly_type,
            "anomaly_params": step.anomaly_params,
            "trigger_at_seconds": step.trigger_at_seconds,
            "duration_seconds": step.duration_seconds,
            "sort_order": step.sort_order,
        }
        for step in scenario.steps
    ]
    return result


async def list_scenarios(
    session: AsyncSession,
    template_id: uuid.UUID | None = None,
) -> list[dict]:
    """List scenarios with optional template filter."""
    stmt = (
        select(Scenario, DeviceTemplate.name.label("template_name"))
        .join(DeviceTemplate, Scenario.template_id == DeviceTemplate.id)
        .order_by(Scenario.created_at)
    )
    if template_id is not None:
        stmt = stmt.where(Scenario.template_id == template_id)
    result = await session.execute(stmt)
    return [_scenario_to_summary(row.Scenario, row.template_name) for row in result.all()]


async def get_scenario(session: AsyncSession, scenario_id: uuid.UUID) -> dict:
    """Get scenario detail with steps."""
    scenario = await _get_scenario_or_404(session, scenario_id)
    template = await _get_template_or_404(session, scenario.template_id)
    return _scenario_to_detail(scenario, template.name)


async def create_scenario(
    session: AsyncSession, data: ScenarioCreate, is_builtin: bool = False,
) -> dict:
    """Create a new scenario with steps."""
    template = await _get_template_or_404(session, data.template_id)
    register_names = {r.name for r in template.registers}
    _validate_steps(data.steps, register_names)

    scenario = Scenario(
        template_id=data.template_id,
        name=data.name,
        description=data.description,
        is_builtin=is_builtin,
        total_duration_seconds=_compute_total_duration(data.steps),
    )
    session.add(scenario)
    await session.flush()

    for step_data in data.steps:
        step = ScenarioStep(
            scenario_id=scenario.id,
            register_name=step_data.register_name,
            anomaly_type=step_data.anomaly_type,
            anomaly_params=step_data.anomaly_params,
            trigger_at_seconds=step_data.trigger_at_seconds,
            duration_seconds=step_data.duration_seconds,
            sort_order=step_data.sort_order,
        )
        session.add(step)

    await session.commit()
    await session.refresh(scenario, ["steps"])
    return _scenario_to_detail(scenario, template.name)


async def update_scenario(
    session: AsyncSession, scenario_id: uuid.UUID, data: ScenarioUpdate,
) -> dict:
    """Update scenario (full replace of steps)."""
    scenario = await _get_scenario_or_404(session, scenario_id)
    if scenario.is_builtin:
        raise ConflictException(
            detail="Built-in scenarios cannot be modified",
            error_code="BUILTIN_PROTECTED",
        )

    template = await _get_template_or_404(session, scenario.template_id)
    register_names = {r.name for r in template.registers}
    _validate_steps(data.steps, register_names)

    scenario.name = data.name
    scenario.description = data.description
    scenario.total_duration_seconds = _compute_total_duration(data.steps)
    scenario.updated_at = datetime.now(UTC)

    # Delete old steps
    for step in list(scenario.steps):
        await session.delete(step)
    await session.flush()

    # Create new steps
    for step_data in data.steps:
        step = ScenarioStep(
            scenario_id=scenario.id,
            register_name=step_data.register_name,
            anomaly_type=step_data.anomaly_type,
            anomaly_params=step_data.anomaly_params,
            trigger_at_seconds=step_data.trigger_at_seconds,
            duration_seconds=step_data.duration_seconds,
            sort_order=step_data.sort_order,
        )
        session.add(step)

    await session.commit()
    await session.refresh(scenario, ["steps"])
    return _scenario_to_detail(scenario, template.name)


async def delete_scenario(session: AsyncSession, scenario_id: uuid.UUID) -> None:
    """Delete a scenario."""
    scenario = await _get_scenario_or_404(session, scenario_id)
    if scenario.is_builtin:
        raise ConflictException(
            detail="Built-in scenarios cannot be deleted",
            error_code="BUILTIN_PROTECTED",
        )
    await session.delete(scenario)
    await session.commit()


async def export_scenario(session: AsyncSession, scenario_id: uuid.UUID) -> dict:
    """Export scenario as portable JSON."""
    scenario = await _get_scenario_or_404(session, scenario_id)
    template = await _get_template_or_404(session, scenario.template_id)
    return {
        "name": scenario.name,
        "description": scenario.description,
        "template_name": template.name,
        "steps": [
            {
                "register_name": step.register_name,
                "anomaly_type": step.anomaly_type,
                "anomaly_params": step.anomaly_params,
                "trigger_at_seconds": step.trigger_at_seconds,
                "duration_seconds": step.duration_seconds,
                "sort_order": step.sort_order,
            }
            for step in scenario.steps
        ],
    }


async def import_scenario(session: AsyncSession, data: ScenarioExport) -> dict:
    """Import scenario from JSON, resolving template_name to template_id."""
    stmt = select(DeviceTemplate).where(DeviceTemplate.name == data.template_name)
    result = await session.execute(stmt)
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundException(
            detail=f"Template '{data.template_name}' not found",
            error_code="TEMPLATE_NOT_FOUND",
        )

    create_data = ScenarioCreate(
        template_id=template.id,
        name=data.name,
        description=data.description,
        steps=data.steps,
    )
    return await create_scenario(session, create_data)
