"""Anomaly injection engine — applies anomalies to generated register values."""

import logging
import random
from dataclasses import dataclass
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class AnomalyState:
    """State of an active anomaly on a register."""

    anomaly_type: str
    params: dict
    activated_at: float | None = None  # None = not yet seen by apply()
    frozen_value: float | None = None


@dataclass
class ScheduleEntry:
    """A loaded schedule entry (in-memory representation)."""

    register_name: str
    anomaly_type: str
    anomaly_params: dict
    trigger_after_seconds: int
    duration_seconds: int


class AnomalyInjector:
    """Manages per-device anomaly state and applies anomalies to values."""

    def __init__(self) -> None:
        self._active: dict[UUID, dict[str, AnomalyState]] = {}
        self._schedules: dict[UUID, list[ScheduleEntry]] = {}
        self._scheduled_active: dict[UUID, dict[str, AnomalyState]] = {}

    def inject(
        self, device_id: UUID, register_name: str,
        anomaly_type: str, params: dict,
    ) -> None:
        """Inject a real-time anomaly on a register (immediate, in-memory)."""
        if device_id not in self._active:
            self._active[device_id] = {}
        self._active[device_id][register_name] = AnomalyState(
            anomaly_type=anomaly_type, params=params,
        )
        logger.info(
            "Anomaly injected: device=%s register=%s type=%s",
            device_id, register_name, anomaly_type,
        )

    def remove(self, device_id: UUID, register_name: str) -> None:
        """Remove a real-time anomaly from a specific register."""
        if device_id in self._active:
            self._active[device_id].pop(register_name, None)

    def clear_realtime(self, device_id: UUID) -> None:
        """Clear only real-time anomalies (not schedules)."""
        self._active.pop(device_id, None)

    def clear_device(self, device_id: UUID) -> None:
        """Clear all state for a device (real-time + schedules). Used on device stop."""
        self._active.pop(device_id, None)
        self._schedules.pop(device_id, None)
        self._scheduled_active.pop(device_id, None)

    def get_active(self, device_id: UUID) -> dict[str, AnomalyState]:
        """Get all active real-time anomalies for a device."""
        return dict(self._active.get(device_id, {}))

    def load_schedules(self, device_id: UUID, schedules: list[dict]) -> None:
        """Load schedule entries for a device (called on device start)."""
        self._schedules[device_id] = [
            ScheduleEntry(
                register_name=s["register_name"],
                anomaly_type=s["anomaly_type"],
                anomaly_params=s["anomaly_params"],
                trigger_after_seconds=s["trigger_after_seconds"],
                duration_seconds=s["duration_seconds"],
            )
            for s in schedules
        ]
        self._scheduled_active.pop(device_id, None)

    def apply(
        self, device_id: UUID, register_name: str,
        value: float, elapsed_seconds: float,
    ) -> float:
        """Apply anomaly to a value. Returns modified or original value."""
        rt_anomalies = self._active.get(device_id, {})
        if register_name in rt_anomalies:
            return self._apply_anomaly(
                rt_anomalies[register_name], value, elapsed_seconds,
            )

        self._update_scheduled_anomalies(device_id, register_name, elapsed_seconds)
        sched_anomalies = self._scheduled_active.get(device_id, {})
        if register_name in sched_anomalies:
            return self._apply_anomaly(
                sched_anomalies[register_name], value, elapsed_seconds,
            )

        return value

    def _update_scheduled_anomalies(
        self, device_id: UUID, register_name: str,
        elapsed_seconds: float,
    ) -> None:
        """Activate/deactivate scheduled anomalies based on elapsed time."""
        schedules = self._schedules.get(device_id, [])
        if not schedules:
            return

        if device_id not in self._scheduled_active:
            self._scheduled_active[device_id] = {}

        active_schedule = None
        for sched in schedules:
            if sched.register_name != register_name:
                continue
            start = sched.trigger_after_seconds
            end = start + sched.duration_seconds
            if start <= elapsed_seconds < end:
                active_schedule = sched
                break

        if active_schedule is not None:
            if register_name not in self._scheduled_active[device_id]:
                self._scheduled_active[device_id][register_name] = AnomalyState(
                    anomaly_type=active_schedule.anomaly_type,
                    params=active_schedule.anomaly_params,
                    activated_at=elapsed_seconds,
                )
        else:
            self._scheduled_active.get(device_id, {}).pop(register_name, None)

    def _apply_anomaly(
        self, state: AnomalyState, value: float,
        elapsed_seconds: float,
    ) -> float:
        """Apply a specific anomaly to a value."""
        match state.anomaly_type:
            case "spike":
                prob = float(state.params.get("probability", 0.1))
                mult = float(state.params.get("multiplier", 2.0))
                if random.random() < prob:
                    return value * mult
                return value
            case "drift":
                drift_rate = float(state.params["drift_per_second"])
                max_drift = float(state.params["max_drift"])
                if state.activated_at is None:
                    state.activated_at = elapsed_seconds
                time_since = elapsed_seconds - state.activated_at
                drift = drift_rate * time_since
                if abs(drift) > abs(max_drift):
                    drift = max_drift if drift_rate >= 0 else -max_drift
                return value + drift
            case "flatline":
                if "value" in state.params:
                    return float(state.params["value"])
                if state.frozen_value is None:
                    state.frozen_value = value
                return state.frozen_value
            case "out_of_range":
                return float(state.params["value"])
            case "data_loss":
                return 0.0
            case _:
                return value

    def clear_all(self) -> None:
        """Clear all state (used during shutdown)."""
        self._active.clear()
        self._schedules.clear()
        self._scheduled_active.clear()
