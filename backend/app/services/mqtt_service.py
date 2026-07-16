"""MQTT config CRUD service."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import DeviceInstance
from app.models.mqtt import MqttBrokerSettings, MqttPublishConfig
from app.models.template import DeviceTemplate

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


async def resume_enabled_publishing(session: AsyncSession) -> int:
    """(Re)start publish tasks for enabled configs on running devices.

    Needed after an adapter reconnect, which cancels every publish task.
    Returns the number of devices whose publishing was started.
    """
    from app.protocols import protocol_manager

    adapter = protocol_manager.get_adapter("mqtt")
    if adapter is None:
        return 0

    result = await session.execute(
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
    started = 0
    for config, device_name, slave_id, template_name in result.all():
        try:
            adapter.set_device_meta(  # type: ignore[attr-defined]
                config.device_id, device_name, slave_id, template_name,
            )
            await adapter.start_publishing(config.device_id, config)  # type: ignore[attr-defined]
            started += 1
        except Exception as e:
            logger.warning(
                "Failed to resume MQTT publishing for device %s: %s",
                config.device_id, e,
            )
    return started


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
