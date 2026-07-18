"""MQTT broker and publish config CRUD service."""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictException, NotFoundException
from app.models.device import DeviceInstance
from app.models.mqtt import MqttBrokerSettings, MqttPublishConfig
from app.models.template import DeviceTemplate
from app.schemas.mqtt import MqttBrokerWrite

logger = logging.getLogger(__name__)

MASKED_PASSWORD = "****"


# --- Brokers ---


async def list_brokers(session: AsyncSession) -> list[MqttBrokerSettings]:
    """List all MQTT brokers ordered by name."""
    result = await session.execute(
        select(MqttBrokerSettings).order_by(MqttBrokerSettings.name)
    )
    return list(result.scalars().all())


async def get_broker(
    session: AsyncSession, broker_id: uuid.UUID,
) -> MqttBrokerSettings | None:
    """Get one MQTT broker by id."""
    result = await session.execute(
        select(MqttBrokerSettings).where(MqttBrokerSettings.id == broker_id)
    )
    return result.scalar_one_or_none()


async def _ensure_unique_name(
    session: AsyncSession, name: str, exclude_id: uuid.UUID | None = None,
) -> None:
    """Raise ConflictException when another broker already uses this name."""
    stmt = select(MqttBrokerSettings.id).where(MqttBrokerSettings.name == name)
    if exclude_id is not None:
        stmt = stmt.where(MqttBrokerSettings.id != exclude_id)
    if (await session.execute(stmt)).first() is not None:
        raise ConflictException(
            detail=f"MQTT broker name '{name}' already exists",
            error_code="DUPLICATE_NAME",
        )


async def create_broker(
    session: AsyncSession, data: MqttBrokerWrite,
) -> MqttBrokerSettings:
    """Create a new MQTT broker."""
    await _ensure_unique_name(session, data.name)
    broker = MqttBrokerSettings(
        name=data.name,
        host=data.host,
        port=data.port,
        username=data.username,
        password=data.password,
        client_id=data.client_id,
        use_tls=data.use_tls,
    )
    session.add(broker)
    await session.commit()
    await session.refresh(broker)
    return broker


async def update_broker(
    session: AsyncSession, broker_id: uuid.UUID, data: MqttBrokerWrite,
) -> MqttBrokerSettings:
    """Update an MQTT broker; a masked password keeps the stored one."""
    broker = await get_broker(session, broker_id)
    if broker is None:
        raise NotFoundException(detail="MQTT broker not found")
    await _ensure_unique_name(session, data.name, exclude_id=broker_id)
    broker.name = data.name
    broker.host = data.host
    broker.port = data.port
    broker.username = data.username
    if data.password != MASKED_PASSWORD:
        broker.password = data.password
    broker.client_id = data.client_id
    broker.use_tls = data.use_tls
    await session.commit()
    await session.refresh(broker)
    return broker


async def count_configs_for_broker(
    session: AsyncSession, broker_id: uuid.UUID,
) -> int:
    """Number of publish configs referencing this broker."""
    result = await session.execute(
        select(func.count())
        .select_from(MqttPublishConfig)
        .where(MqttPublishConfig.broker_id == broker_id)
    )
    return int(result.scalar_one())


async def delete_broker(session: AsyncSession, broker_id: uuid.UUID) -> None:
    """Delete a broker; refused while publish configs still reference it."""
    broker = await get_broker(session, broker_id)
    if broker is None:
        raise NotFoundException(detail="MQTT broker not found")
    in_use = await count_configs_for_broker(session, broker_id)
    if in_use > 0:
        raise ConflictException(
            detail=(
                f"MQTT broker '{broker.name}' is referenced by {in_use} device "
                "publish config(s); remove those first"
            ),
            error_code="BROKER_IN_USE",
        )
    await session.delete(broker)
    await session.commit()


# --- Publish configs ---


async def list_publish_configs(
    session: AsyncSession, device_id: uuid.UUID,
) -> list[tuple[MqttPublishConfig, str]]:
    """All (config, broker_name) pairs for a device, ordered by broker name."""
    result = await session.execute(
        select(MqttPublishConfig, MqttBrokerSettings.name)
        .join(MqttBrokerSettings, MqttPublishConfig.broker_id == MqttBrokerSettings.id)
        .where(MqttPublishConfig.device_id == device_id)
        .order_by(MqttBrokerSettings.name)
    )
    return [(row[0], row[1]) for row in result.all()]


