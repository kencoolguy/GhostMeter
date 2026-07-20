"""API routes for MQTT broker CRUD and per-(device, broker) publish config."""

import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.exceptions import AppException, NotFoundException
from app.models.mqtt import MqttBrokerSettings, MqttPublishConfig
from app.schemas.common import ApiResponse
from app.schemas.mqtt import (
    MqttBrokerRead,
    MqttBrokerWrite,
    MqttPublishConfigRead,
    MqttPublishConfigWrite,
    MqttTestResult,
)
from app.services import mqtt_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_mqtt_adapter():
    """The registered mqtt adapter, or None when unavailable."""
    from app.protocols import protocol_manager

    return protocol_manager.get_adapter("mqtt")


def _broker_read(broker: MqttBrokerSettings, adapter) -> MqttBrokerRead:
    """Serialize a broker row with its live connection state."""
    connected = False
    if adapter is not None:
        try:
            connected = bool(adapter.is_broker_connected(broker.id))
        except Exception:
            connected = False
    return MqttBrokerRead(
        id=str(broker.id),
        name=broker.name,
        host=broker.host,
        port=broker.port,
        username=broker.username,
        password="****" if broker.password else "",
        client_id=broker.client_id,
        use_tls=broker.use_tls,
        connected=connected,
    )


def _config_read(config: MqttPublishConfig, broker_name: str) -> MqttPublishConfigRead:
    """Serialize a publish config row."""
    return MqttPublishConfigRead(
        device_id=str(config.device_id),
        broker_id=str(config.broker_id),
        broker_name=broker_name,
        topic_template=config.topic_template,
        payload_mode=config.payload_mode,
        publish_interval_seconds=config.publish_interval_seconds,
        qos=config.qos,
        retain=config.retain,
        enabled=config.enabled,
    )


# --- Brokers ---


@router.get("/mqtt/brokers", response_model=ApiResponse[list[MqttBrokerRead]])
async def list_brokers(
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[MqttBrokerRead]]:
    """List all MQTT brokers."""
    brokers = await mqtt_service.list_brokers(session)
    adapter = _get_mqtt_adapter()
    return ApiResponse(data=[_broker_read(b, adapter) for b in brokers])


