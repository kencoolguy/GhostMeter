# MQTT Adapter Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MQTT publish capability — users configure topic/payload per device, press Start Publishing to push simulated data to a broker.

**Architecture:** MqttAdapter reads values from SimulationEngine at publish time (no engine changes). Global broker settings in DB. Per-device publish config with start/stop control. Frontend: Settings page broker form + Device Detail MQTT card.

**Tech Stack:** Python 3.12, aiomqtt, FastAPI, SQLAlchemy 2.0, Alembic, React 18, Ant Design 5, TypeScript

**Spec:** `docs/superpowers/specs/2026-03-23-mqtt-adapter-design.md`

---

## Chunk 1: Backend — DB Models, Schemas, Migration

### Task 1: Create ORM models for MQTT tables

**Files:**
- Create: `backend/app/models/mqtt.py`

- [ ] **Step 1: Write the ORM models**

```python
"""MQTT-related ORM models."""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MqttBrokerSettings(Base):
    """Global MQTT broker connection settings (single row)."""

    __tablename__ = "mqtt_broker_settings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    host: Mapped[str] = mapped_column(String(255), default="localhost")
    port: Mapped[int] = mapped_column(Integer, default=1883)
    username: Mapped[str] = mapped_column(String(255), default="")
    password: Mapped[str] = mapped_column(String(255), default="")
    client_id: Mapped[str] = mapped_column(String(255), default="ghostmeter")
    use_tls: Mapped[bool] = mapped_column(Boolean, default=False)


class MqttPublishConfig(Base):
    """Per-device MQTT publish configuration."""

    __tablename__ = "mqtt_publish_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_instances.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    topic_template: Mapped[str] = mapped_column(
        String(500), default="telemetry/{device_name}"
    )
    payload_mode: Mapped[str] = mapped_column(String(20), default="batch")
    publish_interval_seconds: Mapped[int] = mapped_column(Integer, default=5)
    qos: Mapped[int] = mapped_column(Integer, default=0)
    retain: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [ ] **Step 2: Verify import**

Run: `docker run --rm -v "$(pwd)/backend:/app" -w /app ghostmeter-backend python -c "from app.models.mqtt import MqttBrokerSettings, MqttPublishConfig; print('OK')"`

Expected: `OK`

---

### Task 2: Create Pydantic schemas

**Files:**
- Create: `backend/app/schemas/mqtt.py`

- [ ] **Step 1: Write the schemas**

```python
"""Pydantic schemas for MQTT configuration."""

from pydantic import BaseModel, field_validator


class MqttBrokerSettingsRead(BaseModel):
    """Broker settings response (password masked)."""

    host: str = "localhost"
    port: int = 1883
    username: str = ""
    password: str = ""
    client_id: str = "ghostmeter"
    use_tls: bool = False


class MqttBrokerSettingsWrite(BaseModel):
    """Broker settings update request."""

    host: str = "localhost"
    port: int = 1883
    username: str = ""
    password: str = ""
    client_id: str = "ghostmeter"
    use_tls: bool = False

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v


class MqttPublishConfigRead(BaseModel):
    """Per-device MQTT publish config response."""

    device_id: str
    topic_template: str
    payload_mode: str
    publish_interval_seconds: int
    qos: int
    retain: bool
    enabled: bool


class MqttPublishConfigWrite(BaseModel):
    """Per-device MQTT publish config create/update."""

    topic_template: str = "telemetry/{device_name}"
    payload_mode: str = "batch"
    publish_interval_seconds: int = 5
    qos: int = 0
    retain: bool = False

    @field_validator("payload_mode")
    @classmethod
    def validate_payload_mode(cls, v: str) -> str:
        if v not in ("batch", "per_register"):
            raise ValueError("payload_mode must be 'batch' or 'per_register'")
        return v

    @field_validator("qos")
    @classmethod
    def validate_qos(cls, v: int) -> int:
        if v not in (0, 1, 2):
            raise ValueError("QoS must be 0, 1, or 2")
        return v

    @field_validator("publish_interval_seconds")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Interval must be at least 1 second")
        return v


class MqttTestResult(BaseModel):
    """Result of broker connection test."""

    success: bool
    message: str


class MqttPublishConfigExport(BaseModel):
    """MQTT publish config in export format."""

    device_name: str
    topic_template: str
    payload_mode: str
    publish_interval_seconds: int
    qos: int
    retain: bool
    enabled: bool
