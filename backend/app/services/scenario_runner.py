"""In-memory scenario executor — drives timeline via AnomalyInjector."""

import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

from app.simulation.anomaly_injector import AnomalyInjector

logger = logging.getLogger(__name__)


@dataclass
class StepInfo:
    """Immutable step info for the runner."""

    register_name: str
    anomaly_type: str
    anomaly_params: dict
    trigger_at_seconds: int
    duration_seconds: int


@dataclass
class RunningScenario:
    """State of a currently running scenario on a device."""

    scenario_id: UUID
    scenario_name: str
    total_duration_seconds: int
    steps: list[StepInfo]
    started_at: float = 0.0
    status: str = "running"
    active_anomalies: set[str] = field(default_factory=set)
    task: asyncio.Task | None = None


class ScenarioRunner:
    """Manages scenario execution across devices."""

    def __init__(self, anomaly_injector: AnomalyInjector) -> None:
        self._running: dict[UUID, RunningScenario] = {}
        self._injector = anomaly_injector

    async def start(
        self,
        device_id: UUID,
        scenario_id: UUID,
        scenario_name: str,
        total_duration_seconds: int,
        steps: list[StepInfo],
    ) -> None:
        """Start executing a scenario on a device."""
        if device_id in self._running:
            raise RuntimeError(f"Device {device_id} already has a running scenario")

        loop = asyncio.get_running_loop()
        running = RunningScenario(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            total_duration_seconds=total_duration_seconds,
            steps=steps,
            started_at=loop.time(),
        )
        self._running[device_id] = running
        running.task = asyncio.create_task(self._drive_timeline(device_id, running))
        logger.info(
            "Scenario '%s' started on device %s (%d steps, %ds total)",
            scenario_name, device_id, len(steps), total_duration_seconds,
        )

    async def stop(self, device_id: UUID) -> None:
        """Stop a running scenario and clear all injected anomalies."""
        running = self._running.pop(device_id, None)
        if running is None:
            return
        if running.task and not running.task.done():
            running.task.cancel()
            try:
                await running.task
            except asyncio.CancelledError:
                pass
        # Clear all anomalies injected by this scenario
        for register_name in list(running.active_anomalies):
            self._injector.remove(device_id, register_name)
        running.active_anomalies.clear()
        running.status = "completed"
        logger.info("Scenario '%s' stopped on device %s", running.scenario_name, device_id)

    def get_status(self, device_id: UUID) -> dict | None:
        """Get execution status for a device. Returns None if no scenario running."""
        running = self._running.get(device_id)
        if running is None:
            return None

        loop = asyncio.get_running_loop()
        elapsed = int(loop.time() - running.started_at)

        active_steps = []
        for step in running.steps:
            end_at = step.trigger_at_seconds + step.duration_seconds
            if step.trigger_at_seconds <= elapsed < end_at:
                active_steps.append({
                    "register_name": step.register_name,
                    "anomaly_type": step.anomaly_type,
                    "remaining_seconds": max(0, end_at - elapsed),
                })

        return {
            "scenario_id": running.scenario_id,
            "scenario_name": running.scenario_name,
            "status": running.status,
            "elapsed_seconds": min(elapsed, running.total_duration_seconds),
            "total_duration_seconds": running.total_duration_seconds,
            "active_steps": active_steps,
        }

    async def _drive_timeline(self, device_id: UUID, running: RunningScenario) -> None:
        """Asyncio task that drives scenario execution."""
        loop = asyncio.get_running_loop()
        triggered: set[int] = set()  # indices of steps already triggered

        try:
            while True:
                elapsed = loop.time() - running.started_at

                # Activate steps that should start
                for i, step in enumerate(running.steps):
                    if i not in triggered and elapsed >= step.trigger_at_seconds:
                        self._injector.inject(
                            device_id, step.register_name,
                            step.anomaly_type, step.anomaly_params,
                        )
                        running.active_anomalies.add(step.register_name)
                        triggered.add(i)

                # Deactivate steps that should end
                for i, step in enumerate(running.steps):
                    end_at = step.trigger_at_seconds + step.duration_seconds
                    if i in triggered and elapsed >= end_at and step.register_name in running.active_anomalies:
                        self._injector.remove(device_id, step.register_name)
                        running.active_anomalies.discard(step.register_name)

                # Check if scenario is complete
                if elapsed >= running.total_duration_seconds and not running.active_anomalies:
                    running.status = "completed"
                    self._running.pop(device_id, None)
                    logger.info("Scenario '%s' completed on device %s", running.scenario_name, device_id)
                    break

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            pass  # Cleanup handled by stop()


# Module-level singleton — importable from services layer
from app.simulation import anomaly_injector as _anomaly_injector

scenario_runner = ScenarioRunner(_anomaly_injector)
