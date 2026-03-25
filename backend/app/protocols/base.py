"""Protocol adapter base class and shared types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID


@dataclass
class RegisterInfo:
    """Lightweight register descriptor passed to protocol adapters."""

    address: int
    function_code: int  # 3=holding, 4=input
    data_type: str      # int16, uint16, int32, uint32, float32, float64
    byte_order: str     # big_endian, little_endian, etc.
    oid: str | None = None  # SNMP OID string, null for Modbus


@dataclass
class DeviceStats:
    """Per-device communication statistics."""

    request_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_response_ms: float = 0.0

    @property
    def avg_response_ms(self) -> float:
        """Average response time in milliseconds."""
        if self.success_count == 0:
            return 0.0
        return self.total_response_ms / self.success_count


class ProtocolAdapter(ABC):
    """Base class for protocol adapters.

    Subclasses implement _do_add_device / _do_remove_device for protocol-specific
    setup. Stats lifecycle (create on add, remove on remove) is handled here.
    """

    def __init__(self) -> None:
        self._device_stats: dict[UUID, DeviceStats] = {}

    # --- Stats (concrete, inherited by all adapters) ---

    def get_stats(self, device_id: UUID) -> DeviceStats | None:
        """Get communication stats for a device."""
        return self._device_stats.get(device_id)

    def reset_stats(self, device_id: UUID) -> None:
        """Reset stats counters for a device."""
        if device_id in self._device_stats:
            self._device_stats[device_id] = DeviceStats()

    # --- Device lifecycle (template methods) ---

    async def add_device(
        self,
        device_id: UUID,
        slave_id: int,
        registers: list[RegisterInfo],
    ) -> None:
        """Register a device — creates stats entry, then delegates to subclass."""
        self._device_stats[device_id] = DeviceStats()
        await self._do_add_device(device_id, slave_id, registers)

    async def remove_device(self, device_id: UUID) -> None:
        """Unregister a device — delegates to subclass, then cleans up stats.

        Subclass cleanup runs first so it can still access stats during teardown.
        Stats are removed last.
        """
        await self._do_remove_device(device_id)
        self._device_stats.pop(device_id, None)

    # --- Abstract methods (subclasses must implement) ---

    @abstractmethod
    async def start(self) -> None:
        """Start the protocol server."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the protocol server."""

    @abstractmethod
    async def _do_add_device(
        self,
        device_id: UUID,
        slave_id: int,
        registers: list[RegisterInfo],
    ) -> None:
        """Protocol-specific device registration."""

    @abstractmethod
    async def _do_remove_device(self, device_id: UUID) -> None:
        """Protocol-specific device unregistration."""

    @abstractmethod
    async def update_register(
        self,
        device_id: UUID,
        address: int,
        function_code: int,
        value: float,
        data_type: str,
        byte_order: str,
    ) -> None:
        """Update a register value (called by simulation engine)."""

    @abstractmethod
    def get_status(self) -> dict:
        """Return adapter status info."""