async def get_publish_config(
    session: AsyncSession, device_id: uuid.UUID, broker_id: uuid.UUID,
) -> MqttPublishConfig | None:
    """Get the publish config for one (device, broker) pair."""
    result = await session.execute(
        select(MqttPublishConfig).where(
            MqttPublishConfig.device_id == device_id,
            MqttPublishConfig.broker_id == broker_id,
        )
    )
    return result.scalar_one_or_none()


async def upsert_publish_config(
    session: AsyncSession,
    device_id: uuid.UUID,
    broker_id: uuid.UUID,
    topic_template: str,
    payload_mode: str,
    publish_interval_seconds: int,
    qos: int,
    retain: bool,
) -> MqttPublishConfig:
    """Create or update the publish config for one (device, broker) pair."""
    broker = await get_broker(session, broker_id)
    if broker is None:
        raise NotFoundException(detail="MQTT broker not found")
    config = await get_publish_config(session, device_id, broker_id)
    if config is None:
        config = MqttPublishConfig(
            device_id=device_id,
            broker_id=broker_id,
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
    session: AsyncSession, device_id: uuid.UUID, broker_id: uuid.UUID,
) -> bool:
    """Delete the publish config for one (device, broker) pair."""
    config = await get_publish_config(session, device_id, broker_id)
    if config is None:
        return False
    await session.delete(config)
    await session.commit()
    return True


async def set_publish_enabled(
    session: AsyncSession,
    device_id: uuid.UUID,
    broker_id: uuid.UUID,
    enabled: bool,
) -> MqttPublishConfig | None:
    """Set the enabled flag on one (device, broker) publish config."""
    config = await get_publish_config(session, device_id, broker_id)
    if config is None:
        return None
    config.enabled = enabled
    await session.commit()
    await session.refresh(config)
    return config


async def get_device_meta(
    session: AsyncSession, device_id: uuid.UUID,
) -> tuple[str, int, str] | None:
    """Device name, slave_id and template name for MQTT topic rendering."""
    result = await session.execute(
        select(DeviceInstance.name, DeviceInstance.slave_id, DeviceTemplate.name)
        .join(DeviceTemplate, DeviceInstance.template_id == DeviceTemplate.id)
        .where(DeviceInstance.id == device_id)
    )
    row = result.first()
    if row is None:
        return None
    return (row[0], row[1], row[2])


async def resume_enabled_publishing(
    session: AsyncSession, broker_id: uuid.UUID | None = None,
) -> int:
    """(Re)start publish tasks for enabled configs on running devices.

    Needed after a broker reconnect (which cancels that broker's publish
    tasks) and on backend startup. With `broker_id`, only that broker's
    configs are resumed. Returns the number of (device, broker) pairs whose
    publishing was started.
    """
    from app.protocols import protocol_manager

    adapter = protocol_manager.get_adapter("mqtt")
    if adapter is None:
        return 0

    stmt = (
        select(
            MqttPublishConfig,
            DeviceInstance.name,
            DeviceInstance.slave_id,
            DeviceTemplate.name,
        )
        .join(DeviceInstance, MqttPublishConfig.device_id == DeviceInstance.id)
        .join(DeviceTemplate, DeviceInstance.template_id == DeviceTemplate.id)
        .where(
            MqttPublishConfig.enabled.is_(True),
            DeviceInstance.status == "running",
        )
    )
    if broker_id is not None:
        stmt = stmt.where(MqttPublishConfig.broker_id == broker_id)

    result = await session.execute(stmt)
    started = 0
    for config, device_name, slave_id, template_name in result.all():
        try:
            adapter.set_device_meta(  # type: ignore[attr-defined]
                config.device_id, device_name, slave_id, template_name,
            )
            await adapter.start_publishing(  # type: ignore[attr-defined]
                config.device_id, config.broker_id, config,
            )
            started += 1
        except Exception as e:
            logger.warning(
                "Failed to resume MQTT publishing for device %s to broker %s: %s",
                config.device_id, config.broker_id, e,
            )
    return started
