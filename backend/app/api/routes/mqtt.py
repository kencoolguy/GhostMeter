"""API routes for MQTT broker settings and per-device publish config."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.exceptions import NotFoundException
from app.schemas.common import ApiResponse
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
    except Exception as e:
        # Revert enabled flag on failure
        await mqtt_service.set_publish_enabled(session, device_id, False)
        raise NotFoundException(
            detail=f"Failed to start publishing: {e}",
            error_code="MQTT_ERROR",
        ) from e
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
