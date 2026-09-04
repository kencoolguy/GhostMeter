"""Cross-device aggregate data mode helpers (issue #95).

``data_mode = "aggregate"`` lets one device's register be derived from the same
(or a named) register on other devices — e.g. a main meter whose
``total_energy`` is the sum of its sub-meters. This module holds the pieces
shared by the API validation layer and the simulation engine:

- source-reference resolution (device name or UUID string → device id)
- dependency-graph cycle detection
- DB loaders for the device directory and the aggregate dependency graph
"""

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import DeviceInstance
from app.models.simulation import SimulationConfig

logger = logging.getLogger(__name__)

AGGREGATE_OPS = ("sum", "avg", "weighted_avg", "max", "min")
ON_MISSING_MODES = ("last_known", "zero", "skip")
DEFAULT_ON_MISSING = "last_known"


class AggregateCycleError(Exception):
    """Raised when aggregate sources form a dependency cycle."""


@dataclass
class DeviceDirectory:
    """In-memory snapshot of all devices for source-reference resolution."""

    by_id: dict[UUID, DeviceInstance] = field(default_factory=dict)
    by_name: dict[str, list[UUID]] = field(default_factory=dict)

    def resolve(self, ref: str) -> UUID:
        """Resolve a source reference (device name, else UUID string) to a device id.

        Names win over UUIDs so export/import files (which identify devices by
        name) stay portable across environments. Raises ``ValueError`` with a
        user-facing message when the reference is unknown or ambiguous.
        """
        ids = self.by_name.get(ref)
        if ids:
            if len(ids) > 1:
                raise ValueError(
                    f"Aggregate source '{ref}' is ambiguous: {len(ids)} devices share "
                    "that name — reference it by device id instead"
                )
            return ids[0]
        try:
            device_id = uuid.UUID(ref)
        except (ValueError, AttributeError, TypeError):
            raise ValueError(f"Aggregate source '{ref}' does not match any device") from None
        if device_id not in self.by_id:
            raise ValueError(f"Aggregate source '{ref}' does not match any device")
        return device_id

    def display_name(self, device_id: UUID) -> str:
        device = self.by_id.get(device_id)
        return device.name if device is not None else str(device_id)


async def load_device_directory(session: AsyncSession) -> DeviceDirectory:
    """Load every device into a :class:`DeviceDirectory`."""
    result = await session.execute(select(DeviceInstance))
    directory = DeviceDirectory()
    for device in result.scalars().all():
        directory.by_id[device.id] = device
        directory.by_name.setdefault(device.name, []).append(device.id)
    return directory


def resolve_sources(
    directory: DeviceDirectory, refs: list[str], *, strict: bool,
) -> list[UUID]:
    """Resolve a list of source references.

    ``strict=True`` re-raises the first ``ValueError`` (API validation).
    ``strict=False`` logs and drops unresolvable references (engine launch —
    a deleted or renamed source must not keep the aggregating device from
    starting; the ``on_missing`` policy then applies to it).
    """
    resolved: list[UUID] = []
    for ref in refs:
        try:
            resolved.append(directory.resolve(ref))
        except ValueError as e:
            if strict:
                raise
            logger.warning("Skipping unresolvable aggregate source: %s", e)
    return resolved


async def load_aggregate_dependencies(
    session: AsyncSession, directory: DeviceDirectory,
) -> dict[UUID, set[UUID]]:
    """Build ``device_id → {source device ids}`` from every enabled aggregate config."""
    stmt = select(SimulationConfig).where(
        SimulationConfig.data_mode == "aggregate",
        SimulationConfig.is_enabled.is_(True),
    )
    result = await session.execute(stmt)
    deps: dict[UUID, set[UUID]] = {}
    for cfg in result.scalars().all():
        refs = cfg.mode_params.get("sources") or []
        deps.setdefault(cfg.device_id, set()).update(
            resolve_sources(directory, list(refs), strict=False)
        )
    return deps


def find_cycle(deps: Mapping[UUID, set[UUID]], start: UUID) -> list[UUID] | None:
    """Return a dependency cycle reachable from ``start`` (as a node path), or None.

    A self-reference (``A → A``) is reported as ``[A, A]``.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[UUID, int] = {}
    path: list[UUID] = []

    def visit(node: UUID) -> list[UUID] | None:
        color[node] = GREY
        path.append(node)
        for nxt in deps.get(node, ()):
            state = color.get(nxt, WHITE)
            if state == GREY:
                return path[path.index(nxt):] + [nxt]
            if state == WHITE:
                found = visit(nxt)
                if found is not None:
                    return found
        path.pop()
        color[node] = BLACK
        return None

    return visit(start)


def format_cycle(cycle: list[UUID], directory: DeviceDirectory) -> str:
    return " → ".join(directory.display_name(d) for d in cycle)
