"""Monitor service — aggregates device state and maintains event log."""

import logging
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session_factory
from app.models.device import DeviceInstance
from app.models.template import DeviceTemplate

logger = logging.getLogger(__name__)


@dataclass
class EventLogEntry:
    """A single event in the monitor log."""

    timestamp: str
    device_id: str
    device_name: str
    event_type: str
    detail: str


class MonitorService:
    """Aggregates monitor data and maintains an in-memory event log."""

    def __init__(self, max_events: int = 100) -> None:
        self._event_log: deque[EventLogEntry] = deque(maxlen=max_events)

    def log_event(
        self,
        device_id: UUID | str,
        device_name: str,
        event_type: str,
        detail: str,
    ) -> None:
        """Append an event to the log."""
        entry = EventLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            device_id=str(device_id),
            device_name=device_name,
            event_type=event_type,
            detail=detail,
        )
        self._event_log.append(entry)
        logger.debug("Event logged: %s — %s: %s", device_name, event_type, detail)

    def get_events(self) -> list[dict[str, Any]]:
        """Return all events as dicts (newest first)."""
        return [asdict(e) for e in reversed(self._event_log)]

    async def get_snapshot(self) -> dict[str, Any]:
        """Build a complete monitor snapshot for WebSocket broadcast.

        Aggregates data from:
        - DB: running device instances with template registers
        - SimulationEngine: current register values
        - AnomalyInjector: active anomalies
        - FaultSimulator: active faults
        - ProtocolManager: communication stats
        """
        from app.protocols import protocol_manager
        from app.simulation import anomaly_injector, fault_simulator, simulation_engine

        devices_data: list[dict[str, Any]] = []

        async with async_session_factory() as session:
            stmt = (
                select(DeviceInstance)
                .options(selectinload(DeviceInstance.template).selectinload(DeviceTemplate.registers))
                .where(DeviceInstance.status != "stopped")
            )
            result = await session.execute(stmt)
            devices = result.scalars().all()

        for device in devices:
            device_id = device.id

            # Register values from simulation engine
            current_values = simulation_engine.get_current_values(device_id)
            register_list = []
            if device.template and device.template.registers:
                for reg in device.template.registers:
                    register_list.append({
                        "name": reg.name,
                        "value": current_values.get(reg.name, 0.0),
                        "unit": reg.unit or "",
                    })

            # Active anomalies
            active = anomaly_injector.get_active(device_id)
            active_anomalies = [
                f"{reg}:{state.anomaly_type}" for reg, state in active.items()
            ]

            # Active fault
            fault = fault_simulator.get_fault(device_id)
            active_fault = None
            if fault:
                active_fault = {
                    "fault_type": fault.fault_type,
                    "params": fault.params,
                }

            # Communication stats
            stats_data = {
                "request_count": 0,
                "success_count": 0,
                "error_count": 0,
                "avg_response_ms": 0.0,
            }
            stats = protocol_manager.get_stats("modbus_tcp", device_id)
            if stats:
                stats_data = {
                    "request_count": stats.request_count,
                    "success_count": stats.success_count,
                    "error_count": stats.error_count,
                    "avg_response_ms": round(stats.avg_response_ms, 1),
                }

            devices_data.append({
                "device_id": str(device_id),
                "name": device.name,
                "slave_id": device.slave_id,
                "port": device.port,
                "status": device.status,
                "registers": register_list,
                "active_anomalies": active_anomalies,
                "active_fault": active_fault,
                "stats": stats_data,
            })

        return {
            "type": "monitor_update",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "devices": devices_data,
            "events": self.get_events(),
        }


monitor_service = MonitorService()
