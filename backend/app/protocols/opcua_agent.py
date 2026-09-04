"""OPC UA server adapter using asyncua (FreeOpcUa).

Exposes simulated devices as Object nodes under a GhostMeter folder, each
register as a read-only Variable node. Values are pushed in from the
simulation engine via update_register(); asyncua delivers subscription
notifications to clients automatically when a node value changes.

Security: SecurityPolicy None + Anonymous (MVP).
"""

import asyncio
import logging
import math
import random
from uuid import UUID

from asyncua import Server, ua
from asyncua.common.callback import CallbackType

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

# Writable integer ranges per Variant type (clamp targets)
_INT_RANGES: dict[ua.VariantType, tuple[int, int]] = {
    ua.VariantType.Int16: (-32768, 32767),
    ua.VariantType.UInt16: (0, 65535),
    ua.VariantType.Int32: (-2147483648, 2147483647),
    ua.VariantType.UInt32: (0, 4294967295),
}
_FLOAT32_MAX = 3.4028234663852886e38


def _coerce_to_range(value: float, vtype: ua.VariantType) -> float | int:
    """Clamp/saturate a value into the range writable for an OPC UA Variant type.

    Out-of-range values (reachable via anomaly injection) would write but then
    fail every client read with a server-side struct error, so we clamp to keep
    the node readable. Double is unconstrained (Python float is 64-bit already).
    """
    num = float(value)
    if vtype in _INT_RANGES:
        if math.isnan(num):
            return 0
        lo, hi = _INT_RANGES[vtype]
        if num <= lo:
            return lo
        if num >= hi:
            return hi
        return int(num)
    if vtype == ua.VariantType.Float and not math.isnan(num):
        return max(-_FLOAT32_MAX, min(_FLOAT32_MAX, num))
    return num


def device_object_nodeid(ns_idx: int, slave_id: int) -> ua.NodeId:
    """NodeId of a device's Object node: ``ns=<idx>;s=<slave_id>``."""
    return ua.NodeId(str(slave_id), ns_idx)


