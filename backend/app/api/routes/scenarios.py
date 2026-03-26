"""API routes for scenario management."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiResponse
from app.schemas.scenario import (
    ScenarioCreate,
    ScenarioDetail,
    ScenarioExport,
    ScenarioSummary,
    ScenarioUpdate,
)
from app.services import scenario_service

router = APIRouter()


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
