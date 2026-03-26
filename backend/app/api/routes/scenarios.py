"""API routes for scenario management."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiResponse
from app.schemas.scenario import (
    ScenarioCreate,
    ScenarioDetail,
    ScenarioExecutionStatus,
    ScenarioExport,
    ScenarioSummary,
    ScenarioUpdate,
)
from app.services import scenario_service
from app.services.scenario_runner import StepInfo, scenario_runner as runner

router = APIRouter()

# Execution routes use a separate router mounted under /devices
execution_router = APIRouter()


@router.get("", response_model=ApiResponse[list[ScenarioSummary]])
async def list_scenarios(
    template_id: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[ScenarioSummary]]:
    """List all scenarios, optionally filtered by template."""
    scenarios = await scenario_service.list_scenarios(session, template_id)
    return ApiResponse(data=[ScenarioSummary(**s) for s in scenarios])


# /import MUST come before /{scenario_id}
@router.post("/import", response_model=ApiResponse[ScenarioDetail], status_code=201)
async def import_scenario(
    data: ScenarioExport,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ScenarioDetail]:
    """Import scenario from JSON."""
    scenario = await scenario_service.import_scenario(session, data)
    return ApiResponse(data=ScenarioDetail(**scenario))


@router.get("/{scenario_id}", response_model=ApiResponse[ScenarioDetail])
async def get_scenario(
    scenario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ScenarioDetail]:
    """Get scenario with all steps."""
    scenario = await scenario_service.get_scenario(session, scenario_id)
    return ApiResponse(data=ScenarioDetail(**scenario))


@router.post("", response_model=ApiResponse[ScenarioDetail], status_code=201)
async def create_scenario(
    data: ScenarioCreate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ScenarioDetail]:
    """Create a new scenario with steps."""
    scenario = await scenario_service.create_scenario(session, data)
    return ApiResponse(data=ScenarioDetail(**scenario))


@router.put("/{scenario_id}", response_model=ApiResponse[ScenarioDetail])
async def update_scenario(
    scenario_id: uuid.UUID,
    data: ScenarioUpdate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ScenarioDetail]:
    """Update scenario (full replace of steps)."""
    scenario = await scenario_service.update_scenario(session, scenario_id, data)
    return ApiResponse(data=ScenarioDetail(**scenario))


@router.delete("/{scenario_id}", response_model=ApiResponse[None])
async def delete_scenario(
    scenario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete a scenario (409 for built-in)."""
    await scenario_service.delete_scenario(session, scenario_id)
    return ApiResponse(data=None, message="Scenario deleted")


@router.post("/{scenario_id}/export", response_model=ApiResponse[ScenarioExport])
async def export_scenario(
    scenario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[ScenarioExport]:
    """Export scenario as portable JSON."""
    data = await scenario_service.export_scenario(session, scenario_id)
    return ApiResponse(data=ScenarioExport(**data))


# --- Execution endpoints (mounted under /devices via execution_router) ---


@execution_router.post("/{device_id}/scenario/{scenario_id}/start", response_model=ApiResponse[None])
async def start_scenario(
    device_id: uuid.UUID,
    scenario_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Start executing a scenario on a device."""
    from app.exceptions import ConflictException
    from app.services import device_service

    # Verify device is running
    device = await device_service.get_device(session, device_id)
    if device["status"] != "running":
        raise ConflictException(
            detail="Device must be running to start a scenario",
            error_code="DEVICE_NOT_RUNNING",
        )

    # Check no scenario already running
    if runner.get_status(device_id) is not None:
        raise ConflictException(
            detail="A scenario is already running on this device",
            error_code="SCENARIO_ALREADY_RUNNING",
        )

    # Get scenario and validate template match
    scenario = await scenario_service.get_scenario(session, scenario_id)
    if scenario["template_id"] != device["template_id"]:
        raise ConflictException(
            detail="Scenario template does not match device template",
            error_code="TEMPLATE_MISMATCH",
        )

    steps = [
        StepInfo(
            register_name=s["register_name"],
            anomaly_type=s["anomaly_type"],
            anomaly_params=s["anomaly_params"],
            trigger_at_seconds=s["trigger_at_seconds"],
            duration_seconds=s["duration_seconds"],
        )
        for s in scenario["steps"]
    ]

    await runner.start(
        device_id, scenario_id,
        scenario["name"], scenario["total_duration_seconds"], steps,
    )
    return ApiResponse(data=None, message="Scenario started")


@execution_router.post("/{device_id}/scenario/stop", response_model=ApiResponse[None])
async def stop_scenario(device_id: uuid.UUID) -> ApiResponse[None]:
    """Stop a running scenario on a device."""
    await runner.stop(device_id)
    return ApiResponse(data=None, message="Scenario stopped")


@execution_router.get("/{device_id}/scenario/status", response_model=ApiResponse[ScenarioExecutionStatus])
async def get_scenario_status(device_id: uuid.UUID) -> ApiResponse[ScenarioExecutionStatus]:
    """Get scenario execution status for a device."""
    from app.exceptions import NotFoundException

    status = runner.get_status(device_id)
    if status is None:
        raise NotFoundException(
            detail="No scenario running on this device",
            error_code="NO_RUNNING_SCENARIO",
        )
    return ApiResponse(data=ScenarioExecutionStatus(**status))