```

- [ ] **Step 2: Verify import**

Run: `docker run --rm -v "$(pwd)/backend:/app" -w /app ghostmeter-backend python -c "from app.schemas.mqtt import MqttBrokerSettingsRead, MqttPublishConfigWrite; print('OK')"`

Expected: `OK`

---

### Task 3: Create Alembic migration

**Files:**
- Create: `backend/alembic/versions/xxx_add_mqtt_tables.py` (auto-generated)

- [ ] **Step 1: Generate migration**

Run: `docker run --rm -v "$(pwd)/backend:/app" -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter" ghostmeter-backend alembic revision --autogenerate -m "add mqtt broker settings and publish configs"`

- [ ] **Step 2: Run migration**

Run: `docker run --rm -v "$(pwd)/backend:/app" -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter" ghostmeter-backend alembic upgrade head`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/mqtt.py backend/app/schemas/mqtt.py backend/alembic/versions/
git commit -m "feat: add MQTT ORM models, Pydantic schemas, and migration"
```

---

## Chunk 2: Backend — MQTT Service + API Routes

### Task 4: Create MQTT service layer

**Files:**
- Create: `backend/app/services/mqtt_service.py`

- [ ] **Step 1: Write the service**

```python
"""MQTT config CRUD service."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mqtt import MqttBrokerSettings, MqttPublishConfig

logger = logging.getLogger(__name__)


async def get_broker_settings(session: AsyncSession) -> MqttBrokerSettings | None:
    """Get the global MQTT broker settings (single row)."""
    result = await session.execute(select(MqttBrokerSettings).limit(1))
    return result.scalar_one_or_none()


async def upsert_broker_settings(
    session: AsyncSession,
    host: str,
    port: int,
    username: str,
    password: str,
    client_id: str,
    use_tls: bool,
) -> MqttBrokerSettings:
    """Create or update the global MQTT broker settings."""
    settings = await get_broker_settings(session)
    if settings is None:
        settings = MqttBrokerSettings(
            host=host, port=port, username=username,
            password=password, client_id=client_id, use_tls=use_tls,
        )
        session.add(settings)
    else:
        settings.host = host
        settings.port = port
        settings.username = username
        # Keep existing password if masked value sent
        if password != "****":
            settings.password = password
        settings.client_id = client_id
        settings.use_tls = use_tls
    await session.commit()
    await session.refresh(settings)
    return settings


async def get_publish_config(
    session: AsyncSession, device_id: uuid.UUID,
) -> MqttPublishConfig | None:
    """Get MQTT publish config for a device."""
    result = await session.execute(
        select(MqttPublishConfig).where(MqttPublishConfig.device_id == device_id)
    )
    return result.scalar_one_or_none()


async def upsert_publish_config(
    session: AsyncSession,
    device_id: uuid.UUID,
    topic_template: str,
    payload_mode: str,
    publish_interval_seconds: int,
    qos: int,
    retain: bool,
) -> MqttPublishConfig:
    """Create or update MQTT publish config for a device."""
    config = await get_publish_config(session, device_id)
    if config is None:
        config = MqttPublishConfig(
            device_id=device_id,
            topic_template=topic_template,
            payload_mode=payload_mode,
            publish_interval_seconds=publish_interval_seconds,
            qos=qos,
            retain=retain,
        )
        session.add(config)
    else:
        config.topic_template = topic_template
        config.payload_mode = payload_mode
        config.publish_interval_seconds = publish_interval_seconds
        config.qos = qos
        config.retain = retain
    await session.commit()
    await session.refresh(config)
    return config


async def delete_publish_config(
    session: AsyncSession, device_id: uuid.UUID,
) -> bool:
    """Delete MQTT publish config for a device."""
    config = await get_publish_config(session, device_id)
    if config is None:
        return False
    await session.delete(config)
    await session.commit()
    return True


async def set_publish_enabled(
    session: AsyncSession, device_id: uuid.UUID, enabled: bool,
) -> MqttPublishConfig | None:
    """Set the enabled flag on a device's MQTT publish config."""
    config = await get_publish_config(session, device_id)
    if config is None:
        return None
    config.enabled = enabled
    await session.commit()
    await session.refresh(config)
    return config
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/mqtt_service.py
git commit -m "feat: add MQTT service layer (broker settings + publish config CRUD)"
```

---

### Task 5: Create API routes

**Files:**
- Create: `backend/app/api/routes/mqtt.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write the routes**

