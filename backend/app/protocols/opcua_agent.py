"""OPC UA server adapter using asyncua (FreeOpcUa).

Exposes simulated devices as Object nodes under a GhostMeter folder, each
register as a read-only Variable node. Values are pushed in from the
simulation engine via update_register(); asyncua delivers subscription
notifications to clients automatically when a node value changes.

Security: SecurityPolicy None + Anonymous (MVP).
"""

import logging
from uuid import UUID

from asyncua import Server, ua

from app.protocols.base import ProtocolAdapter, RegisterInfo

logger = logging.getLogger(__name__)


# template data_type → (OPC UA VariantType, python caster)
_TYPE_MAP: dict[str, tuple[ua.VariantType, type]] = {
    "int16": (ua.VariantType.Int16, int),
    "uint16": (ua.VariantType.UInt16, int),
    "int32": (ua.VariantType.Int32, int),
    "uint32": (ua.VariantType.UInt32, int),
    "float32": (ua.VariantType.Float, float),
    "float64": (ua.VariantType.Double, float),
}


class OpcUaAdapter(ProtocolAdapter):
    """Single shared OPC UA server exposing all devices in one address space."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 4840,
        endpoint_path: str = "/ghostmeter/server/",
        server_name: str = "GhostMeter OPC UA Server",
        namespace_uri: str = "http://ghostmeter.local/opcua/",
    ) -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._endpoint = f"opc.tcp://{host}:{port}{endpoint_path}"
        self._server_name = server_name
        self._namespace_uri = namespace_uri
        self._server: Server | None = None
        self._ns_idx: int = 0
        self._folder = None  # GhostMeter parent folder node
        self._running = False
        self._device_objects: dict[UUID, object] = {}          # device_id → Object node
        self._nodes: dict[tuple[UUID, int, int], object] = {}  # (device_id, addr, fc) → Variable node
        self._device_meta: dict[UUID, str] = {}                # device_id → display name

    async def start(self) -> None:
        """Start the OPC UA server and create the GhostMeter folder."""
        try:
            self._server = Server()
            await self._server.init()
            self._server.set_endpoint(self._endpoint)
            self._server.set_server_name(self._server_name)
            self._server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
            self._ns_idx = await self._server.register_namespace(self._namespace_uri)
            self._folder = await self._server.nodes.objects.add_folder(
                self._ns_idx, "GhostMeter"
            )
            await self._server.start()
            self._running = True
            logger.info("OPC UA server started on %s", self._endpoint)
        except Exception:
            logger.warning("Failed to start OPC UA server", exc_info=True)
            self._running = False

    async def stop(self) -> None:
        """Stop the OPC UA server and clear all node state."""
        if self._server is not None:
            try:
                await self._server.stop()
            except Exception:
                logger.debug("Error stopping OPC UA server", exc_info=True)
        self._server = None
        self._folder = None
        self._device_objects.clear()
        self._nodes.clear()
        self._device_meta.clear()
        self._device_stats.clear()
        self._running = False
        logger.info("OPC UA server stopped")

    async def _do_add_device(
        self,
        device_id: UUID,
        slave_id: int,
        registers: list[RegisterInfo],
    ) -> None:
        """Placeholder — implemented in Task 5."""

    async def _do_remove_device(self, device_id: UUID) -> None:
        """Placeholder — implemented in Task 8."""

    async def update_register(
        self,
        device_id: UUID,
        address: int,
        function_code: int,
        value: float,
        data_type: str,
        byte_order: str,
    ) -> None:
        """Placeholder — implemented in Task 6."""

    def set_device_meta(self, device_id: UUID, device_name: str) -> None:
        """Set the display name used for a device's Object node.

        MUST be called before add_device so the node is created with the name.
        """
        self._device_meta[device_id] = device_name

    def get_status(self) -> dict:
        """Return adapter status."""
        return {
            "endpoint": self._endpoint,
            "port": self._port,
            "running": self._running,
            "device_count": len(self._device_objects),
            "node_count": len(self._nodes),
        }
