"""In-memory tracker for client write attempts against the read-only simulator.

Protocol-agnostic so issue #72 can reuse it for OPC UA / BACnet. In-memory
only — no DB persistence; cleared on device stop and server restart.
"""

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

logger = logging.getLogger(__name__)

MAX_EVENTS_PER_DEVICE = 50


@dataclass(frozen=True)
class WriteEvent:
    """A single recorded client write attempt."""

    timestamp: datetime          # UTC
    operation: str               # human label, e.g. "Write Register" / "WriteProperty"
    address: int                 # Modbus address / BACnet object instance
    values: list[str]            # stringified written values
    register_name: str | None    # resolved register/object name, or None


class WriteTracker:
    """Per-device ring buffer of client write attempts. In-memory only."""

    def __init__(self) -> None:
        self._buffers: dict[UUID, deque[WriteEvent]] = {}
        self._unread: dict[UUID, int] = {}

    def record(
        self,
        device_id: UUID,
        operation: str,
        address: int,
        values: list[str],
        register_name: str | None = None,
    ) -> None:
        """Append a write event and bump the device's unread count."""
        buf = self._buffers.get(device_id)
        if buf is None:
            buf = deque(maxlen=MAX_EVENTS_PER_DEVICE)
            self._buffers[device_id] = buf
        buf.append(
            WriteEvent(
                timestamp=datetime.now(timezone.utc),
                operation=operation,
                address=address,
                values=list(values),
                register_name=register_name,
            )
        )
        self._unread[device_id] = self._unread.get(device_id, 0) + 1

    def get_events(self, device_id: UUID) -> list[WriteEvent]:
        """Return events newest-first."""
        buf = self._buffers.get(device_id)
        if not buf:
            return []
        return list(reversed(buf))

    def get_unread_count(self, device_id: UUID) -> int:
        return self._unread.get(device_id, 0)

    def latest(self, device_id: UUID) -> WriteEvent | None:
        buf = self._buffers.get(device_id)
        if not buf:
            return None
        return buf[-1]

    def mark_read(self, device_id: UUID) -> None:
        """Reset the unread count; the event buffer is retained."""
        self._unread[device_id] = 0

    def clear(self, device_id: UUID) -> None:
        """Drop all state for one device (on device stop/remove)."""
        self._buffers.pop(device_id, None)
        self._unread.pop(device_id, None)

    def clear_all(self) -> None:
        """Drop all state (used in tests / shutdown)."""
        self._buffers.clear()
        self._unread.clear()