```python
"""API routes for MQTT broker settings and per-device publish config."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.exceptions import NotFoundException
from app.schemas.api import ApiResponse
from app.schemas.mqtt import (
    MqttBrokerSettingsRead,
    MqttBrokerSettingsWrite,
    MqttPublishConfigRead,
    MqttPublishConfigWrite,
    MqttTestResult,
)
from app.services import mqtt_service

router = APIRouter()


# --- Broker settings ---

@router.get("/mqtt", response_model=ApiResponse[MqttBrokerSettingsRead])
async def get_broker_settings(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[MqttBrokerSettingsRead]:
    """Get global MQTT broker settings."""
    settings = await mqtt_service.get_broker_settings(session)
    if settings is None:
        return ApiResponse(data=MqttBrokerSettingsRead())
    data = MqttBrokerSettingsRead(
        host=settings.host,
        port=settings.port,
        username=settings.username,
        password="****" if settings.password else "",
        client_id=settings.client_id,
        use_tls=settings.use_tls,
    )
    return ApiResponse(data=data)


@router.put("/mqtt", response_model=ApiResponse[MqttBrokerSettingsRead])
async def update_broker_settings(
    data: MqttBrokerSettingsWrite,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[MqttBrokerSettingsRead]:
    """Update global MQTT broker settings."""
    settings = await mqtt_service.upsert_broker_settings(
        session, data.host, data.port, data.username,
        data.password, data.client_id, data.use_tls,
    )
    result = MqttBrokerSettingsRead(
        host=settings.host,
        port=settings.port,
        username=settings.username,
        password="****" if settings.password else "",
        client_id=settings.client_id,
        use_tls=settings.use_tls,
    )
    return ApiResponse(data=result, message="MQTT broker settings updated")


@router.post("/mqtt/test", response_model=ApiResponse[MqttTestResult])
async def test_broker_connection(
    data: MqttBrokerSettingsWrite,
) -> ApiResponse[MqttTestResult]:
    """Test MQTT broker connection with provided settings."""
    try:
        import aiomqtt
        async with aiomqtt.Client(
            hostname=data.host,
            port=data.port,
            username=data.username or None,
            password=data.password or None,
            identifier=f"{data.client_id}-test",
            timeout=5,
        ):
            pass
        return ApiResponse(data=MqttTestResult(success=True, message="Connection successful"))
    except Exception as e:
        return ApiResponse(data=MqttTestResult(success=False, message=str(e)))


# --- Per-device publish config ---

@router.get(
    "/devices/{device_id}/mqtt",
    response_model=ApiResponse[MqttPublishConfigRead | None],
)
async def get_device_mqtt_config(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[MqttPublishConfigRead | None]:
    """Get MQTT publish config for a device."""
    config = await mqtt_service.get_publish_config(session, device_id)
    if config is None:
        return ApiResponse(data=None)
    return ApiResponse(data=MqttPublishConfigRead(
        device_id=str(config.device_id),
        topic_template=config.topic_template,
        payload_mode=config.payload_mode,
        publish_interval_seconds=config.publish_interval_seconds,
        qos=config.qos,
        retain=config.retain,
        enabled=config.enabled,
    ))


@router.put(
    "/devices/{device_id}/mqtt",
    response_model=ApiResponse[MqttPublishConfigRead],
)
async def upsert_device_mqtt_config(
    device_id: uuid.UUID,
    data: MqttPublishConfigWrite,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[MqttPublishConfigRead]:
    """Create or update MQTT publish config for a device."""
    config = await mqtt_service.upsert_publish_config(
        session, device_id, data.topic_template, data.payload_mode,
        data.publish_interval_seconds, data.qos, data.retain,
    )
    return ApiResponse(data=MqttPublishConfigRead(
        device_id=str(config.device_id),
        topic_template=config.topic_template,
        payload_mode=config.payload_mode,
        publish_interval_seconds=config.publish_interval_seconds,
        qos=config.qos,
        retain=config.retain,
        enabled=config.enabled,
    ), message="MQTT publish config saved")


@router.delete("/devices/{device_id}/mqtt")
async def delete_device_mqtt_config(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Delete MQTT publish config for a device."""
    deleted = await mqtt_service.delete_publish_config(session, device_id)
    if not deleted:
        raise NotFoundException(detail="MQTT config not found", error_code="NOT_FOUND")
    return ApiResponse(message="MQTT publish config deleted")


@router.post(
    "/devices/{device_id}/mqtt/start",
    response_model=ApiResponse[MqttPublishConfigRead],
)
async def start_mqtt_publishing(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[MqttPublishConfigRead]:
    """Start MQTT publishing for a device."""
    config = await mqtt_service.set_publish_enabled(session, device_id, True)
    if config is None:
        raise NotFoundException(
            detail="MQTT config not found. Configure MQTT first.",
            error_code="NOT_FOUND",
        )
    # Start the actual publishing task
    from app.protocols import protocol_manager
    try:
        mqtt_adapter = protocol_manager.get_adapter("mqtt")
        await mqtt_adapter.start_publishing(device_id, config)  # type: ignore[attr-defined]
    except (KeyError, Exception) as e:
        raise NotFoundException(
            detail=f"Failed to start publishing: {e}",
            error_code="MQTT_ERROR",
        )
    return ApiResponse(data=MqttPublishConfigRead(
        device_id=str(config.device_id),
        topic_template=config.topic_template,
        payload_mode=config.payload_mode,
        publish_interval_seconds=config.publish_interval_seconds,
        qos=config.qos,
        retain=config.retain,
        enabled=config.enabled,
    ), message="MQTT publishing started")


@router.post(
    "/devices/{device_id}/mqtt/stop",
    response_model=ApiResponse[MqttPublishConfigRead],
)
async def stop_mqtt_publishing(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[MqttPublishConfigRead]:
    """Stop MQTT publishing for a device."""
    config = await mqtt_service.set_publish_enabled(session, device_id, False)
    if config is None:
        raise NotFoundException(detail="MQTT config not found", error_code="NOT_FOUND")
    from app.protocols import protocol_manager
    try:
        mqtt_adapter = protocol_manager.get_adapter("mqtt")
        await mqtt_adapter.stop_publishing(device_id)  # type: ignore[attr-defined]
    except (KeyError, Exception):
        pass  # Best-effort stop
    return ApiResponse(data=MqttPublishConfigRead(
        device_id=str(config.device_id),
        topic_template=config.topic_template,
        payload_mode=config.payload_mode,
        publish_interval_seconds=config.publish_interval_seconds,
        qos=config.qos,
        retain=config.retain,
        enabled=config.enabled,
    ), message="MQTT publishing stopped")
```

