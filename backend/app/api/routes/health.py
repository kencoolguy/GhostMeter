import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.database import engine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint with DB connectivity status.

    Returns:
        Dict with status, database connectivity, and app version.
    """
    settings = get_settings()
    db_status = "connected"

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.warning("Database health check failed", exc_info=True)
        db_status = "disconnected"

    status = "ok" if db_status == "connected" else "error"

    return {
        "status": status,
        "database": db_status,
        "version": settings.APP_VERSION,
    }
