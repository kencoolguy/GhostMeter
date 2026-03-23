"""Protocol manager — lifecycle manager for all protocol adapters."""

import logging
from uuid import UUID

from app.protocols.base import ProtocolAdapter, RegisterInfo

logger = logging.getLogger(__name__)


class ProtocolManager:
    """Manages lifecycle of all protocol adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, ProtocolAdapter] = {}
        self._running: bool = False

    @property
    def is_running(self) -> bool:
        """True after start_all(), false after stop_all()."""
        return self._running

    def register_adapter(self, protocol: str, adapter: ProtocolAdapter) -> None:
        """Register an adapter for a protocol name."""
        self._adapters[protocol] = adapter
        logger.info("Registered protocol adapter: %s", protocol)

    async def start_all(self) -> None:
        """Start all registered adapters."""
        for name, adapter in self._adapters.items():
            try:
                await adapter.start()
                logger.info("Protocol adapter started: %s", name)
            except Exception:
                logger.exception("Failed to start protocol adapter: %s", name)
                return
        self._running = True

    async def stop_all(self) -> None:
        """Stop all registered adapters."""
        self._running = False
        for name, adapter in self._adapters.items():
            try:
                await adapter.stop()
                logger.info("Protocol adapter stopped: %s", name)
            except Exception:
                logger.exception("Error stopping protocol adapter: %s", name)

    async def add_device(
        self,
        protocol: str,
        device_id: UUID,
        slave_id: int,
        registers: list[RegisterInfo],
    ) -> None:
        """Delegate add_device to the correct adapter."""
        adapter = self._adapters[protocol]
        await adapter.add_device(device_id, slave_id, registers)

    async def remove_device(self, protocol: str, device_id: UUID) -> None:
        """Delegate remove_device to the correct adapter."""
        adapter = self._adapters[protocol]
        await adapter.remove_device(device_id)

    def get_adapter(self, protocol: str) -> ProtocolAdapter:
        """Get adapter by protocol name."""
        return self._adapters[protocol]
