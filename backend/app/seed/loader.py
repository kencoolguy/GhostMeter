import json
import logging
from pathlib import Path

from sqlalchemy import select

from app.database import async_session_factory
from app.models.template import DeviceTemplate
from app.schemas.template import TemplateCreate
from app.services import template_service

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).parent


async def seed_builtin_templates() -> None:
    """Load all seed JSON files and create builtin templates if they don't exist."""
    json_files = sorted(SEED_DIR.glob("*.json"))
    if not json_files:
        logger.info("No seed files found in %s", SEED_DIR)
        return

    async with async_session_factory() as session:
        for json_file in json_files:
            try:
                raw = json.loads(json_file.read_text(encoding="utf-8"))
                template_name = raw["name"]

                # Check if already exists
                stmt = select(DeviceTemplate).where(
                    DeviceTemplate.name == template_name,
                    DeviceTemplate.is_builtin.is_(True),
                )
                result = await session.execute(stmt)
                if result.scalar_one_or_none() is not None:
                    logger.debug(
                        "Builtin template '%s' already exists, skipping",
                        template_name,
                    )
                    continue

                data = TemplateCreate(**raw)
                await template_service.create_template(
                    session, data, is_builtin=True
                )
                logger.info("Seeded builtin template: %s", template_name)

            except Exception:
                logger.error(
                    "Failed to load seed file %s", json_file.name, exc_info=True
                )
