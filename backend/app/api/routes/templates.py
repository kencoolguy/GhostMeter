import json
import uuid

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.common import ApiResponse
from app.schemas.template import (
    TemplateClone,
    TemplateCreate,
    TemplateDetail,
    TemplateSummary,
    TemplateUpdate,
)
from app.services import template_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[TemplateSummary]])
async def list_templates(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[TemplateSummary]]:
    """List all device templates."""
    templates = await template_service.list_templates(session)
    summaries = [TemplateSummary(**t) for t in templates]
    return ApiResponse(data=summaries)


@router.post("", response_model=ApiResponse[TemplateDetail], status_code=201)
async def create_template(
    data: TemplateCreate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TemplateDetail]:
    """Create a new device template."""
    template = await template_service.create_template(session, data)
    return ApiResponse(data=TemplateDetail.model_validate(template))


# --- /import MUST come before /{template_id} routes ---

@router.post("/import", response_model=ApiResponse[TemplateDetail], status_code=201)
async def import_template(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TemplateDetail]:
    """Import a template from a JSON file."""
    content = await file.read()
    raw = json.loads(content)
    data = TemplateCreate(**raw)
    template = await template_service.import_template(session, data)
    return ApiResponse(data=TemplateDetail.model_validate(template))


# --- /{template_id} routes ---

@router.get("/{template_id}", response_model=ApiResponse[TemplateDetail])
async def get_template(
    template_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TemplateDetail]:
    """Get a single template with all register definitions."""
    template = await template_service.get_template(session, template_id)
    return ApiResponse(data=TemplateDetail.model_validate(template))


@router.put("/{template_id}", response_model=ApiResponse[TemplateDetail])
async def update_template(
    template_id: uuid.UUID,
    data: TemplateUpdate,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TemplateDetail]:
    """Update a device template (full replacement including registers)."""
    template = await template_service.update_template(session, template_id, data)
    return ApiResponse(data=TemplateDetail.model_validate(template))


@router.delete("/{template_id}", response_model=ApiResponse[None])
async def delete_template(
    template_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[None]:
    """Delete a device template."""
    await template_service.delete_template(session, template_id)
    return ApiResponse(message="Template deleted successfully")


@router.post(
    "/{template_id}/clone",
    response_model=ApiResponse[TemplateDetail],
    status_code=201,
)
async def clone_template(
    template_id: uuid.UUID,
    data: TemplateClone = TemplateClone(),
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[TemplateDetail]:
    """Clone a device template."""
    template = await template_service.clone_template(session, template_id, data)
    return ApiResponse(data=TemplateDetail.model_validate(template))


@router.get("/{template_id}/export")
async def export_template(
    template_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export a template as a JSON file download."""
    export_data = await template_service.export_template(session, template_id)
    content = json.dumps(export_data, indent=2, ensure_ascii=False)
    filename = f"{export_data['name'].replace(' ', '_').lower()}.json"
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