@router.post(
    "/mqtt/brokers", response_model=ApiResponse[MqttBrokerRead], status_code=201,
)
async def create_broker(
    data: MqttBrokerWrite,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[MqttBrokerRead]:
    """Create an MQTT broker and connect the running adapter to it."""
    broker = await mqtt_service.create_broker(session, data)

    adapter = _get_mqtt_adapter()
    if adapter is not None:
        try:
            await adapter.connect_broker(broker.id, broker)  # type: ignore[attr-defined]
        except Exception:
            logger.warning("Connecting new MQTT broker failed", exc_info=True)

    return ApiResponse(
        data=_broker_read(broker, adapter), message="MQTT broker created",
    )


@router.put(
    "/mqtt/brokers/{broker_id}", response_model=ApiResponse[MqttBrokerRead],
)
async def update_broker(
    broker_id: uuid.UUID,
    data: MqttBrokerWrite,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[MqttBrokerRead]:
    """Update a broker, reconnect only it, and resume only its publish tasks."""
    broker = await mqtt_service.update_broker(session, broker_id, data)

    adapter = _get_mqtt_adapter()
    if adapter is not None:
        try:
            connected = await adapter.reconnect_broker(  # type: ignore[attr-defined]
                broker.id, broker,
            )
            if connected:
                await mqtt_service.resume_enabled_publishing(session, broker.id)
        except Exception:
            logger.warning("Reconnecting MQTT broker failed", exc_info=True)

    return ApiResponse(
        data=_broker_read(broker, adapter), message="MQTT broker updated",
    )


@router.delete("/mqtt/brokers/{broker_id}")
async def delete_broker(
    broker_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Delete a broker (refused while device configs reference it)."""
    await mqtt_service.delete_broker(session, broker_id)

    adapter = _get_mqtt_adapter()
    if adapter is not None:
        try:
            await adapter.disconnect_broker(broker_id)  # type: ignore[attr-defined]
        except Exception:
            logger.warning("Disconnecting deleted MQTT broker failed", exc_info=True)

    return ApiResponse(message="MQTT broker deleted")


@router.post("/mqtt/test", response_model=ApiResponse[MqttTestResult])
async def test_broker_connection(
    data: MqttBrokerWrite,
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
    response_model=ApiResponse[list[MqttPublishConfigRead]],
)
async def list_device_mqtt_configs(
    device_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[MqttPublishConfigRead]]:
    """List MQTT publish configs for a device (one per broker)."""
    configs = await mqtt_service.list_publish_configs(session, device_id)
    return ApiResponse(data=[_config_read(c, name) for c, name in configs])


@router.put(
    "/devices/{device_id}/mqtt/{broker_id}",
    response_model=ApiResponse[MqttPublishConfigRead],
)
async def upsert_device_mqtt_config(
    device_id: uuid.UUID,
    broker_id: uuid.UUID,
    data: MqttPublishConfigWrite,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[MqttPublishConfigRead]:
    """Create or update the publish config for one (device, broker) pair."""
    config = await mqtt_service.upsert_publish_config(
        session, device_id, broker_id, data.topic_template, data.payload_mode,
        data.publish_interval_seconds, data.qos, data.retain,
    )
    broker = await mqtt_service.get_broker(session, broker_id)
    broker_name = broker.name if broker else ""
    return ApiResponse(
        data=_config_read(config, broker_name), message="MQTT publish config saved",
    )


@router.delete("/devices/{device_id}/mqtt/{broker_id}")
async def delete_device_mqtt_config(
    device_id: uuid.UUID,
    broker_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse:
    """Delete the publish config for one (device, broker) pair."""
    deleted = await mqtt_service.delete_publish_config(session, device_id, broker_id)
    if not deleted:
        raise NotFoundException(detail="MQTT config not found", error_code="NOT_FOUND")

    adapter = _get_mqtt_adapter()
    if adapter is not None:
        try:
            await adapter.stop_publishing(device_id, broker_id)  # type: ignore[attr-defined]
        except Exception:
            pass  # Best-effort stop
    return ApiResponse(message="MQTT publish config deleted")


async def _target_configs(
    session: AsyncSession, device_id: uuid.UUID, broker_id: uuid.UUID | None,
) -> list[tuple[MqttPublishConfig, str]]:
    """The (config, broker_name) pairs a start/stop call operates on."""
    configs = await mqtt_service.list_publish_configs(session, device_id)
    if broker_id is not None:
        configs = [(c, name) for c, name in configs if c.broker_id == broker_id]
    if not configs:
        raise NotFoundException(
            detail="MQTT config not found. Configure MQTT first.",
            error_code="NOT_FOUND",
        )
    return configs


@router.post(
    "/devices/{device_id}/mqtt/start",
    response_model=ApiResponse[list[MqttPublishConfigRead]],
)
async def start_mqtt_publishing(
    device_id: uuid.UUID,
    broker_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[MqttPublishConfigRead]]:
    """Start MQTT publishing for a device — one broker, or all configured."""
    configs = await _target_configs(session, device_id, broker_id)

    adapter = _get_mqtt_adapter()
    if adapter is None:
        raise AppException(
            status_code=500,
            error_code="MQTT_ERROR",
            detail="MQTT protocol adapter is not registered",
        )

    # The publish loop renders topics from device meta — set it first,
    # otherwise topics come out as "unknown" (issue #82).
    meta = await mqtt_service.get_device_meta(session, device_id)
    if meta is not None:
        device_name, slave_id, template_name = meta
        adapter.set_device_meta(  # type: ignore[attr-defined]
            device_id, device_name, slave_id, template_name,
        )

    started: list[MqttPublishConfigRead] = []
    errors: list[str] = []
    for config, broker_name in configs:
        await mqtt_service.set_publish_enabled(
            session, device_id, config.broker_id, True,
        )
        try:
            await adapter.start_publishing(  # type: ignore[attr-defined]
                device_id, config.broker_id, config,
            )
        except Exception as e:
            # Revert enabled flag for this pair only
            await mqtt_service.set_publish_enabled(
                session, device_id, config.broker_id, False,
            )
            errors.append(f"{broker_name}: {e}")
            continue
        started.append(_config_read(config, broker_name))

    if not started:
        raise AppException(
            status_code=500,
            error_code="MQTT_ERROR",
            detail=f"Failed to start publishing: {'; '.join(errors)}",
        )

    message = "MQTT publishing started"
    if errors:
        message += f" (failed for: {'; '.join(errors)})"
    return ApiResponse(data=started, message=message)


@router.post(
    "/devices/{device_id}/mqtt/stop",
    response_model=ApiResponse[list[MqttPublishConfigRead]],
)
async def stop_mqtt_publishing(
    device_id: uuid.UUID,
    broker_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> ApiResponse[list[MqttPublishConfigRead]]:
    """Stop MQTT publishing for a device — one broker, or all configured."""
    configs = await _target_configs(session, device_id, broker_id)

    stopped: list[MqttPublishConfigRead] = []
    adapter = _get_mqtt_adapter()
    for config, broker_name in configs:
        updated = await mqtt_service.set_publish_enabled(
            session, device_id, config.broker_id, False,
        )
        if adapter is not None:
            try:
                await adapter.stop_publishing(  # type: ignore[attr-defined]
                    device_id, config.broker_id,
                )
            except Exception:
                pass  # Best-effort stop
        stopped.append(_config_read(updated or config, broker_name))

    return ApiResponse(data=stopped, message="MQTT publishing stopped")