- [ ] **Step 2: Register routes in main.py**

Add import:
```python
from app.api.routes.mqtt import router as mqtt_router
```

Add to api_v1_router (after system_router line):
```python
api_v1_router.include_router(mqtt_router, prefix="/system", tags=["mqtt"])
```

Note: broker routes go under `/system/mqtt`, device routes under `/system/devices/{id}/mqtt`. This keeps them grouped. Alternatively, device MQTT routes could use a separate router prefix — but to avoid complexity, we put them under the same router and use the full path in the route decorators.

- [ ] **Step 3: Run tests to verify no breakage**

Run: `docker run --rm -v "$(pwd)/backend:/app" -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter" ghostmeter-backend python -m pytest -v --tb=short`

Expected: All existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/mqtt.py backend/app/main.py
git commit -m "feat: add MQTT API routes (broker settings + per-device publish config)"
```

---

## Chunk 3: Backend — MqttAdapter Implementation

### Task 6: Create MqttAdapter

**Files:**
- Create: `backend/app/protocols/mqtt_adapter.py`
- Modify: `backend/app/protocols/__init__.py`
- Modify: `backend/app/main.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add aiomqtt to requirements.txt**

Append: `aiomqtt>=2.0.0`

- [ ] **Step 2: Write MqttAdapter**

