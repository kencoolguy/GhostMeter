"""SNMPv2c agent adapter using pysnmp v7."""

import asyncio
import logging
from uuid import UUID

from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config, engine
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.proto.rfc1902 import Gauge32, Integer32, ObjectName, OctetString
from pysnmp.smi import instrum

from app.protocols.base import DeviceStats, ProtocolAdapter, RegisterInfo

logger = logging.getLogger(__name__)


class _GhostMeterMibInstrum(instrum.MibInstrumController):
    """Custom MIB instrumentation that resolves OIDs from SimulationEngine."""

    def __init__(self, adapter: "SnmpAdapter") -> None:
        super().__init__(engine.SnmpEngine().getMibBuilder())
        self._adapter = adapter

    def readVars(self, varBinds, acInfo=None):
        """Handle SNMP GET requests."""
        result = []
        for oid, val in varBinds:
            oid_str = str(oid)
            # Strip leading dot if present
            if oid_str.startswith("."):
                oid_str = oid_str[1:]
            value, data_type = self._adapter.resolve_oid(oid_str)
            if value is not None:
                snmp_val = self._adapter.to_snmp_value(value, data_type)
                result.append((oid, snmp_val))
            else:
                # Return noSuchObject
                from pysnmp.proto import rfc1905
                result.append((oid, rfc1905.noSuchObject))
        return result

    def readNextVars(self, varBinds, acInfo=None):
        """Handle SNMP GETNEXT requests (used by WALK)."""
        result = []
        sorted_oids = self._adapter.get_sorted_oids()

        for oid, val in varBinds:
            oid_str = str(oid)
            if oid_str.startswith("."):
                oid_str = oid_str[1:]

            # Find next OID after the requested one
            next_oid = None
            for candidate in sorted_oids:
                oid_tuple = tuple(int(x) for x in candidate.split("."))
                req_tuple = tuple(int(x) for x in oid_str.split(".")) if oid_str else ()
                if oid_tuple > req_tuple:
                    next_oid = candidate
                    break

            if next_oid:
                value, data_type = self._adapter.resolve_oid(next_oid)
                if value is not None:
                    snmp_val = self._adapter.to_snmp_value(value, data_type)
                    next_oid_obj = ObjectName(next_oid)
                    result.append((next_oid_obj, snmp_val))
                    continue

            # End of MIB
            from pysnmp.proto import rfc1905
            result.append((oid, rfc1905.endOfMibView))

        return result


class SnmpAdapter(ProtocolAdapter):
    """SNMPv2c command responder (agent). Responds to GET/GETNEXT/WALK."""

    def __init__(self, port: int = 10161, community: str = "public") -> None:
        super().__init__()
        self._port = port
        self._community = community
        self._running = False
        # OID string → (device_id, register_name) mapping
        self._oid_map: dict[str, tuple[UUID, str]] = {}
        # device_id → list of OID strings (for cleanup)
        self._device_oids: dict[UUID, list[str]] = {}
        # device_id → list of RegisterInfo (for data type lookup)
        self._device_registers: dict[UUID, list[RegisterInfo]] = {}
        self._snmp_engine: engine.SnmpEngine | None = None

    async def start(self) -> None:
        """Start SNMP agent on configured UDP port."""
        try:
            self._snmp_engine = engine.SnmpEngine()

            # Configure transport (UDP/IPv4)
            config.addTransport(
                self._snmp_engine,
                udp.domainName,
                udp.UdpTransport().openServerMode(("0.0.0.0", self._port)),
            )

            # Configure SNMPv2c community
            config.addV1System(
                self._snmp_engine,
                "ghostmeter-area",
                self._community,
            )

            # Allow full read access
            config.addVacmUser(
                self._snmp_engine,
                2,  # securityModel: SNMPv2c
                "ghostmeter-area",
                "noAuthNoPriv",
                readSubTree=(1, 3, 6),
            )

            # Set up SNMP context with our custom instrumentation
            snmp_context = context.SnmpContext(self._snmp_engine)

            # Register command responders
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
                pass
            self._snmp_engine = None
        self._oid_map.clear()
        self._device_oids.clear()
        self._device_registers.clear()
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
            # Check conflict
            if reg.oid in self._oid_map:
                existing_device_id, _ = self._oid_map[reg.oid]
                if existing_device_id != device_id:
                    from app.exceptions import ConflictException

                    raise ConflictException(
                        detail=f"OID {reg.oid} is already registered by another device",
                        error_code="OID_CONFLICT",
                    )
            oids_to_add.append(reg)

        # Register all OIDs — use OID as initial name key (set_register_names fixes this)
        device_oid_list: list[str] = []
        for reg in oids_to_add:
            self._oid_map[reg.oid] = (device_id, reg.oid)  # type: ignore[arg-type]
            device_oid_list.append(reg.oid)  # type: ignore[arg-type]

        self._device_oids[device_id] = device_oid_list
        self._device_registers[device_id] = registers
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
        self._device_registers.pop(device_id, None)
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
        """No-op. SNMP reads from SimulationEngine at query time."""

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

        # Find data type from register info
        data_type = "float32"
        for reg in self._device_registers.get(device_id, []):
            if reg.oid == oid_str:
                data_type = reg.data_type
                break

        return value, data_type

    def get_sorted_oids(self) -> list[str]:
        """Get all registered OIDs sorted by numeric components."""
        return sorted(
            self._oid_map.keys(),
            key=lambda o: tuple(int(x) for x in o.split(".")),
        )

    @staticmethod
    def to_snmp_value(value: float, data_type: str) -> Integer32 | Gauge32 | OctetString:
        """Convert a register value to the appropriate SNMP type."""
        if data_type in ("int16", "int32"):
            return Integer32(int(value))
        elif data_type in ("uint16", "uint32"):
            return Gauge32(int(value))
        else:
            # float32, float64 → string representation
            return OctetString(str(round(value, 4)))
