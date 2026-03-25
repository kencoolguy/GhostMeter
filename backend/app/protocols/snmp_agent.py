"""SNMPv2c agent adapter using pysnmp v7."""

import bisect
import logging
from uuid import UUID

from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config, engine
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.proto.rfc1902 import Gauge32, Integer32, OctetString

from app.exceptions import ConflictException
from app.protocols.base import ProtocolAdapter, RegisterInfo

logger = logging.getLogger(__name__)


def _oid_sort_key(oid_str: str) -> tuple[int, ...]:
    """Parse OID string into a tuple of ints for sorting/comparison."""
    return tuple(int(x) for x in oid_str.split("."))


class SnmpAdapter(ProtocolAdapter):
    """SNMPv2c command responder (agent). Responds to GET/GETNEXT/WALK."""

    def __init__(self, port: int = 10161, community: str = "public") -> None:
        super().__init__()
        self._port = port
        self._community = community
        self._running = False
        # OID string → (device_id, register_name) mapping
        self._oid_map: dict[str, tuple[UUID, str]] = {}
        # OID string → data_type for O(1) lookup in resolve_oid
        self._oid_data_types: dict[str, str] = {}
        # device_id → list of OID strings (for cleanup)
        self._device_oids: dict[UUID, list[str]] = {}
        # Cached sorted OID list (invalidated on add/remove device)
        self._sorted_oids: list[str] = []
        self._sorted_oid_keys: list[tuple[int, ...]] = []
        self._snmp_engine: engine.SnmpEngine | None = None

    async def start(self) -> None:
        """Start SNMP agent on configured UDP port."""
        try:
            self._snmp_engine = engine.SnmpEngine()

            config.addTransport(
                self._snmp_engine,
                udp.domainName,
                udp.UdpTransport().openServerMode(("0.0.0.0", self._port)),
            )

            config.addV1System(
                self._snmp_engine,
                "ghostmeter-area",
                self._community,
            )

            config.addVacmUser(
                self._snmp_engine,
                2,  # securityModel: SNMPv2c
                "ghostmeter-area",
                "noAuthNoPriv",
                readSubTree=(1, 3, 6),
            )

            snmp_context = context.SnmpContext(self._snmp_engine)
            cmdrsp.GetCommandResponder(self._snmp_engine, snmp_context)
            cmdrsp.NextCommandResponder(self._snmp_engine, snmp_context)
            cmdrsp.BulkCommandResponder(self._snmp_engine, snmp_context)

            self._running = True
            logger.info(
                "SNMP agent started on UDP port %d (community: %s)",
                self._port,
                self._community,
            )
        except Exception:
            logger.warning("Failed to start SNMP agent", exc_info=True)
            self._running = False

    async def stop(self) -> None:
        """Stop SNMP agent."""
        if self._snmp_engine:
            try:
                self._snmp_engine.transportDispatcher.closeDispatcher()
            except Exception:
                logger.debug("Error closing SNMP transport dispatcher", exc_info=True)
            self._snmp_engine = None
        self._oid_map.clear()
        self._oid_data_types.clear()
        self._device_oids.clear()
        self._sorted_oids.clear()
        self._sorted_oid_keys.clear()
        self._device_stats.clear()
        self._running = False
        logger.info("SNMP agent stopped")

    async def _do_add_device(
        self,
        device_id: UUID,
        slave_id: int,
        registers: list[RegisterInfo],
    ) -> None:
        """Register device OIDs in agent. Checks for OID conflicts."""
        oids_to_add: list[RegisterInfo] = []
        for reg in registers:
            if not reg.oid:
                continue
            if reg.oid in self._oid_map:
                existing_device_id, _ = self._oid_map[reg.oid]
                if existing_device_id != device_id:
                    raise ConflictException(
                        detail=f"OID {reg.oid} is already registered by another device",
                        error_code="OID_CONFLICT",
                    )
            oids_to_add.append(reg)

        device_oid_list: list[str] = []
        for reg in oids_to_add:
            oid = reg.oid  # already checked non-None above
            self._oid_map[oid] = (device_id, oid)  # type: ignore[arg-type]
            self._oid_data_types[oid] = reg.data_type  # type: ignore[arg-type]
            device_oid_list.append(oid)  # type: ignore[arg-type]

        self._device_oids[device_id] = device_oid_list
        self._invalidate_sorted_oids()
        logger.info(
            "SNMP: registered %d OIDs for device %s",
            len(device_oid_list),
            device_id,
        )

    async def _do_remove_device(self, device_id: UUID) -> None:
        """Unregister device OIDs from agent."""
        oids = self._device_oids.pop(device_id, [])
        for oid in oids:
            self._oid_map.pop(oid, None)
            self._oid_data_types.pop(oid, None)
        self._invalidate_sorted_oids()
        logger.info(
            "SNMP: unregistered %d OIDs for device %s", len(oids), device_id
        )

    async def update_register(
        self,
        device_id: UUID,
        address: int,
        function_code: int,
        value: float,
        data_type: str,
        byte_order: str,
    ) -> None:
        """No-op. SNMP reads values from SimulationEngine at query time."""

    def get_status(self) -> dict:
        """Return adapter status."""
        return {
            "port": self._port,
            "community": self._community,
            "running": self._running,
            "registered_oids": len(self._oid_map),
            "registered_devices": len(self._device_oids),
        }

    # --- SNMP-specific methods ---

    def set_register_names(
        self,
        device_id: UUID,
        oid_to_name: dict[str, str],
    ) -> None:
        """Set the OID→register_name mapping for a device."""
        for oid, name in oid_to_name.items():
            if oid in self._oid_map:
                self._oid_map[oid] = (device_id, name)

    def resolve_oid(self, oid_str: str) -> tuple[float | None, str]:
        """Resolve an OID to a value from SimulationEngine.

        Returns (value, data_type) or (None, "") if OID not found.
        """
        entry = self._oid_map.get(oid_str)
        if entry is None:
            return None, ""

        device_id, register_name = entry

        from app.simulation import simulation_engine

        values = simulation_engine.get_current_values(device_id)
        if not values:
            return None, ""

        value = values.get(register_name)
        if value is None:
            return None, ""

        data_type = self._oid_data_types.get(oid_str, "float32")
        return value, data_type

    def get_sorted_oids(self) -> list[str]:
        """Get all registered OIDs sorted by numeric components (cached)."""
        return self._sorted_oids

    def get_next_oid(self, oid_str: str) -> str | None:
        """Find the next OID after the given one using binary search."""
        if not self._sorted_oid_keys:
            return None
        req_key = _oid_sort_key(oid_str) if oid_str else ()
        idx = bisect.bisect_right(self._sorted_oid_keys, req_key)
        if idx < len(self._sorted_oids):
            return self._sorted_oids[idx]
        return None

    def _invalidate_sorted_oids(self) -> None:
        """Rebuild the cached sorted OID list."""
        self._sorted_oids = sorted(
            self._oid_map.keys(), key=_oid_sort_key,
        )
        self._sorted_oid_keys = [_oid_sort_key(o) for o in self._sorted_oids]

    @staticmethod
    def to_snmp_value(value: float, data_type: str) -> Integer32 | Gauge32 | str:
        """Convert a register value to the appropriate SNMP type."""
        if data_type in ("int16", "int32"):
            return Integer32(int(value))
        elif data_type in ("uint16", "uint32"):
            return Gauge32(int(value))
        else:
            return str(round(value, 4))
