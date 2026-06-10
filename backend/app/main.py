import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from app.api.routes.anomaly import router as anomaly_router
from app.api.routes.devices import router as devices_router
from app.api.routes.health import router as health_router
from app.api.routes.mqtt import router as mqtt_router
from app.api.routes.scenarios import execution_router as scenario_execution_router
from app.api.routes.scenarios import router as scenarios_router
from app.api.routes.simulation import router as simulation_router
from app.api.routes.simulation_profiles import router as profiles_router
from app.api.routes.system import router as system_router
from app.api.routes.templates import router as templates_router
from app.api.websocket import router as ws_router
from app.api.websocket import start_broadcast, stop_broadcast
from app.config import get_settings
from app.database import async_session_factory, engine
from app.exceptions import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
)
from app.models.device import DeviceInstance
from app.protocols import protocol_manager
from app.protocols.bacnet_agent import BacnetAdapter
from app.protocols.base import RegisterInfo
from app.protocols.modbus_tcp import ModbusTcpAdapter
from app.protocols.mqtt_adapter import MqttAdapter
from app.protocols.opcua_agent import OpcUaAdapter
from app.protocols.snmp_agent import SnmpAdapter
from app.seed.loader import seed_builtin_profiles, seed_builtin_scenarios, seed_builtin_templates
from app.services.template_service import get_template as get_template_with_registers
from app.simulation import simulation_engine

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
# asyncua logs ~1100 INFO lines per Server.init() while loading the standard
# address space, which spams startup logs at root INFO. Quiet it to WARNING.
# (Noise reduction only — the CI 6h timeout was a coverage-tracer issue; see
# pyproject [tool.coverage.run].)
logging.getLogger("asyncua").setLevel(logging.WARNING)
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

    # Seed built-in templates and profiles
    await seed_builtin_templates()
    logger.info("Template seed data check complete")
    await seed_builtin_profiles()
    logger.info("Profile seed data check complete")
    await seed_builtin_scenarios()
    logger.info("Scenario seed data check complete")

    # Start Modbus TCP protocol adapter
    modbus_adapter = ModbusTcpAdapter(
        host=settings.MODBUS_HOST,
        port=settings.MODBUS_PORT,
    )
    protocol_manager.register_adapter("modbus_tcp", modbus_adapter)

    # Register MQTT adapter
    mqtt_adapter = MqttAdapter()
    protocol_manager.register_adapter("mqtt", mqtt_adapter)

    # Register SNMP adapter
    snmp_adapter = SnmpAdapter(
        port=settings.SNMP_PORT,
        community=settings.SNMP_COMMUNITY,
    )
    protocol_manager.register_adapter("snmp", snmp_adapter)

    # Register OPC UA adapter
    opcua_adapter = OpcUaAdapter(
        host=settings.OPCUA_HOST,
        port=settings.OPCUA_PORT,
        endpoint_path=settings.OPCUA_ENDPOINT_PATH,
        server_name=settings.OPCUA_SERVER_NAME,
        namespace_uri=settings.OPCUA_NAMESPACE_URI,
    )
    protocol_manager.register_adapter("opcua", opcua_adapter)

    # Register BACnet adapter
    bacnet_adapter = BacnetAdapter(
        address=settings.BACNET_ADDRESS,
        port=settings.BACNET_PORT,
        device_instance_base=settings.BACNET_DEVICE_INSTANCE_BASE,
        network=settings.BACNET_NETWORK,
    )
    protocol_manager.register_adapter("bacnet", bacnet_adapter)

    await protocol_manager.start_all()
    logger.info("Protocol manager started")

    # Resume devices that were running before shutdown
    async with async_session_factory() as session:
        result = await session.execute(
            select(DeviceInstance).where(DeviceInstance.status == "running")
        )
        running_devices = result.scalars().all()

        resumed = 0
        for device in running_devices:
            try:
                template = await get_template_with_registers(session, device.template_id)
                register_infos = [
                    RegisterInfo(
                        address=reg.address,
                        function_code=reg.function_code,
                        data_type=reg.data_type,
                        byte_order=reg.byte_order,
                        oid=reg.oid,
                        name=reg.name,
                        unit=reg.unit,
                    )
                    for reg in template.registers
                ]
                if template.protocol == "opcua":
                    opcua_adapter.set_device_meta(device.id, device.name)
                if template.protocol == "bacnet":
                    bacnet_adapter = protocol_manager.get_adapter("bacnet")
                    if bacnet_adapter is not None:
                        bacnet_adapter.set_device_meta(device.id, device.name)  # type: ignore[attr-defined]
                await protocol_manager.add_device(
                    template.protocol, device.id, device.slave_id, register_infos,
                )
                await simulation_engine.start_device(device.id)
                # SNMP needs its OID→register-name map rebuilt so resolve_oid can
                # look values up by name (mirrors device_service.start_device).
                # Without this, resumed SNMP devices serve noSuchObject after a
                # restart even though their OIDs are registered.
                if template.protocol == "snmp":
                    snmp_adapter = protocol_manager.get_adapter("snmp")
                    if snmp_adapter is not None:
                        oid_to_name = {
                            reg.oid: reg.name
                            for reg in template.registers
                            if reg.oid
                        }
                        snmp_adapter.set_register_names(device.id, oid_to_name)
                resumed += 1
            except Exception:
                logger.error(
                    "Failed to resume device %s (%s)",
                    device.name, device.id, exc_info=True,
                )

    if resumed:
        logger.info("Resumed %d device(s)", resumed)

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
api_v1_router.include_router(
    profiles_router, prefix="/simulation-profiles", tags=["simulation-profiles"],
)
api_v1_router.include_router(system_router, prefix="/system", tags=["system"])
api_v1_router.include_router(mqtt_router, prefix="/system", tags=["mqtt"])
api_v1_router.include_router(scenarios_router, prefix="/scenarios", tags=["scenarios"])
api_v1_router.include_router(
    scenario_execution_router, prefix="/devices", tags=["scenario-execution"],
)
app.include_router(api_v1_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
