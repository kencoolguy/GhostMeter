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

import asyncio
import ipaddress
import logging
import math
import random
import socket
import time
from uuid import UUID

from bacpypes3.app import Application
from bacpypes3.errors import ExecutionError
from bacpypes3.local.analog import AnalogInputObject
from bacpypes3.local.device import DeviceObject
from bacpypes3.local.networkport import NetworkPortObject
from bacpypes3.object import Object
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
_FLOAT32_MAX = 3.4028234663852886e38  # BACnet Real is float32 on the wire


def _clamp_to_real(value: float) -> float:
    """Clamp to the float32-representable range.

    Out-of-range values (reachable via anomaly injection) raise OverflowError
    when bacpypes3 encodes the Real response, turning every client read into
    an operational-problem error. NaN/inf are valid float32 patterns and pass
    through unchanged.
    """
    if math.isnan(value) or math.isinf(value):
        return value
    return max(-_FLOAT32_MAX, min(_FLOAT32_MAX, value))


class _DeviceApplication(Application):
    """Per-device BACnet application that counts read requests for stats.

    Instances are created via Application.from_object_list(); the adapter
    sets _ghost_adapter/_ghost_device_id right after construction.
    """

    _ghost_adapter: "BacnetAdapter | None" = None
    _ghost_device_id: UUID | None = None

    async def _drop_for_fault(self) -> bool:
        """Pull-based comm-fault gate for confirmed read requests.

        Returns True when the request must be dropped (timeout / intermittent
        — the client sees a timeout). Sleeps for delay faults and raises
        ExecutionError for exception faults (bacpypes3 converts it to a BACnet
        Error APDU, same path as the WriteProperty rejection).
        """
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import get_delay_seconds, get_failure_rate

        fault = fault_simulator.get_fault(self._ghost_device_id)
        if fault is None:
            return False
        if fault.fault_type == "timeout":
            return True
        if fault.fault_type == "intermittent":
            return random.random() < get_failure_rate(fault.params)
        if fault.fault_type == "delay":
            await asyncio.sleep(get_delay_seconds(fault.params))
            return False
        if fault.fault_type == "exception":
            raise ExecutionError(errorClass="device", errorCode="operationalProblem")
        return False

    async def do_ReadPropertyRequest(self, apdu) -> None:
        t0 = time.monotonic()
        try:
            if await self._drop_for_fault():
                self._count(t0, success=False)
                return
            await super().do_ReadPropertyRequest(apdu)
        except Exception:
            self._count(t0, success=False)
            raise
        self._count(t0, success=True)

    async def do_ReadPropertyMultipleRequest(self, apdu) -> None:
        t0 = time.monotonic()
        try:
            if await self._drop_for_fault():
                self._count(t0, success=False)
                return
            await super().do_ReadPropertyMultipleRequest(apdu)
        except Exception:
            self._count(t0, success=False)
            raise
        self._count(t0, success=True)

    async def do_WritePropertyRequest(self, apdu) -> None:
        """Simulated devices are read-only; values come from the simulation
        engine. bacpypes3's local objects would otherwise accept the write."""
        raise ExecutionError(errorClass="property", errorCode="writeAccessDenied")

    async def do_WhoIsRequest(self, apdu) -> None:
        """A device under timeout/intermittent fault goes fully dark (no I-Am),
        like a real dead device. delay/exception only affect reads."""
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import get_failure_rate

        fault = fault_simulator.get_fault(self._ghost_device_id)
        if fault is not None:
            if fault.fault_type == "timeout":
                return
            if fault.fault_type == "intermittent" and random.random() < get_failure_rate(
                fault.params
            ):
                return
        await super().do_WhoIsRequest(apdu)

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
            # bacpypes3 binds its UDP socket in a background task that retries
            # forever on OSError, so Application.from_object_list() returns
            # successfully even when the port is already taken. Probe-bind a
            # throwaway socket first so a port conflict fails loudly here
            # (running=False) instead of silently serving nothing.
            # SO_REUSEADDR lets bacpypes3 rebind immediately after the probe
            # closes; it does NOT let the probe bind over a foreign socket on
            # macOS/Linux unless that socket also set it, so the check holds.
            bind_host = self._address.split("/", 1)[0]
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind((bind_host, self._port))

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
            if ipaddress.ip_network(self._address, strict=False).prefixlen == 0:
                self._disable_broadcast_endpoints(self._router_app)
                logger.warning(
                    "BACNET_ADDRESS %s has no usable subnet broadcast; broadcast "
                    "endpoint disabled (unicast reads work; Who-Is broadcast "
                    "discovery requires a concrete interface CIDR, e.g. 192.168.1.10/24)",
                    self._address,
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
            self._cancel_transport_tasks(self._router_app)
            try:
                self._router_app.close()
            except Exception:
                logger.debug("Error closing BACnet router app", exc_info=True)
            self._router_app = None
        # VirtualNetwork keeps a global name registry; release our entry so
        # restart (and the test suite) can re-create the network. Guarded so
        # that a failed start() caused by ANOTHER adapter owning this VLAN
        # name (ValueError from VirtualNetwork()) does not remove the other
        # instance's registry entry — in that case self._vlan is still None.
        if VirtualNetwork._networks.get(self._vlan_name) is self._vlan:
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

        # Defensive: re-adding an already-registered device_id would overwrite
        # its app and strand the old VLAN node. Unreachable via the service
        # layer (start requires status "stopped"), but cheap to guard.
        stale_app = self._device_apps.pop(device_id, None)
        if stale_app is not None:
            self._detach_vlan_nodes(stale_app)
            try:
                stale_app.close()
            except Exception:
                logger.debug("Error closing stale BACnet device app", exc_info=True)

        display_name = self._device_meta.get(device_id) or f"Device_{slave_id}"
        core_objs: list[Object] = [
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

        # Build the app from the device + VLAN port first (this attaches the
        # app's VirtualNode to the VLAN), then add the analog inputs one by
        # one. If any add_object raises (e.g. a register name colliding with
        # an internal object name → duplicate objectName RuntimeError), the
        # half-built app must be fully torn down — otherwise its VLAN node
        # lingers and a retried slave_id would create a duplicate-MAC node.
        app = _DeviceApplication.from_object_list(core_objs)
        app._ghost_adapter = self
        app._ghost_device_id = device_id

        analog_objs: dict[int, AnalogInputObject] = {}
        try:
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
                app.add_object(ai)
                analog_objs[reg.address] = ai
        except Exception:
            self._detach_vlan_nodes(app)
            try:
                app.close()
            except Exception:
                logger.debug(
                    "Error closing half-built BACnet device app", exc_info=True,
                )
            raise

        self._device_apps[device_id] = app
        self._instance_owner[instance] = device_id
        for addr, ai in analog_objs.items():
            self._objects[(device_id, addr)] = ai

        # Announce on the network (best-effort; broadcast may not leave a
        # docker bridge — unicast reads are unaffected). On /31 and /32 binds
        # (loopback tests, single-IP Tailscale deploys) the prefix has no
        # broadcast address and i_am() would raise RuntimeError("no broadcast")
        # in a background task on every device start — skip it entirely.
        # Same for /0 (wildcard): its broadcast endpoint is disabled in
        # start(), so a broadcast I-Am cannot work there either.
        prefixlen = ipaddress.ip_network(self._address, strict=False).prefixlen
        if prefixlen >= 31 or prefixlen == 0:
            logger.debug(
                "BACnet: skipping I-Am broadcast (no broadcast address on %s)",
                self._address,
            )
        else:
            try:
                app.i_am()
            except Exception:
                logger.debug("BACnet: I-Am broadcast failed", exc_info=True)

        logger.info(
            "BACnet: added device %s (instance %d, %d objects)",
            display_name, instance, len(analog_objs),
        )

    @staticmethod
    def _disable_broadcast_endpoints(app: Application) -> None:
        """Remove the doomed broadcast-bind task so replies are not blocked.

        With a wildcard bind (0.0.0.0/0) the subnet broadcast is
        255.255.255.255, which cannot be bound on macOS; bacpypes3 retries
        that bind forever AND awaits it before sending any reply
        (IPv4DatagramServer.indication gathers _transport_tasks), so every
        response would hang. Dropping the task unblocks unicast traffic.
        Cancelling triggers one harmless "Exception in callback ...
        CancelledError" log line from bacpypes3's done-callback.
        """
        for link_layer in getattr(app, "link_layers", {}).values():
            server = getattr(link_layer, "server", None)
            tasks = getattr(server, "_transport_tasks", None)
            if not tasks or len(tasks) < 2:
                continue
            # _transport_tasks = [local_endpoint_task, broadcast_endpoint_task]
            broadcast_task = tasks.pop(1)
            broadcast_task.cancel()
            server.broadcast_address = None  # LocalBroadcast sends now fail fast

    @staticmethod
    def _cancel_transport_tasks(app: Application) -> None:
        """Cancel pending UDP bind tasks on the app's IPv4 link layers.

        bacpypes3's IPv4DatagramServer binds in a background task that
        retries forever on OSError, and its close() only closes already-bound
        transports — a still-retrying task survives stop() and would bind an
        orphan socket if the port later frees up. Best-effort: link layers
        without a .server / _transport_tasks (e.g. VLAN) are skipped.

        Cancelling a still-pending task may log a harmless "Exception in
        callback ... CancelledError" traceback: bacpypes3's own done-callback
        (set_local_transport_protocol) calls task.result() unguarded. Noise
        only; the alternative is leaking the orphan bind task.
        """
        for link_layer in getattr(app, "link_layers", {}).values():
            server = getattr(link_layer, "server", None)
            for task in getattr(server, "_transport_tasks", None) or []:
                try:
                    if not task.done():
                        task.cancel()
                except Exception:
                    logger.debug(
                        "Error cancelling BACnet transport task", exc_info=True,
                    )

    @staticmethod
    def _detach_vlan_nodes(app: Application) -> None:
        """Detach the app's VirtualNode(s) from the VLAN.

        Application.close() does NOT do this (VirtualLinkLayer.close() is a
        no-op in bacpypes3 0.0.106), so without it a removed/failed device
        keeps answering on the VLAN and a re-added slave_id would create a
        duplicate-MAC node.
        """
        for link_layer in getattr(app, "link_layers", {}).values():
            node = getattr(link_layer, "node", None)
            if node is not None and node.lan is not None:
                node.lan.remove_node(node)

    async def _do_remove_device(self, device_id: UUID) -> None:
        """Close and remove the device's BACnet application."""
        app = self._device_apps.pop(device_id, None)
        if app is not None:
            try:
                app.close()
            except Exception:
                logger.debug("Error closing BACnet device app", exc_info=True)
            self._detach_vlan_nodes(app)
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
        """Push a value into the analog-input object (function_code/byte_order
        are irrelevant for BACnet; presentValue is always Real)."""
        obj = self._objects.get((device_id, address))
        if obj is None:
            logger.debug(
                "BACnet: no object for device %s addr %d", device_id, address,
            )
            return
        obj.presentValue = _clamp_to_real(float(value))

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