```python
"""MQTT publish adapter using aiomqtt."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import aiomqtt

from app.protocols.base import DeviceStats, ProtocolAdapter, RegisterInfo

logger = logging.getLogger(__name__)


class MqttAdapter(ProtocolAdapter):
    """MQTT publish adapter. Reads values from SimulationEngine at publish time."""

    def __init__(self) -> None:
        super().__init__()
        self._client: aiomqtt.Client | None = None
        self._connected: bool = False
        self._available: bool = False
        self._host: str = ""
        self._port: int = 1883
        self._device_registers: dict[UUID, list[RegisterInfo]] = {}
        self._device_meta: dict[UUID, dict] = {}  # device_name, slave_id, template_name
        self._publish_tasks: dict[UUID, asyncio.Task] = {}
        self._publish_configs: dict[UUID, dict] = {}

    async def start(self) -> None:
        """Load broker settings from DB and connect.

        If no broker settings exist, mark as unavailable (no-op).
        This prevents blocking other adapters in start_all().
        """
        from app.database import async_session_factory
        from app.models.mqtt import MqttBrokerSettings
        from sqlalchemy import select

        async with async_session_factory() as session:
            result = await session.execute(select(MqttBrokerSettings).limit(1))
            settings = result.scalar_one_or_none()

        if settings is None:
            logger.info("No MQTT broker settings configured — adapter inactive")
            self._available = False
            return

        self._host = settings.host
        self._port = settings.port

        try:
            self._client = aiomqtt.Client(
                hostname=settings.host,
                port=settings.port,
                username=settings.username or None,
                password=settings.password or None,
                identifier=settings.client_id,
            )
            await self._client.__aenter__()
            self._connected = True
            self._available = True
            logger.info("MQTT connected to %s:%d", settings.host, settings.port)
        except Exception:
            logger.warning("MQTT broker connection failed — adapter inactive", exc_info=True)
            self._available = False
            self._connected = False

    async def stop(self) -> None:
        """Stop all publish tasks and disconnect."""
        for device_id in list(self._publish_tasks):
            await self.stop_publishing(device_id)
        self._publish_tasks.clear()
        self._publish_configs.clear()
        self._device_registers.clear()
        self._device_meta.clear()
        self._device_stats.clear()

        if self._client and self._connected:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
        self._client = None
        self._connected = False
        self._available = False
        logger.info("MQTT adapter stopped")

    async def _do_add_device(
        self, device_id: UUID, slave_id: int, registers: list[RegisterInfo],
    ) -> None:
        """Store register map for payload building."""
        self._device_registers[device_id] = registers

    async def _do_remove_device(self, device_id: UUID) -> None:
        """Stop publishing and clean up."""
        await self.stop_publishing(device_id)
        self._device_registers.pop(device_id, None)
        self._device_meta.pop(device_id, None)
        self._publish_configs.pop(device_id, None)

    async def update_register(
        self, device_id: UUID, address: int, function_code: int,
        value: float, data_type: str, byte_order: str,
    ) -> None:
        """No-op. MQTT reads values from SimulationEngine at publish time."""
        pass

    def get_status(self) -> dict:
        """Return adapter status."""
        return {
            "broker_host": self._host,
            "broker_port": self._port,
            "connected": self._connected,
            "available": self._available,
            "publishing_devices": len(self._publish_tasks),
        }

    # --- MQTT-specific ---

    def set_device_meta(
        self, device_id: UUID, device_name: str,
        slave_id: int, template_name: str,
    ) -> None:
        """Store device metadata for topic template rendering."""
        self._device_meta[device_id] = {
            "device_name": device_name,
            "slave_id": slave_id,
            "template_name": template_name,
        }

    async def start_publishing(self, device_id: UUID, config) -> None:
        """Start a per-device publish task."""
        if not self._connected or not self._client:
            raise RuntimeError("MQTT broker not connected")

        await self.stop_publishing(device_id)

        self._publish_configs[device_id] = {
            "topic_template": config.topic_template,
            "payload_mode": config.payload_mode,
            "interval": config.publish_interval_seconds,
            "qos": config.qos,
            "retain": config.retain,
        }
        task = asyncio.create_task(self._publish_loop(device_id))
        self._publish_tasks[device_id] = task
        logger.info("Started MQTT publishing for device %s", device_id)

    async def stop_publishing(self, device_id: UUID) -> None:
        """Cancel a device's publish task."""
        task = self._publish_tasks.pop(device_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._publish_configs.pop(device_id, None)
        logger.info("Stopped MQTT publishing for device %s", device_id)

    async def reconnect(self, host: str, port: int,
                        username: str, password: str,
                        client_id: str, use_tls: bool) -> None:
        """Reconnect with new broker settings."""
        # Stop all publishing
        for device_id in list(self._publish_tasks):
            await self.stop_publishing(device_id)

        # Disconnect old
        if self._client and self._connected:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass

        # Connect new
        self._host = host
        self._port = port
        try:
            self._client = aiomqtt.Client(
                hostname=host, port=port,
                username=username or None,
                password=password or None,
                identifier=client_id,
            )
            await self._client.__aenter__()
            self._connected = True
            self._available = True
            logger.info("MQTT reconnected to %s:%d", host, port)
        except Exception:
            logger.warning("MQTT reconnect failed", exc_info=True)
            self._connected = False

    async def _publish_loop(self, device_id: UUID) -> None:
        """Per-device publish loop."""
        from app.simulation import simulation_engine

        config = self._publish_configs.get(device_id)
        if not config:
            return

        meta = self._device_meta.get(device_id, {})
        interval = config["interval"]

        while True:
            try:
                await asyncio.sleep(interval)

                if not self._connected or not self._client:
                    stats = self._device_stats.get(device_id)
                    if stats:
                        stats.request_count += 1
                        stats.error_count += 1
                    continue

                values = simulation_engine.get_current_values(device_id)
                if not values:
                    continue

                now = datetime.now(timezone.utc).isoformat()

                if config["payload_mode"] == "batch":
                    topic = self._render_topic(config["topic_template"], meta)
                    payload = json.dumps({
                        "device": meta.get("device_name", str(device_id)),
                        "timestamp": now,
                        "values": values,
                    })
                    await self._publish_one(
                        device_id, topic, payload, config["qos"], config["retain"],
                    )
                else:  # per_register
                    for reg_name, reg_value in values.items():
                        topic = self._render_topic(
                            config["topic_template"], meta, reg_name,
                        )
                        payload = json.dumps({
                            "value": reg_value,
                            "timestamp": now,
                        })
                        await self._publish_one(
                            device_id, topic, payload, config["qos"], config["retain"],
                        )

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("MQTT publish error for device %s: %s", device_id, e)
                stats = self._device_stats.get(device_id)
                if stats:
                    stats.request_count += 1
                    stats.error_count += 1

    async def _publish_one(
        self, device_id: UUID, topic: str, payload: str, qos: int, retain: bool,
    ) -> None:
        """Publish a single message and update stats."""
        stats = self._device_stats.get(device_id)
        if stats:
            stats.request_count += 1
        try:
            await self._client.publish(topic, payload, qos=qos, retain=retain)  # type: ignore[union-attr]
            if stats:
                stats.success_count += 1
        except Exception:
            if stats:
                stats.error_count += 1
            raise

    def _render_topic(
        self, template: str, meta: dict, register_name: str = "",
    ) -> str:
        """Render topic template with variables."""
        return template.format(
            device_name=meta.get("device_name", "unknown"),
            slave_id=meta.get("slave_id", 0),
            template_name=meta.get("template_name", "unknown"),
            register_name=register_name,
        )
```

