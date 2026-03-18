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


class ProtocolAdapter(ABC):
    """Base class for protocol adapters."""

    @abstractmethod
    async def start(self) -> None:
        """Start the protocol server."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the protocol server."""

    @abstractmethod
    async def add_device(
        self,
        device_id: UUID,
        slave_id: int,
        registers: list[RegisterInfo],
    ) -> None:
        """Register a device's slave ID and its register map on the server."""

    @abstractmethod
    async def remove_device(self, device_id: UUID) -> None:
        """Unregister a device from the server."""

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
        """Update a register value (called by simulation engine in Phase 5)."""

    @abstractmethod
    def get_status(self) -> dict:
        """Return adapter status info."""
