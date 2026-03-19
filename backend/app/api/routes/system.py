"""System-level API routes for config export/import."""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.services import system_service

router = APIRouter()


@router.get("/export")
async def export_config(session: AsyncSession = Depends(get_session)) -> Response:
    """Export full system configuration as JSON file download."""
    snapshot = await system_service.export_system(session)
    content = json.dumps(snapshot.model_dump(), indent=2, ensure_ascii=False)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=ghostmeter-config.json"},
    )
