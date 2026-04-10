from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.database as _db_module
from app.config import get_settings
from app.database import Base, get_session
from app.main import app

settings = get_settings()


def _build_test_db_url() -> str:
    """Derive a test database URL from the production URL.

    Appends '_test' to the database name so tests never touch production data.
    """
    base_url = settings.database_url_computed
    parts = base_url.rsplit("/", 1)
    return f"{parts[0]}/{parts[1]}_test"


def _admin_url() -> str:
    """URL pointing at the default 'postgres' database for admin DDL."""
    base_url = settings.database_url_computed
    parts = base_url.rsplit("/", 1)
    return f"{parts[0]}/postgres"


@pytest.fixture(scope="session", autouse=True)
async def create_test_database():
    """Create the test database once per session, drop it at the end."""
    test_db_name = f"{settings.POSTGRES_DB}_test"
    admin_engine = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")

    async with admin_engine.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db_name}"'))
        await conn.execute(text(f'CREATE DATABASE "{test_db_name}"'))

    await admin_engine.dispose()

    yield

    admin_engine = create_async_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{test_db_name}' AND pid <> pg_backend_pid()"
        ))
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{test_db_name}"'))
    await admin_engine.dispose()


@pytest.fixture(autouse=True)
async def setup_database():
    """Create tables before each test and truncate after.

    Replaces both the FastAPI dependency (get_session) AND the module-level
    async_session_factory so that code using either path hits the test DB.
    """
    test_engine = create_async_engine(_build_test_db_url(), echo=False)
    test_session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False,
    )

    # Override FastAPI dependency
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    # Override module-level factory everywhere.
    # Modules that did `from app.database import async_session_factory`
    # hold a local binding that must be patched individually.
    import app.seed.loader as _seed_mod
    import app.services.monitor_service as _monitor_mod
    import app.simulation.engine as _engine_mod

    _patched_modules = [_db_module, _seed_mod, _monitor_mod, _engine_mod]
    _originals = {mod: getattr(mod, "async_session_factory") for mod in _patched_modules}
    for mod in _patched_modules:
        mod.async_session_factory = test_session_factory

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE device_templates, register_definitions, device_instances, "
            "simulation_configs, anomaly_schedules, simulation_profiles, "
            "mqtt_broker_settings, mqtt_publish_configs, "
            "scenarios, scenario_steps CASCADE"
        ))

    # Restore original factories
    for mod, orig in _originals.items():
        mod.async_session_factory = orig
    await test_engine.dispose()
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for testing FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
