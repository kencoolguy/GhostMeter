"""BACnet/IP adapter using bacpypes3.

Topology (mirrors bacpypes3 samples/ip-to-vlan.py): one IPv4 router
application bound to a single UDP port, plus a VirtualNetwork (VLAN).
Each GhostMeter device is an independent BACnet device application
attached to the VLAN, so EMS clients see one BACnet router with N
discoverable devices behind network BACNET_NETWORK.

Numbering (deterministic, no DB changes):
- router device instance  = BACNET_DEVICE_INSTANCE_BASE
- device instance         = BACNET_DEVICE_INSTANCE_BASE + slave_id
- device VLAN MAC         = slave_id (1-247; router reserves 254)
- object instance         = register address (analog-input, read-only)

Values are pushed in via update_register() (same model as OPC UA).
"""

import logging
import time
from uuid import UUID

from bacpypes3.app import Application
from bacpypes3.local.analog import AnalogInputObject
from bacpypes3.local.device import DeviceObject
from bacpypes3.local.networkport import NetworkPortObject
from bacpypes3.vlan import VirtualNetwork

from app.exceptions import ConflictException
from app.protocols.base import ProtocolAdapter, RegisterInfo

logger = logging.getLogger(__name__)

# register unit string → BACnet EngineeringUnits enum name
_UNIT_MAP: dict[str, str] = {
    "V": "volts",
    "A": "amperes",
    "W": "watts",
    "kW": "kilowatts",
    "kWh": "kilowatt-hours",
    "Wh": "watt-hours",
    "Hz": "hertz",
    "%": "percent",
    "°C": "degrees-celsius",
    "VA": "volt-amperes",
    "var": "volt-amperes-reactive",
}

_ROUTER_VLAN_MAC = 254  # router node address on the VLAN; slave_ids are 1-247
_VENDOR_ID = 999  # bacpypes3 sample/local-object vendor id


class _DeviceApplication(Application):
    """Per-device BACnet application that counts read requests for stats.

    Instances are created via Application.from_object_list(); the adapter
    sets _ghost_adapter/_ghost_device_id right after construction.
    """

    _ghost_adapter: "BacnetAdapter | None" = None
    _ghost_device_id: UUID | None = None

    async def do_ReadPropertyRequest(self, apdu) -> None:
        t0 = time.monotonic()
        try:
            await super().do_ReadPropertyRequest(apdu)
        except Exception:
            self._count(t0, success=False)
            raise
        self._count(t0, success=True)

    async def do_ReadPropertyMultipleRequest(self, apdu) -> None:
        t0 = time.monotonic()
        try:
            await super().do_ReadPropertyMultipleRequest(apdu)
        except Exception:
            self._count(t0, success=False)
            raise
        self._count(t0, success=True)

    def _count(self, t0: float, success: bool) -> None:
        if self._ghost_adapter is None or self._ghost_device_id is None:
            return
        self._ghost_adapter._count_request(
            self._ghost_device_id, (time.monotonic() - t0) * 1000.0, success,
        )