def register_nodeid(ns_idx: int, slave_id: int, register_name: str) -> ua.NodeId:
    """NodeId of a register's Variable node: ``ns=<idx>;s=<slave_id>.<register_name>``."""
    return ua.NodeId(f"{slave_id}.{register_name}", ns_idx)


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
        self._nodes: dict[tuple[UUID, int, int], object] = {}  # (dev, addr, fc) → node
        self._node_device: dict[ua.NodeId, UUID] = {}          # variable NodeId → device_id
        # nodeid → (address, name, vtype)
        self._node_write_meta: dict[ua.NodeId, tuple[int, str, ua.VariantType]] = {}
        self._device_meta: dict[UUID, str] = {}                # device_id → display name
        self._last_values: dict[tuple[UUID, int, int], tuple[float | int, ua.VariantType]] = {}
        self._faulted: set[UUID] = set()  # devices with fault callbacks attached

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
            # Delay faults sleep in this async PreRead hook (suspends only the
            # requesting session) instead of blocking the whole event loop in
            # the synchronous value callback.
            self._server.subscribe_server_callback(
                CallbackType.PreRead, self._pre_read_fault_delay,
            )
            self._server.subscribe_server_callback(
                CallbackType.PreWrite, self._pre_write_record,
            )
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
        from app.simulation import write_tracker
        for device_id in set(self._node_device.values()):
            write_tracker.clear(device_id)
        self._server = None
        self._folder = None
        self._device_objects.clear()
        self._nodes.clear()
        self._node_device.clear()
        self._node_write_meta.clear()
        self._last_values.clear()
        self._faulted.clear()
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
        """Create an Object node for the device and a Variable node per register."""
        if self._server is None or self._folder is None:
            raise RuntimeError("OPC UA server not started")

        meta_name = self._device_meta.get(device_id)
        display_name = f"{meta_name} (#{slave_id})" if meta_name else f"Device_{slave_id}"
        # Stable string NodeIds keyed by slave_id (issue #98). asyncua would
        # otherwise auto-number nodes in creation order, so ids shifted on every
        # restart / device add-remove and broke clients that store NodeIds.
        # slave_id is unique per protocol port; the display name is not (it can
        # be renamed and duplicated), so it only feeds the browse name.
        dev_obj = await self._folder.add_object(
            device_object_nodeid(self._ns_idx, slave_id),
            ua.QualifiedName(display_name, self._ns_idx),
        )
        self._device_objects[device_id] = dev_obj

        for reg in registers:
            node_name = reg.name or f"reg_{reg.address}"
            vtype, caster = _TYPE_MAP.get(reg.data_type, (ua.VariantType.Double, float))
            var = await dev_obj.add_variable(
                register_nodeid(self._ns_idx, slave_id, node_name),
                ua.QualifiedName(node_name, self._ns_idx),
                caster(0),
                varianttype=vtype,
            )
            # Unit → node Description (best-effort; non-critical for MVP)
            if reg.unit:
                try:
                    await var.write_attribute(
                        ua.AttributeIds.Description,
                        ua.DataValue(ua.Variant(
                            ua.LocalizedText(reg.unit), ua.VariantType.LocalizedText
                        )),
                    )
                except Exception:
                    logger.debug("Could not set Description for %s", node_name)
            self._nodes[(device_id, reg.address, reg.function_code)] = var
            self._node_device[var.nodeid] = device_id
            await var.set_writable(True)
            self._node_write_meta[var.nodeid] = (reg.address, node_name, vtype)
            self._last_values[(device_id, reg.address, reg.function_code)] = (
                caster(0), vtype,
            )

        logger.info(
            "OPC UA: added device %s (%s) with %d nodes",
            display_name, device_id, len(registers),
        )
        from app.simulation import fault_simulator
        if fault_simulator.get_fault(device_id) is not None:
            await self.apply_fault(device_id)

    async def _do_remove_device(self, device_id: UUID) -> None:
        """Delete the device's Object node (and child variables) and clear maps."""
        dev_obj = self._device_objects.pop(device_id, None)
        if dev_obj is not None and self._server is not None:
            try:
                await self._server.delete_nodes([dev_obj], recursive=True)
            except Exception:
                logger.debug("Error deleting OPC UA nodes for %s", device_id, exc_info=True)
        self._nodes = {
            key: node for key, node in self._nodes.items() if key[0] != device_id
        }
        self._node_device = {
            nid: did for nid, did in self._node_device.items() if did != device_id
        }
        self._node_write_meta = {
            nid: meta
            for nid, meta in self._node_write_meta.items()
            if nid in self._node_device
        }
        from app.simulation import write_tracker
        write_tracker.clear(device_id)
        self._last_values = {
            k: v for k, v in self._last_values.items() if k[0] != device_id
        }
        self._faulted.discard(device_id)
        self._device_meta.pop(device_id, None)
        logger.info("OPC UA: removed device %s", device_id)

    async def update_register(
        self,
        device_id: UUID,
        address: int,
        function_code: int,
        value: float,
        data_type: str,
        byte_order: str,
    ) -> None:
        """Push a value into the variable node (byte_order is irrelevant for OPC UA)."""
        key = (device_id, address, function_code)
        node = self._nodes.get(key)
        if node is None:
            logger.debug(
                "OPC UA: no node for device %s addr %d fc %d",
                device_id, address, function_code,
            )
            return
        vtype, _caster = _TYPE_MAP.get(data_type, (ua.VariantType.Double, float))
        coerced = _coerce_to_range(value, vtype)
        self._last_values[key] = (coerced, vtype)
        if device_id in self._faulted:
            # Node has a fault value-callback attached; writing would clear it.
            return
        await node.write_value(ua.Variant(coerced, vtype))

    # --- Fault application (overrides base no-op) ---

    def _bad_datavalue(self, status_code: int) -> "ua.DataValue":
        """Build a DataValue carrying a Bad StatusCode (no value)."""
        return ua.DataValue(StatusCode_=ua.StatusCode(status_code))

    def _good_datavalue(self, key: tuple[UUID, int, int]) -> "ua.DataValue":
        """Build a Good DataValue from the latest cached value for a node."""
        value, vtype = self._last_values.get(key, (0, ua.VariantType.Double))
        return ua.DataValue(ua.Variant(value, vtype))

    def _make_fault_callback(self, device_id: UUID, key: tuple[UUID, int, int]):
        """Create the synchronous value callback asyncua calls on every read.

        Reads fault_simulator live so it reflects the current fault type/params
        (single source of truth, same model as Modbus trace_pdu).
        """
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import get_failure_rate

        def cb(nodeid, attr):  # noqa: ANN001 — asyncua calls cb(nodeid, attr)
            fault = fault_simulator.get_fault(device_id)
            if fault is None:
                return self._good_datavalue(key)
            ftype = fault.fault_type
            if ftype == "exception":
                return self._bad_datavalue(ua.StatusCodes.BadDeviceFailure)
            if ftype == "timeout":
                return self._bad_datavalue(ua.StatusCodes.BadTimeout)
            if ftype == "delay":
                # The sleep happens in _pre_read_fault_delay (async, per
                # session); this callback must stay non-blocking and only
                # serves the cached value.
                return self._good_datavalue(key)
            if ftype == "intermittent":
                if random.random() < get_failure_rate(fault.params):
                    return self._bad_datavalue(ua.StatusCodes.BadCommunicationError)
                return self._good_datavalue(key)
            return self._good_datavalue(key)  # unknown type → behave normally

        return cb

    async def _pre_write_record(self, event, dispatcher) -> None:  # noqa: ANN001
        """PreWrite server callback: record client writes, then coerce their type.

        Records the client's ORIGINAL value (before any coercion) so the audit
        trail faithfully reflects what the client sent — coercing first would
        misreport e.g. a Double 55.9 written to an Int16 node as "55". Then
        coerces a type-mismatched Variant to the node's declared type in place so
        asyncua accepts the write and the value round-trips (read-back friendly
        until the next simulation tick overwrites it).

        Only external (network client) writes are handled — internal simulation
        updates (update_register → node.write_value, is_external=False) are
        skipped so they don't appear as client writes. Defensive: a failure here
        must not disrupt the server."""
        if not getattr(event, "is_external", False):
            return
        try:
            from app.simulation import write_tracker

            for wv in getattr(event.request_params, "NodesToWrite", None) or []:
                if wv.AttributeId != ua.AttributeIds.Value:
                    continue  # ignore non-Value attribute writes (e.g. Description)
                meta = self._node_write_meta.get(wv.NodeId)
                if meta is None:
                    continue  # not one of our register nodes
                device_id = self._node_device.get(wv.NodeId)
                if device_id is None:
                    continue
                address, node_name, expected_vtype = meta
                dv = wv.Value
                if dv is None or dv.Value is None:
                    continue
                # Record the client's original value (faithful — before coercion).
                write_tracker.record(
                    device_id, "Write", address, [str(dv.Value.Value)], node_name
                )
                # Coerce a mismatched Variant type so the write applies cleanly.
                if dv.Value.VariantType != expected_vtype:
                    coerced = _coerce_to_range(dv.Value.Value, expected_vtype)
                    wv.Value = ua.DataValue(ua.Variant(coerced, expected_vtype))
        except Exception:  # pragma: no cover — defensive; must not disrupt the server
            logger.warning("Failed to handle OPC UA client write", exc_info=True)

    async def _pre_read_fault_delay(self, event, dispatcher) -> None:  # noqa: ANN001
        """PreRead server callback: apply delay faults without blocking.

        asyncua awaits this hook inside InternalSession.read, so the sleep
        suspends only the requesting session's pipeline — the event loop
        (other protocol servers, REST, WebSocket, simulation ticks) keeps
        running. The synchronous value callback cannot do this: a time.sleep
        there stalls the entire process.
        """
        if not self._faulted:
            return
        from app.simulation import fault_simulator
        from app.simulation.fault_simulator import get_delay_seconds

        delay = 0.0
        for read_value in getattr(event.request_params, "NodesToRead", None) or []:
            device_id = self._node_device.get(read_value.NodeId)
            if device_id is None or device_id not in self._faulted:
                continue
            fault = fault_simulator.get_fault(device_id)
            if fault is not None and fault.fault_type == "delay":
                delay = max(delay, get_delay_seconds(fault.params))
        if delay > 0:
            await asyncio.sleep(delay)

    async def apply_fault(self, device_id: UUID) -> None:
        """Attach a value callback to each of the device's nodes (idempotent)."""
        if self._server is None or device_id in self._faulted:
            return
        aspace = self._server.iserver.aspace
        for key, node in list(self._nodes.items()):
            if key[0] != device_id:
                continue
            cb = self._make_fault_callback(device_id, key)
            aspace.set_attribute_value_callback(node.nodeid, ua.AttributeIds.Value, cb)
        self._faulted.add(device_id)
        logger.info("OPC UA: fault callbacks attached for device %s", device_id)

    async def remove_fault(self, device_id: UUID) -> None:
        """Detach callbacks by re-writing cached values (restores value +
        clears callback + resumes subscriptions in one write)."""
        if device_id not in self._faulted:
            return
        for key, node in list(self._nodes.items()):
            if key[0] != device_id:
                continue
            value, vtype = self._last_values.get(key, (0, ua.VariantType.Double))
            try:
                await node.write_value(ua.Variant(value, vtype))
            except Exception:
                # The node keeps its fault callback until the next update_register
                # write clears it; surface this since a stuck callback is observable.
                logger.warning(
                    "OPC UA: failed to restore node %s after fault clear (device %s); "
                    "its fault callback persists until the next value update",
                    key, device_id, exc_info=True,
                )
        self._faulted.discard(device_id)
        logger.info("OPC UA: fault callbacks removed for device %s", device_id)

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
