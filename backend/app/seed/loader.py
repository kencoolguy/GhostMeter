import json
import logging
from pathlib import Path

from sqlalchemy import select

from app.database import async_session_factory
from app.models.simulation_profile import SimulationProfile
from app.models.template import DeviceTemplate
from app.schemas.template import TemplateCreate
from app.services import template_service

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).parent
PROFILES_DIR = SEED_DIR / "profiles"
SCENARIOS_DIR = SEED_DIR / "scenarios"


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


async def seed_builtin_profiles() -> None:
    """Load profile seed JSON files and create builtin profiles if they don't exist."""
    if not PROFILES_DIR.is_dir():
        logger.info("No profiles seed directory found at %s", PROFILES_DIR)
        return

    json_files = sorted(PROFILES_DIR.glob("*.json"))
    if not json_files:
        logger.info("No profile seed files found in %s", PROFILES_DIR)
        return

    async with async_session_factory() as session:
        for json_file in json_files:
            try:
                raw = json.loads(json_file.read_text(encoding="utf-8"))
                template_name = raw["template_name"]
                profile_name = raw["name"]

                # Find template by name
                stmt = select(DeviceTemplate).where(
                    DeviceTemplate.name == template_name,
                )
                result = await session.execute(stmt)
                template = result.scalar_one_or_none()
                if template is None:
                    logger.warning(
                        "Template '%s' not found for profile seed '%s', skipping",
                        template_name, json_file.name,
                    )
                    continue

                # Check if profile already exists
                stmt = select(SimulationProfile).where(
                    SimulationProfile.template_id == template.id,
                    SimulationProfile.name == profile_name,
                )
                result = await session.execute(stmt)
                if result.scalar_one_or_none() is not None:
                    logger.debug(
                        "Profile '%s' for '%s' already exists, skipping",
                        profile_name, template_name,
                    )
                    continue

                # If is_default, clear any existing default first
                if raw.get("is_default", False):
                    stmt = select(SimulationProfile).where(
                        SimulationProfile.template_id == template.id,
                        SimulationProfile.is_default.is_(True),
                    )
                    result = await session.execute(stmt)
                    existing_default = result.scalar_one_or_none()
                    if existing_default is not None:
                        existing_default.is_default = False

                profile = SimulationProfile(
                    template_id=template.id,
                    name=profile_name,
                    description=raw.get("description"),
                    is_builtin=True,
                    is_default=raw.get("is_default", False),
                    configs=raw["configs"],
                )
                session.add(profile)
                await session.commit()
                logger.info(
                    "Seeded profile '%s' for template '%s'",
                    profile_name, template_name,
                )

            except Exception:
                logger.error(
                    "Failed to load profile seed %s", json_file.name, exc_info=True,
                )


async def seed_builtin_scenarios() -> None:
    """Load scenario seed JSON files and create builtin scenarios if they don't exist."""
    if not SCENARIOS_DIR.is_dir():
        logger.info("No scenarios seed directory found at %s", SCENARIOS_DIR)
        return

    from app.models.scenario import Scenario
    from app.schemas.scenario import ScenarioCreate, ScenarioStepCreate
    from app.services import scenario_service

    json_files = sorted(SCENARIOS_DIR.glob("*.json"))

    async with async_session_factory() as session:
        for json_file in json_files:
            try:
                raw = json.loads(json_file.read_text(encoding="utf-8"))
                scenario_name = raw["name"]
                template_name = raw["template_name"]

                # Resolve template
                stmt = select(DeviceTemplate).where(DeviceTemplate.name == template_name)
                result = await session.execute(stmt)
                template = result.scalar_one_or_none()
                if template is None:
                    logger.warning(
                        "Template '%s' not found for scenario seed '%s', skipping",
                        template_name, scenario_name,
                    )
                    continue

                # Check if already exists
                stmt2 = select(Scenario).where(
                    Scenario.template_id == template.id,
                    Scenario.name == scenario_name,
                    Scenario.is_builtin.is_(True),
                )
                result2 = await session.execute(stmt2)
                if result2.scalar_one_or_none() is not None:
                    logger.debug("Builtin scenario '%s' already exists, skipping", scenario_name)
                    continue

                steps = [ScenarioStepCreate(**s) for s in raw["steps"]]
                create_data = ScenarioCreate(
                    template_id=template.id,
                    name=scenario_name,
                    description=raw.get("description"),
                    steps=steps,
                )
                await scenario_service.create_scenario(session, create_data, is_builtin=True)
                logger.info("Seeded builtin scenario: %s", scenario_name)

            except Exception:
                logger.error("Failed to load scenario seed %s", json_file.name, exc_info=True)
