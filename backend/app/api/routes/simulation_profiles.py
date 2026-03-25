"""API routes for simulation profile CRUD + import/export."""

import json
import uuid

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiResponse
from app.schemas.simulation_profile import (
    SimulationProfileCreate,
    SimulationProfileExport,
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


@router.get("/template/{template_id}")
async def download_blank_profile(
    template_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Download a blank profile template JSON for a given device template."""
    data = await simulation_profile_service.generate_blank_profile(session, template_id)
    content = json.dumps(data, indent=2, ensure_ascii=False)
    filename = data.get("template_name", "profile").replace(" ", "_").lower()
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}_blank_profile.json"'
        },
    )


@router.post(
    "/import",
    response_model=ApiResponse[SimulationProfileResponse],
    status_code=201,
)
async def import_profile(
    template_id: uuid.UUID,
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[SimulationProfileResponse]:
    """Import a profile from a JSON file upload."""
    try:
        content = await file.read()
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        from app.exceptions import ValidationException
        raise ValidationException(detail=f"Invalid JSON file: {e}")

    profile = await simulation_profile_service.import_profile(session, template_id, data)
    return ApiResponse(data=SimulationProfileResponse.model_validate(profile))


@router.get(
    "/{profile_id}/export",
)
async def export_profile(
    profile_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export a profile as a JSON file download."""
    data = await simulation_profile_service.export_profile(session, profile_id)
    content = json.dumps(data, indent=2, ensure_ascii=False)
    filename = data.get("name", "profile").replace(" ", "_").lower()
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.json"'
        },
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
