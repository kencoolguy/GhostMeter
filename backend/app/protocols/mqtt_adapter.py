"""MQTT publish adapter using aiomqtt.

Manages one aiomqtt client per configured broker; publish tasks are keyed by
(device_id, broker_id) so one device can publish to several brokers with
independent configs, and one broker's failure or reconnect never touches
another broker's tasks.
"""

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from uuid import UUID

import aiomqtt

from app.protocols.base import ProtocolAdapter, RegisterInfo

logger = logging.getLogger(__name__)


class MqttAdapter(ProtocolAdapter):
    """MQTT publish adapter. Reads values from SimulationEngine at publish time."""

    # MQTT is publish-only — there is no request/response channel to return a
    # protocol error on, so the "exception" fault type cannot be simulated.
    supported_fault_types = frozenset({"delay", "timeout", "intermittent"})

    # aiomqtt has no built-in reconnect: a dropped connection stays dead until
    # a new client is opened. These bound the retry backoff for the per-broker
    # reconnect task (overridable per instance for tests).
    RECONNECT_INITIAL_DELAY: float = 1.0
    RECONNECT_MAX_DELAY: float = 60.0

    def __init__(self) -> None:
        super().__init__()
        self._clients: dict[UUID, aiomqtt.Client] = {}
        self._broker_info: dict[UUID, dict] = {}
        self._broker_settings: dict[UUID, object] = {}
        self._reconnect_tasks: dict[UUID, asyncio.Task] = {}
        self._available: bool = False
        self._device_registers: dict[UUID, list[RegisterInfo]] = {}
        self._device_meta: dict[UUID, dict] = {}
        self._publish_tasks: dict[tuple[UUID, UUID], asyncio.Task] = {}
        self._publish_configs: dict[tuple[UUID, UUID], dict] = {}

    async def start(self) -> None:
        """Load all broker rows from DB and connect each one independently.

        If no brokers are configured, mark as unavailable (no-op). A broker
        that fails to connect is recorded as disconnected but never blocks
        the others (or start_all()).
        """
        from sqlalchemy import select

        from app.database import async_session_factory
        from app.models.mqtt import MqttBrokerSettings

        async with async_session_factory() as session:
            result = await session.execute(select(MqttBrokerSettings))
            brokers = result.scalars().all()

        if not brokers:
            logger.info("No MQTT brokers configured — adapter inactive")
            self._available = False
            return

        self._available = True
        for broker in brokers:
            await self.connect_broker(broker.id, broker)

    async def stop(self) -> None:
        """Stop all publish tasks and disconnect every broker."""
        for device_id, broker_id in list(self._publish_tasks):
            await self._cancel_publish_task(device_id, broker_id)
        self._publish_tasks.clear()
        self._publish_configs.clear()
        self._device_registers.clear()
        self._device_meta.clear()
        self._device_stats.clear()

        for broker_id in list(self._reconnect_tasks):
            await self._cancel_reconnect_task(broker_id)
        for broker_id in list(self._clients):
            await self._close_client(broker_id)
        self._clients.clear()
        self._broker_info.clear()
        self._broker_settings.clear()
        self._available = False
        logger.info("MQTT adapter stopped")

    # --- Broker lifecycle ---

    async def connect_broker(self, broker_id: UUID, settings) -> bool:
        """Connect a client for one broker; record its state either way.

        `settings` needs name/host/port/username/password/client_id attrs
        (ORM row or schema object). Returns True when connected; on failure
        a background reconnect task keeps retrying with backoff.
        """
        self._available = True
        self._broker_info[broker_id] = {
            "name": settings.name,
            "host": settings.host,
            "port": settings.port,
            "connected": False,
        }
        self._broker_settings[broker_id] = settings
        if await self._try_connect(broker_id, settings):
            return True
        self._schedule_reconnect(broker_id)
        return False

    async def disconnect_broker(self, broker_id: UUID) -> None:
        """Cancel this broker's publish tasks and drop its client."""
        await self._cancel_reconnect_task(broker_id)
        for device_id, task_broker_id in list(self._publish_tasks):
            if task_broker_id == broker_id:
                await self._cancel_publish_task(device_id, task_broker_id)
        await self._close_client(broker_id)
        self._broker_info.pop(broker_id, None)
        self._broker_settings.pop(broker_id, None)

    async def reconnect_broker(self, broker_id: UUID, settings) -> bool:
        """Apply new settings to one broker without touching the others.

        Cancels only this broker's publish tasks; the caller is responsible
        for resuming enabled configs afterwards.
        """
        await self._cancel_reconnect_task(broker_id)
        for device_id, task_broker_id in list(self._publish_tasks):
            if task_broker_id == broker_id:
                await self._cancel_publish_task(device_id, task_broker_id)
        await self._close_client(broker_id)
        return await self.connect_broker(broker_id, settings)

    async def _try_connect(self, broker_id: UUID, settings) -> bool:
        """Open a client for one broker and flip its state on success."""
        try:
            client = aiomqtt.Client(
                hostname=settings.host,
                port=settings.port,
                username=settings.username or None,
                password=settings.password or None,
                identifier=settings.client_id,
            )
            await client.__aenter__()
        except Exception:
            logger.warning(
                "MQTT broker '%s' (%s:%d) connection failed",
                settings.name, settings.host, settings.port, exc_info=True,
            )
            return False
        self._clients[broker_id] = client
        info = self._broker_info.get(broker_id)
        if info is not None:
            info["connected"] = True
        logger.info(
            "MQTT connected to broker '%s' (%s:%d)",
            settings.name, settings.host, settings.port,
        )
        return True

    def _mark_broker_disconnected(self, broker_id: UUID) -> None:
        """Record a lost connection and make sure a reconnect task is running."""
        info = self._broker_info.get(broker_id)
        if info is not None and info["connected"]:
            info["connected"] = False
            logger.warning(
                "MQTT broker '%s' (%s:%d) connection lost — reconnecting",
                info["name"], info["host"], info["port"],
            )
        self._schedule_reconnect(broker_id)

    def _schedule_reconnect(self, broker_id: UUID) -> None:
        """Start this broker's reconnect task unless one is already running."""
        task = self._reconnect_tasks.get(broker_id)
        if task is not None and not task.done():
            return
        if broker_id not in self._broker_settings:
            return
        self._reconnect_tasks[broker_id] = asyncio.create_task(
            self._reconnect_loop(broker_id)
        )

    async def _reconnect_loop(self, broker_id: UUID) -> None:
        """Retry connecting one broker with exponential backoff until it works."""
        delay = self.RECONNECT_INITIAL_DELAY
        try:
            while True:
                await asyncio.sleep(delay)
                settings = self._broker_settings.get(broker_id)
                if settings is None:  # broker was removed meanwhile
                    return
                await self._close_client(broker_id)
                if await self._try_connect(broker_id, settings):
                    return
                delay = min(delay * 2, self.RECONNECT_MAX_DELAY)
        finally:
            self._reconnect_tasks.pop(broker_id, None)

    async def _cancel_reconnect_task(self, broker_id: UUID) -> None:
        """Cancel and await one broker's reconnect task, if any."""
        task = self._reconnect_tasks.pop(broker_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def is_broker_connected(self, broker_id: UUID) -> bool:
        """Whether this broker currently has a live client."""
        return bool(self._broker_info.get(broker_id, {}).get("connected"))

    async def _close_client(self, broker_id: UUID) -> None:
        """Close and forget one broker's client, ignoring close errors."""
        client = self._clients.pop(broker_id, None)
        if client is not None:
            try:
                await client.__aexit__(None, None, None)
            except Exception:
                pass
        info = self._broker_info.get(broker_id)
        if info is not None:
            info["connected"] = False

    # --- ProtocolAdapter interface ---

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

    async def update_register(
        self, device_id: UUID, address: int, function_code: int,
        value: float, data_type: str, byte_order: str,
    ) -> None:
        """No-op. MQTT reads values from SimulationEngine at publish time."""

    def get_status(self) -> dict:
        """Return adapter status with per-broker connection states."""
        brokers = [
            {
                "id": str(broker_id),
                "name": info["name"],
                "host": info["host"],
                "port": info["port"],
                "connected": info["connected"],
            }
            for broker_id, info in self._broker_info.items()
        ]
        return {
            "available": self._available,
            "connected": any(b["connected"] for b in brokers),
            "brokers": brokers,
            "publishing_devices": len({d for d, _ in self._publish_tasks}),
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

    async def start_publishing(
        self, device_id: UUID, broker_id: UUID, config,
    ) -> None:
        """Start the publish task for one (device, broker) pair."""
        if not self.is_broker_connected(broker_id):
            raise RuntimeError("MQTT broker not connected")

        await self.stop_publishing(device_id, broker_id)

        key = (device_id, broker_id)
        self._publish_configs[key] = {
            "topic_template": config.topic_template,
            "payload_mode": config.payload_mode,
            "interval": config.publish_interval_seconds,
            "qos": config.qos,
            "retain": config.retain,
        }
        task = asyncio.create_task(self._publish_loop(device_id, broker_id))
        self._publish_tasks[key] = task
        logger.info(
            "Started MQTT publishing for device %s to broker %s",
            device_id, broker_id,
        )

    async def stop_publishing(
        self, device_id: UUID, broker_id: UUID | None = None,
    ) -> None:
        """Cancel a device's publish tasks — one broker's, or all of them."""
        for task_device_id, task_broker_id in list(self._publish_tasks):
            if task_device_id != device_id:
                continue
            if broker_id is not None and task_broker_id != broker_id:
                continue
            await self._cancel_publish_task(task_device_id, task_broker_id)
        logger.info(
            "Stopped MQTT publishing for device %s (broker=%s)",
            device_id, broker_id or "all",
        )

    async def _cancel_publish_task(self, device_id: UUID, broker_id: UUID) -> None:
        """Cancel and await one (device, broker) publish task."""
        key = (device_id, broker_id)
        task = self._publish_tasks.pop(key, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._publish_configs.pop(key, None)

    async def _publish_loop(self, device_id: UUID, broker_id: UUID) -> None:
        """Publish loop for one (device, broker) pair."""
        from app.simulation import fault_simulator, simulation_engine
        from app.simulation.fault_simulator import get_delay_seconds, get_failure_rate

        config = self._publish_configs.get((device_id, broker_id))
        if not config:
            return

        meta = self._device_meta.get(device_id, {})
        interval = config["interval"]

        while True:
            try:
                await asyncio.sleep(interval)

                fault = fault_simulator.get_fault(device_id)
                if fault is not None:
                    if fault.fault_type == "timeout" or (
                        fault.fault_type == "intermittent"
                        and random.random() < get_failure_rate(fault.params)
                    ):
                        stats = self._device_stats.get(device_id)
                        if stats:
                            stats.request_count += 1
                            stats.error_count += 1
                        continue
                    if fault.fault_type == "delay":
                        await asyncio.sleep(get_delay_seconds(fault.params))
                    # "exception" is excluded via supported_fault_types (422 at REST)

                if not self.is_broker_connected(broker_id):
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
                        device_id, broker_id, topic, payload,
                        config["qos"], config["retain"],
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
                            device_id, broker_id, topic, payload,
                            config["qos"], config["retain"],
                        )

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(
                    "MQTT publish error for device %s to broker %s: %s",
                    device_id, broker_id, e,
                )
                stats = self._device_stats.get(device_id)
                if stats:
                    stats.request_count += 1
                    stats.error_count += 1

    async def _publish_one(
        self, device_id: UUID, broker_id: UUID,
        topic: str, payload: str, qos: int, retain: bool,
    ) -> None:
        """Publish a single message and update the device's stats."""
        stats = self._device_stats.get(device_id)
        if stats:
            stats.request_count += 1
        try:
            client = self._clients[broker_id]
            await client.publish(topic, payload, qos=qos, retain=retain)
            if stats:
                stats.success_count += 1
        except aiomqtt.MqttError:
            if stats:
                stats.error_count += 1
            self._mark_broker_disconnected(broker_id)
            raise
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
