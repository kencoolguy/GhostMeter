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
        self._device_meta: dict[UUID, dict] = {}
        self._publish_tasks: dict[UUID, asyncio.Task] = {}
        self._publish_configs: dict[UUID, dict] = {}

    async def start(self) -> None:
        """Load broker settings from DB and connect.

        If no broker settings exist, mark as unavailable (no-op).
        This prevents blocking other adapters in start_all().
        """
        from sqlalchemy import select

        from app.database import async_session_factory
        from app.models.mqtt import MqttBrokerSettings

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

    async def reconnect(
        self, host: str, port: int,
        username: str, password: str,
        client_id: str, use_tls: bool,
    ) -> None:
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