- [ ] **Step 3: Register MqttAdapter in __init__.py**

No change needed in `__init__.py` — adapter is registered in `main.py` lifespan.

- [ ] **Step 4: Register MqttAdapter in main.py lifespan**

Add import at top:
```python
from app.protocols.mqtt_adapter import MqttAdapter
```

Add after Modbus adapter registration (after `protocol_manager.register_adapter("modbus_tcp", modbus_adapter)` line, before `await protocol_manager.start_all()`):
```python
    # Register MQTT adapter
    mqtt_adapter = MqttAdapter()
    protocol_manager.register_adapter("mqtt", mqtt_adapter)
```

- [ ] **Step 5: Rebuild backend, verify startup**

Run: `docker compose up -d --build backend`

Check logs: `docker compose logs backend --tail 20`

Expected: Logs show "MQTT broker not configured — adapter inactive" (no broker set up yet), Modbus starts normally.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/app/protocols/mqtt_adapter.py backend/app/main.py
git commit -m "feat: implement MqttAdapter with publish loop and broker management"
```

---

## Chunk 4: Backend — Device Service Integration + Monitor Service

### Task 7: Integrate MQTT publishing into device lifecycle

**Files:**
- Modify: `backend/app/services/device_service.py`

- [ ] **Step 1: Add MQTT auto-start in start_device**

After the simulation engine start block (after `await simulation_engine.start_device(device.id)` try/except), add:

```python
    # Auto-start MQTT publishing if configured and enabled
    try:
        mqtt_config = await mqtt_service.get_publish_config(session, device.id)
        if mqtt_config and mqtt_config.enabled:
            mqtt_adapter = protocol_manager.get_adapter("mqtt")
            mqtt_adapter.set_device_meta(  # type: ignore[attr-defined]
                device.id, device.name, device.slave_id,
                template.name,
            )
            await mqtt_adapter.start_publishing(device.id, mqtt_config)  # type: ignore[attr-defined]
    except Exception as e:
        logger.warning("Failed to start MQTT publishing for device %s: %s", device_id, e)
```

Add import at top of file:
```python
from app.services import mqtt_service
```

- [ ] **Step 2: Add MQTT stop in stop_device**

Before the protocol manager `remove_device` block, add:

```python
    # Stop MQTT publishing (best-effort)
    try:
        mqtt_adapter = protocol_manager.get_adapter("mqtt")
        await mqtt_adapter.stop_publishing(device.id)  # type: ignore[attr-defined]
    except (KeyError, Exception):
        pass
```

- [ ] **Step 3: Run tests**

Run: `docker run --rm -v "$(pwd)/backend:/app" -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter" ghostmeter-backend python -m pytest -v --tb=short`

