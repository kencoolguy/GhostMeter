"""Simulation engine — manages per-device simulation tasks."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session_factory
from app.models.device import DeviceInstance
from app.models.simulation import SimulationConfig
from app.models.template import DeviceTemplate
from app.protocols import protocol_manager
from app.simulation.data_generator import DataGenerator, GeneratorContext

logger = logging.getLogger(__name__)


@dataclass
class RegisterMeta:
    """Register metadata needed by the simulation loop."""

    address: int
    function_code: int
    data_type: str
    byte_order: str
    scale_factor: float
    sort_order: int


class SimulationEngine:
    """Manages per-device simulation tasks."""

    def __init__(self) -> None:
        self._device_tasks: dict[UUID, asyncio.Task] = {}
        self._device_values: dict[UUID, dict[str, float]] = {}
        self._data_generator = DataGenerator()

    async def start_device(self, device_id: UUID) -> None:
        """Start simulation for a device."""
        if device_id in self._device_tasks:
            logger.warning("Simulation already running for device %s", device_id)
            return

        configs, register_map, device_protocol = await self._load_device_data(device_id)

        if not configs:
            logger.info("No simulation configs for device %s, skipping", device_id)
            return

        interval = min(c.update_interval_ms for c in configs) / 1000.0
        task = asyncio.create_task(
            self._run_device(device_id, configs, register_map, device_protocol, interval),
            name=f"sim-{device_id}",
        )
        self._device_tasks[device_id] = task
        logger.info("Simulation started for device %s (interval=%.1fs)", device_id, interval)

    async def stop_device(self, device_id: UUID) -> None:
        """Stop simulation for a device."""
        task = self._device_tasks.pop(device_id, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._device_values.pop(device_id, None)
            logger.info("Simulation stopped for device %s", device_id)

    async def reload_device(self, device_id: UUID) -> None:
        """Reload simulation configs for a running device."""
        await self.stop_device(device_id)
        await self.start_device(device_id)

    def is_device_simulating(self, device_id: UUID) -> bool:
        """Check if a device has an active simulation task."""
        return device_id in self._device_tasks

    def get_current_values(self, device_id: UUID) -> dict[str, float]:
        """Get last generated values for a device (for monitoring)."""
        return dict(self._device_values.get(device_id, {}))

    async def shutdown(self) -> None:
        """Cancel all simulation tasks concurrently."""
        tasks = list(self._device_tasks.values())
        self._device_tasks.clear()
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._device_values.clear()
        logger.info("Simulation engine shut down")

    async def _load_device_data(
        self, device_id: UUID,
    ) -> tuple[list[SimulationConfig], dict[str, RegisterMeta], str]:
        """Load simulation configs and register metadata from DB."""
        async with async_session_factory() as session:
            # Load enabled simulation configs
            stmt = select(SimulationConfig).where(
                SimulationConfig.device_id == device_id,
                SimulationConfig.is_enabled.is_(True),
            )
            result = await session.execute(stmt)
            configs = list(result.scalars().all())

            # Load device
            stmt = select(DeviceInstance).where(DeviceInstance.id == device_id)
            result = await session.execute(stmt)
            device = result.scalar_one_or_none()
            if device is None:
                return ([], {}, "modbus_tcp")

            # Load template with registers
            stmt = (
                select(DeviceTemplate)
                .options(selectinload(DeviceTemplate.registers))
                .where(DeviceTemplate.id == device.template_id)
            )
            result = await session.execute(stmt)
            template = result.scalar_one()

            register_map: dict[str, RegisterMeta] = {}
            for reg in template.registers:
                register_map[reg.name] = RegisterMeta(
                    address=reg.address,
                    function_code=reg.function_code,
                    data_type=reg.data_type,
                    byte_order=reg.byte_order,
                    scale_factor=reg.scale_factor,
                    sort_order=reg.sort_order,
                )

            return (configs, register_map, template.protocol)

    async def _run_device(
        self,
        device_id: UUID,
        configs: list[SimulationConfig],
        register_map: dict[str, RegisterMeta],
        protocol: str,
        interval: float,
    ) -> None:
        """Per-device simulation loop."""
        start_time = datetime.now(timezone.utc)
        tick_count = 0
        error_count = 0

        from app.simulation import anomaly_injector

        adapter = protocol_manager.get_adapter(protocol)
        self._device_values[device_id] = {}

        # Sort and filter configs — warn once for missing registers
        default_meta = RegisterMeta(0, 3, "float32", "big_endian", 1.0, 9999)
        valid_configs = []
        for c in sorted(configs, key=lambda c: register_map.get(c.register_name, default_meta).sort_order):
            if c.register_name in register_map:
                valid_configs.append(c)
            else:
                logger.warning(
                    "Register '%s' not found in template for device %s — skipping",
                    c.register_name, device_id,
                )

        while True:
            try:
                now = datetime.now(timezone.utc)
                elapsed = (now - start_time).total_seconds()
                now_hour = now.hour + now.minute / 60.0
                context = GeneratorContext(
                    current_values=self._device_values[device_id],
                    elapsed_seconds=elapsed,
                    tick_count=tick_count,
                    current_hour_utc=now_hour,
                )

                for config in valid_configs:
                    reg = register_map[config.register_name]

                    try:
                        generated = self._data_generator.generate(
                            config.data_mode, config.mode_params, context,
                        )
                        generated = anomaly_injector.apply(
                            device_id, config.register_name, generated,
                            context.elapsed_seconds,
                        )
                        if reg.scale_factor != 0:
                            raw_value = generated / reg.scale_factor
                        else:
                            raw_value = generated
                        self._device_values[device_id][config.register_name] = generated

                        await adapter.update_register(
                            device_id, reg.address, reg.function_code,
                            raw_value, reg.data_type, reg.byte_order,
                        )
                    except Exception as e:
                        logger.error(
                            "Error generating value for %s on device %s: %s",
                            config.register_name, device_id, e,
                        )

                tick_count += 1
                error_count = 0

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Simulation tick failed for device %s: %s", device_id, e)
                error_count += 1
                if error_count >= 5:
                    logger.error(
                        "Device %s simulation stopped after %d consecutive errors",
                        device_id, error_count,
                    )
                    await self._set_device_error(device_id)
                    return

            await asyncio.sleep(interval)

    async def _set_device_error(self, device_id: UUID) -> None:
        """Set device status to 'error' in the database."""
        try:
            async with async_session_factory() as session:
                stmt = select(DeviceInstance).where(DeviceInstance.id == device_id)
                result = await session.execute(stmt)
                device = result.scalar_one_or_none()
                if device:
                    device.status = "error"
                    await session.commit()
        except Exception as e:
            logger.error("Failed to set device %s to error state: %s", device_id, e)
