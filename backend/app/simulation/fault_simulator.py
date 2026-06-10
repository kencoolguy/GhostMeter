"""In-memory fault state manager for protocol-level fault simulation."""

import logging
import math
from dataclasses import dataclass
from typing import Any
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


MAX_DELAY_MS = 10_000  # matches the OPC UA server-side delay cap


def get_delay_seconds(params: dict[str, Any]) -> float:
    """Return a delay fault's duration, clamped to [0, MAX_DELAY_MS] ms, as seconds.

    Malformed or non-finite values fall back to the 500 ms default rather than
    crashing the serving path.
    """
    try:
        delay_ms = float(params.get("delay_ms", 500))
        if not math.isfinite(delay_ms):
            delay_ms = 500.0
    except (TypeError, ValueError):
        delay_ms = 500.0
    return min(max(delay_ms, 0.0), float(MAX_DELAY_MS)) / 1000.0


def get_failure_rate(params: dict[str, Any]) -> float:
    """Return an intermittent fault's failure rate, clamped to [0.0, 1.0].

    Malformed or non-finite values fall back to the 0.5 default.
    """
    try:
        rate = float(params.get("failure_rate", 0.5))
        if not math.isfinite(rate):
            rate = 0.5
    except (TypeError, ValueError):
        rate = 0.5
    return min(max(rate, 0.0), 1.0)
