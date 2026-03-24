"""API routes for simulation profile CRUD."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiResponse
from app.schemas.simulation_profile import (
    SimulationProfileCreate,
    SimulationProfileResponse,
    SimulationProfileUpdate,
)
from app.services import simulation_profile_service

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[list[SimulationProfileResponse]],
)
async def list_profiles(
    template_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[SimulationProfileResponse]]:
    """List all simulation profiles for a template."""
    profiles = await simulation_profile_service.list_profiles(session, template_id)
    return ApiResponse(
        data=[SimulationProfileResponse.model_validate(p) for p in profiles]
    )


@router.get(
    "/{profile_id}",
    response_model=ApiResponse[SimulationProfileResponse],
)
async def get_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[SimulationProfileResponse]:
    """Get a single simulation profile."""
    profile = await simulation_profile_service.get_profile(session, profile_id)
    return ApiResponse(data=SimulationProfileResponse.model_validate(profile))


@router.post(
    "",
    response_model=ApiResponse[SimulationProfileResponse],
    status_code=201,
)
async def create_profile(
    data: SimulationProfileCreate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[SimulationProfileResponse]:
    """Create a new simulation profile."""
    profile = await simulation_profile_service.create_profile(session, data)
    return ApiResponse(data=SimulationProfileResponse.model_validate(profile))


@router.put(
    "/{profile_id}",
    response_model=ApiResponse[SimulationProfileResponse],
)
async def update_profile(
    profile_id: uuid.UUID,
    data: SimulationProfileUpdate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[SimulationProfileResponse]:
    """Update a simulation profile."""
    profile = await simulation_profile_service.update_profile(
        session, profile_id, data,
    )
    return ApiResponse(data=SimulationProfileResponse.model_validate(profile))


@router.delete(
    "/{profile_id}",
    response_model=ApiResponse[None],
)
async def delete_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete a simulation profile."""
    await simulation_profile_service.delete_profile(session, profile_id)
    return ApiResponse(message="Profile deleted successfully")