Expected: All existing tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/device_service.py
git commit -m "feat: integrate MQTT publishing into device start/stop lifecycle"
```

---

### Task 8: Update MonitorService to include MQTT stats

**Files:**
- Modify: `backend/app/services/monitor_service.py`

- [ ] **Step 1: Add MQTT stats aggregation**

After the Modbus stats block (the `stats = protocol_manager.get_stats(...)` section), add:

```python
            mqtt_stats = protocol_manager.get_stats("mqtt", device_id)
            if mqtt_stats:
                stats_data["mqtt_request_count"] = mqtt_stats.request_count
                stats_data["mqtt_success_count"] = mqtt_stats.success_count
                stats_data["mqtt_error_count"] = mqtt_stats.error_count
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/monitor_service.py
git commit -m "feat: add MQTT stats to monitor service snapshot"
```

---

## Chunk 5: Docker + Mosquitto Setup

### Task 9: Add mosquitto to Docker Compose

**Files:**
- Modify: `docker-compose.yml`
- Create: `mosquitto.conf`

- [ ] **Step 1: Create mosquitto.conf**

```
listener 1883
allow_anonymous true
```

- [ ] **Step 2: Add mosquitto service to docker-compose.yml**

Add before the `volumes:` section:

```yaml
  mosquitto:
    image: eclipse-mosquitto:2
    container_name: ghostmeter-mosquitto
    profiles: ["mqtt"]
    ports:
      - "1883:1883"
    volumes:
      - ./mosquitto.conf:/mosquitto/config/mosquitto.conf
    restart: unless-stopped
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml mosquitto.conf
git commit -m "feat: add optional mosquitto MQTT broker to Docker Compose"
```

---

## Chunk 6: Frontend — MQTT Broker Settings + Device MQTT Config

### Task 10: Create TypeScript types and API client

**Files:**
- Create: `frontend/src/types/mqtt.ts`
- Create: `frontend/src/services/mqttApi.ts`

- [ ] **Step 1: Write TypeScript interfaces**

```typescript
export interface MqttBrokerSettings {
  host: string;
  port: number;
  username: string;
  password: string;
  client_id: string;
  use_tls: boolean;
}

export interface MqttPublishConfig {
  device_id: string;
  topic_template: string;
  payload_mode: "batch" | "per_register";
  publish_interval_seconds: number;
  qos: number;
  retain: boolean;
  enabled: boolean;
}

export interface MqttPublishConfigWrite {
  topic_template: string;
  payload_mode: "batch" | "per_register";
  publish_interval_seconds: number;
  qos: number;
  retain: boolean;
}

export interface MqttTestResult {
  success: boolean;
  message: string;
}
```

- [ ] **Step 2: Write API client**

```typescript
import { apiClient } from "./apiClient";
import type { ApiResponse } from "../types";
import type {
  MqttBrokerSettings,
  MqttPublishConfig,
  MqttPublishConfigWrite,
  MqttTestResult,
} from "../types/mqtt";

export const mqttApi = {
  getBrokerSettings: () =>
    apiClient.get<ApiResponse<MqttBrokerSettings>>("/system/mqtt").then((r) => r.data),

  updateBrokerSettings: (data: MqttBrokerSettings) =>
    apiClient.put<ApiResponse<MqttBrokerSettings>>("/system/mqtt", data).then((r) => r.data),

  testConnection: (data: MqttBrokerSettings) =>
    apiClient.post<ApiResponse<MqttTestResult>>("/system/mqtt/test", data).then((r) => r.data),

  getDeviceConfig: (deviceId: string) =>
    apiClient.get<ApiResponse<MqttPublishConfig | null>>(`/system/devices/${deviceId}/mqtt`).then((r) => r.data),

  updateDeviceConfig: (deviceId: string, data: MqttPublishConfigWrite) =>
    apiClient.put<ApiResponse<MqttPublishConfig>>(`/system/devices/${deviceId}/mqtt`, data).then((r) => r.data),

  deleteDeviceConfig: (deviceId: string) =>
    apiClient.delete<ApiResponse>(`/system/devices/${deviceId}/mqtt`).then((r) => r.data),

  startPublishing: (deviceId: string) =>
    apiClient.post<ApiResponse<MqttPublishConfig>>(`/system/devices/${deviceId}/mqtt/start`).then((r) => r.data),

  stopPublishing: (deviceId: string) =>
    apiClient.post<ApiResponse<MqttPublishConfig>>(`/system/devices/${deviceId}/mqtt/stop`).then((r) => r.data),
};
```

- [ ] **Step 3: Export types**

Add to `frontend/src/types/index.ts`:
```typescript
export type { MqttBrokerSettings, MqttPublishConfig, MqttPublishConfigWrite, MqttTestResult } from "./mqtt";
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/mqtt.ts frontend/src/services/mqttApi.ts frontend/src/types/index.ts
git commit -m "feat: add MQTT TypeScript types and API client"
```

---

### Task 11: Create MQTT Broker Settings component

**Files:**
- Create: `frontend/src/pages/Settings/MqttBrokerSettings.tsx`
- Modify: `frontend/src/pages/Settings/index.tsx`

- [ ] **Step 1: Write MqttBrokerSettings component**

A Card with form fields for host, port, username, password, client_id, use_tls, Save button, and Test Connection button. Uses `mqttApi` for API calls. Shows success/error status after test.

(Implementation details: standard Ant Design Form with Input, InputNumber, Switch. Test Connection calls `mqttApi.testConnection` with current form values, shows result via `message.success` or `message.error`.)

- [ ] **Step 2: Add to Settings page**

Import and add `<MqttBrokerSettings />` after the existing Configuration Management card in `index.tsx`.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Settings/MqttBrokerSettings.tsx frontend/src/pages/Settings/index.tsx
git commit -m "feat: add MQTT broker settings UI to Settings page"
```