class BacnetAdapter(ProtocolAdapter):
    """BACnet/IP router + VLAN of per-device virtual BACnet devices."""

    def __init__(
        self,
        address: str = "0.0.0.0/0",
        port: int = 47808,
        device_instance_base: int = 100000,
        network: int = 100,
    ) -> None:
        super().__init__()
        self._address = address
        self._port = port
        self._base = device_instance_base
        self._network = network
        self._vlan_name = f"ghostmeter-vlan-{port}"
        self._vlan: VirtualNetwork | None = None
        self._router_app: Application | None = None
        self._device_apps: dict[UUID, Application] = {}
        self._objects: dict[tuple[UUID, int], AnalogInputObject] = {}
        self._instance_owner: dict[int, UUID] = {}  # device instance → device_id
        self._device_meta: dict[UUID, str] = {}     # device_id → display name
        self._running = False

    async def start(self) -> None:
        """Create the VLAN and start the IPv4 router application."""
        try:
            self._vlan = VirtualNetwork(self._vlan_name)

            router_device = DeviceObject(
                objectIdentifier=("device", self._base),
                objectName="GhostMeter BACnet Router",
                vendorIdentifier=_VENDOR_ID,
            )
            # The IPv4 port needs its own configured network number, otherwise
            # the router cannot build the NPDU source address (SADR) when
            # forwarding requests onto the VLAN ("integer network required").
            # Same layout as bacpypes3 samples/ip-to-vlan.json (ip=100, vlan=200).
            ipv4_port = NetworkPortObject(
                f"{self._address}:{self._port}",
                objectIdentifier=("network-port", 1),
                objectName="NetworkPort-IPv4",
                networkNumber=self._network + 1,
                networkNumberQuality="configured",
            )
            vlan_port = NetworkPortObject(
                None,
                objectIdentifier=("network-port", 2),
                objectName="NetworkPort-VLAN",
                networkType="virtual",
                networkInterfaceName=self._vlan_name,
                macAddress=bytes([_ROUTER_VLAN_MAC]),
                networkNumber=self._network,
                networkNumberQuality="configured",
                protocolLevel="bacnet-application",
                changesPending=False,
                outOfService=False,
                reliability="no-fault-detected",
            )
            self._router_app = Application.from_object_list(
                [router_device, ipv4_port, vlan_port]
            )
            self._running = True
            logger.info(
                "BACnet router started on %s:%d (VLAN network %d, router instance %d)",
                self._address, self._port, self._network, self._base,
            )
        except Exception:
            logger.warning("Failed to start BACnet adapter", exc_info=True)
            self._teardown()

    async def stop(self) -> None:
        """Close all device apps and the router; release the VLAN name."""
        self._teardown()
        logger.info("BACnet adapter stopped")

    def _teardown(self) -> None:
        for app in self._device_apps.values():
            try:
                app.close()
            except Exception:
                logger.debug("Error closing BACnet device app", exc_info=True)
        self._device_apps.clear()
        if self._router_app is not None:
            try:
                self._router_app.close()
            except Exception:
                logger.debug("Error closing BACnet router app", exc_info=True)
            self._router_app = None
        # VirtualNetwork keeps a global name registry; release our entry so
        # restart (and the test suite) can re-create the network.
        VirtualNetwork._networks.pop(self._vlan_name, None)
        self._vlan = None
        self._objects.clear()
        self._instance_owner.clear()
        self._device_meta.clear()
        self._device_stats.clear()
        self._running = False

    async def _do_add_device(
        self,
        device_id: UUID,
        slave_id: int,
        registers: list[RegisterInfo],
    ) -> None:
        """Create a virtual BACnet device application on the VLAN."""
        if self._router_app is None or not self._running:
            raise RuntimeError("BACnet adapter not started")

        instance = self._base + slave_id
        owner = self._instance_owner.get(instance)
        if owner is not None and owner != device_id:
            raise ConflictException(
                detail=(
                    f"BACnet device instance {instance} (slave {slave_id}) "
                    "is already registered by another device"
                ),
                error_code="BACNET_INSTANCE_CONFLICT",
            )

        display_name = self._device_meta.get(device_id) or f"Device_{slave_id}"
        objs: list = [
            DeviceObject(
                objectIdentifier=("device", instance),
                objectName=display_name,
                vendorIdentifier=_VENDOR_ID,
            ),
            NetworkPortObject(
                None,
                objectIdentifier=("network-port", 1),
                objectName="NetworkPort-VLAN",
                networkType="virtual",
                networkInterfaceName=self._vlan_name,
                macAddress=bytes([slave_id]),
                protocolLevel="bacnet-application",
                changesPending=False,
                outOfService=False,
                reliability="no-fault-detected",
            ),
        ]

        analog_objs: dict[int, AnalogInputObject] = {}
        for reg in registers:
            if reg.address in analog_objs:
                logger.warning(
                    "BACnet: duplicate register address %d on device %s; skipping %r",
                    reg.address, device_id, reg.name,
                )
                continue
            ai = AnalogInputObject(
                objectIdentifier=("analog-input", reg.address),
                objectName=reg.name or f"reg_{reg.address}",
                presentValue=0.0,
                outOfService=False,
                units=_UNIT_MAP.get(reg.unit or "", "no-units"),
            )
            analog_objs[reg.address] = ai
            objs.append(ai)

        app = _DeviceApplication.from_object_list(objs)
        app._ghost_adapter = self
        app._ghost_device_id = device_id

        self._device_apps[device_id] = app
        self._instance_owner[instance] = device_id
        for addr, ai in analog_objs.items():
            self._objects[(device_id, addr)] = ai

        # Announce on the network (best-effort; broadcast may not leave a
        # docker bridge — unicast reads are unaffected).
        try:
            app.i_am()
        except Exception:
            logger.debug("BACnet: I-Am broadcast failed", exc_info=True)

        logger.info(
            "BACnet: added device %s (instance %d, %d objects)",
            display_name, instance, len(analog_objs),
        )

    async def _do_remove_device(self, device_id: UUID) -> None:
        """Close and remove the device's BACnet application."""
        app = self._device_apps.pop(device_id, None)
        if app is not None:
            try:
                app.close()
            except Exception:
                logger.debug("Error closing BACnet device app", exc_info=True)
            # Application.close() does NOT detach the app's VirtualNode from
            # the VLAN (VirtualLinkLayer.close() is a no-op), so without this
            # the removed device keeps answering and re-adding the same
            # slave_id would create a duplicate-MAC node. Detach explicitly.
            for link_layer in app.link_layers.values():
                node = getattr(link_layer, "node", None)
                if node is not None and node.lan is not None:
                    node.lan.remove_node(node)
        self._objects = {
            key: obj for key, obj in self._objects.items() if key[0] != device_id
        }
        self._instance_owner = {
            inst: dev for inst, dev in self._instance_owner.items()
            if dev != device_id
        }
        self._device_meta.pop(device_id, None)
        logger.info("BACnet: removed device %s", device_id)

    async def update_register(
        self,
        device_id: UUID,
        address: int,
        function_code: int,
        value: float,
        data_type: str,
        byte_order: str,
    ) -> None:
        raise NotImplementedError  # Task 4

    def set_device_meta(self, device_id: UUID, device_name: str) -> None:
        """Set the BACnet objectName used for a device.

        MUST be called before add_device (same contract as OPC UA adapter).
        """
        self._device_meta[device_id] = device_name

    def _count_request(self, device_id: UUID, elapsed_ms: float, success: bool) -> None:
        """Record one client read against the device's stats (called by app)."""
        stats = self._device_stats.get(device_id)
        if stats is None:
            return
        stats.request_count += 1
        if success:
            stats.success_count += 1
            stats.total_response_ms += elapsed_ms
        else:
            stats.error_count += 1

    def get_status(self) -> dict:
        """Return adapter status."""
        return {
            "address": self._address,
            "port": self._port,
            "network": self._network,
            "device_instance_base": self._base,
            "running": self._running,
            "device_count": len(self._device_apps),
            "object_count": len(self._objects),
        }
