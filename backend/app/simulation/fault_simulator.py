"""In-memory fault state manager for protocol-level fault simulation."""

import logging
from dataclasses import dataclass
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class FaultConfig:
    """Configuration for a communication fault on a device."""

    fault_type: str  # delay, timeout, exception, intermittent
    params: dict     # fault_type-specific parameters


class FaultSimulator:
    """Manages per-device fault state. In-memory only (no DB persistence)."""

    def __init__(self) -> None:
        self._device_faults: dict[UUID, FaultConfig] = {}

    def set_fault(self, device_id: UUID, config: FaultConfig) -> None:
        """Set or replace the active fault for a device."""
        self._device_faults[device_id] = config
        logger.info("Fault set for device %s: %s", device_id, config.fault_type)

    def clear_fault(self, device_id: UUID) -> None:
        """Clear the active fault for a device."""
        removed = self._device_faults.pop(device_id, None)
        if removed:
            logger.info("Fault cleared for device %s", device_id)

    def get_fault(self, device_id: UUID | None) -> FaultConfig | None:
        """Get the active fault for a device, or None if no fault is set."""
        if device_id is None:
            return None
        return self._device_faults.get(device_id)

    def clear_all(self) -> None:
        """Clear all faults (used during shutdown)."""
        self._device_faults.clear()
        logger.info("All faults cleared")