---

### Task 12: Create MQTT Publish Config component

**Files:**
- Create: `frontend/src/pages/Devices/MqttPublishConfig.tsx`
- Modify: `frontend/src/pages/Devices/DeviceDetail.tsx`

- [ ] **Step 1: Write MqttPublishConfig component**

A Card with:
- Topic template Input
- Payload mode Radio (Batch / Per-register)
- Interval InputNumber
- QoS Select (0/1/2)
- Retain Switch
- Save Config button
- Start/Stop Publishing button (green/red, prominent)
- Status badge (Publishing / Stopped)

Props: `deviceId: string`

Loads config on mount via `mqttApi.getDeviceConfig`. Save calls `mqttApi.updateDeviceConfig`. Start/Stop calls `mqttApi.startPublishing` / `mqttApi.stopPublishing`.

- [ ] **Step 2: Add to DeviceDetail page**

Import and add `<MqttPublishConfig deviceId={id} />` as a new Card after the Register Map card.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Devices/MqttPublishConfig.tsx frontend/src/pages/Devices/DeviceDetail.tsx
git commit -m "feat: add MQTT publish config UI to Device Detail page"
```

---

## Chunk 7: System Export/Import + Final Verification

### Task 13: Add MQTT data to system export/import

**Files:**
- Modify: `backend/app/schemas/system.py`
- Modify: `backend/app/services/system_service.py`

- [ ] **Step 1: Add MQTT schemas to system.py**

Add to `SystemExport`:
```python
mqtt_broker: MqttBrokerSettingsRead | None = None
mqtt_publish_configs: list[MqttPublishConfigExport] = []
```

Add to `SystemImport`:
```python
mqtt_broker: MqttBrokerSettingsWrite | None = None
mqtt_publish_configs: list[MqttPublishConfigExport] = []
```

Add to `ImportResult`:
```python
mqtt_publish_configs_set: int = 0
```

Add necessary imports from `app.schemas.mqtt`.

- [ ] **Step 2: Update system_service.py export**

In `export_config`, add queries for `MqttBrokerSettings` and `MqttPublishConfig`, include in export data.

- [ ] **Step 3: Update system_service.py import**

In `import_config`, handle `mqtt_broker` and `mqtt_publish_configs` upsert.

- [ ] **Step 4: Run all backend tests**

Run: `docker run --rm -v "$(pwd)/backend:/app" -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter" ghostmeter-backend python -m pytest -v --tb=short`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/system.py backend/app/services/system_service.py
git commit -m "feat: include MQTT configs in system export/import"
```

---

### Task 14: Final verification and documentation updates

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/development-log.md`
- Modify: `docs/development-phases.md`
- Modify: `docs/api-reference.md`

- [ ] **Step 1: Run full backend test suite**

Run: `docker run --rm -v "$(pwd)/backend:/app" -w /app --network ghostmeter_default -e DATABASE_URL="postgresql+asyncpg://ghostmeter:ghostmeter@postgres:5432/ghostmeter" ghostmeter-backend python -m pytest -v --tb=short`

- [ ] **Step 2: Run frontend TypeScript check**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 3: Update documentation files**

Update CHANGELOG, development-log, development-phases, api-reference per CLAUDE.md push rules.

- [ ] **Step 4: Commit docs**

```bash
git add CHANGELOG.md docs/
git commit -m "docs: update documentation for MQTT adapter feature"
```
