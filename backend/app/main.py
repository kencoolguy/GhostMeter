import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes.anomaly import router as anomaly_router
from app.api.routes.system import router as system_router
from app.api.websocket import router as ws_router, start_broadcast, stop_broadcast
from app.api.routes.health import router as health_router
from app.api.routes.devices import router as devices_router
from app.api.routes.simulation import router as simulation_router
from app.api.routes.templates import router as templates_router
from app.config import get_settings
from app.database import engine
from app.protocols import protocol_manager
from app.protocols.modbus_tcp import ModbusTcpAdapter
from app.seed.loader import seed_builtin_templates
from app.simulation import simulation_engine
from app.exceptions import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
)

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)

    # Verify DB connection on startup
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
    except Exception:
        logger.error("Database connection failed", exc_info=True)

    # Seed built-in templates
    await seed_builtin_templates()
    logger.info("Seed data check complete")

    # Start Modbus TCP protocol adapter
    modbus_adapter = ModbusTcpAdapter(
        host=settings.MODBUS_HOST,
        port=settings.MODBUS_PORT,
    )
    protocol_manager.register_adapter("modbus_tcp", modbus_adapter)
    await protocol_manager.start_all()
    logger.info("Protocol manager started")

    # Start WebSocket monitor broadcast
    start_broadcast()
    logger.info("Monitor broadcast started")

    yield

    # Stop monitor broadcast
    await stop_broadcast()
    logger.info("Monitor broadcast stopped")

    # Shutdown simulation engine
    await simulation_engine.shutdown()
    logger.info("Simulation engine stopped")

    # Shutdown protocol manager
    await protocol_manager.stop_all()
    logger.info("Protocol manager stopped")

    # Shutdown
    await engine.dispose()
    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3002", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Routes — health at root, WebSocket at root, API routes under /api/v1
app.include_router(health_router)
app.include_router(ws_router)
api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(templates_router, prefix="/templates", tags=["templates"])
api_v1_router.include_router(devices_router, prefix="/devices", tags=["devices"])
api_v1_router.include_router(simulation_router, prefix="/devices", tags=["simulation"])
api_v1_router.include_router(anomaly_router, prefix="/devices", tags=["anomaly"])
api_v1_router.include_router(system_router, prefix="/system", tags=["system"])
app.include_router(api_v1_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
