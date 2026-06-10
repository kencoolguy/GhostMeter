# BACnet/IP Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add BACnet/IP as the fifth protocol adapter — EMS clients discover N independent virtual BACnet devices behind a router (one UDP port) and read live simulated values via ReadProperty / ReadPropertyMultiple.

**Architecture:** One bacpypes3 IPv4 router Application + a VirtualNetwork (VLAN). Each GhostMeter device is its own bacpypes3 Application attached to the VLAN (device instance = `BACNET_DEVICE_INSTANCE_BASE + slave_id`, VLAN MAC = `slave_id`). Registers become read-only `analog-input` objects (instance = register address). Values are pushed via `update_register` (same model as OPC UA). Per-device stats come from overriding `do_ReadPropertyRequest` / `do_ReadPropertyMultipleRequest` on the per-device Application subclass.

**Tech Stack:** Python 3.12, bacpypes3, FastAPI lifespan integration, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-06-10-bacnet-adapter-design.md`

**Reference material (already verified):**
- bacpypes3 official sample `samples/ip-to-vlan.py` + `ip-to-vlan.json` — exact topology pattern (router app with one IPv4 network-port + one virtual network-port; each virtual device app with a virtual network-port referencing the same VLAN name).
- `bacpypes3.vlan.VirtualNetwork._networks` is a **class-level global registry**; `VirtualNetwork(name)` raises `ValueError` on duplicate name and is never auto-cleaned → `stop()` MUST pop the entry or restart/tests break.
- `bacpypes3.local.analog.AnalogInputObject` exists (verified in repo `bacpypes3/local/analog.py`).
- `NetworkPortObject(addr_string)` parses CIDR+port (e.g. `"127.0.0.1/32:47899"`); with `addr=None` it passes kwargs straight through (used for virtual ports — supply all properties the `ip-to-vlan.json` sample supplies).
- Handlers `do_ReadPropertyRequest` / `do_ReadPropertyMultipleRequest` are overridable async methods (verified in `bacpypes3/service/object.py`).
- Route-aware addressing (`"<net>:<mac>@<router-ip>:<port>"`) requires `bacpypes3.settings.settings.route_aware = True` — used by tests to reach VLAN devices through the router on loopback without broadcasts.

**Environment notes (from project memory):**
- Host tests: Python 3.12 venv, `DATABASE_URL` overridden to `localhost:5434`. Run as:
  `cd backend && DATABASE_URL=postgresql+asyncpg://ghostmeter:ghostmeter@localhost:5434/ghostmeter pytest ...`
  (check `backend/tests/conftest.py` / `.env` for the exact override used by existing tests — follow whatever `pytest` already does; most adapter tests below don't touch the DB at all).
- Branch: work continues on `feature/claude-bacnet-design-20260610`.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/requirements.txt` | Modify | add `bacpypes3` |
| `backend/app/config.py` | Modify | `BACNET_*` settings |
| `backend/app/protocols/bacnet_agent.py` | Create | `BacnetAdapter` — router+VLAN lifecycle, device apps, push updates, stats |
| `backend/app/main.py` | Modify | register adapter in lifespan |
| `backend/app/services/device_service.py` | Modify | pass device display name (mirror OPC UA `set_device_meta`) |
| `backend/app/services/monitor_service.py` | Modify | fall back to BACnet stats (currently hardcodes `modbus_tcp`) |
| `backend/app/seed/bacnet_energy_meter.json` | Create | builtin template |
| `backend/app/seed/profiles/bacnet_energy_meter_normal.json` | Create | builtin profile |
| `frontend/src/pages/Templates/TemplateForm.tsx` | Modify | protocol dropdown option |
| `docker-compose.yml` | Modify | `47808:47808/udp` |
| `backend/tests/test_bacnet_adapter.py` | Create | adapter integration tests (loopback client) |
| `CHANGELOG.md`, `docs/development-log.md`, `docs/development-phases.md`, `README.md` | Modify | docs |

---

### Task 1: Dependency + configuration

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_bacnet_adapter.py` (new)

- [ ] **Step 1.1: Add dependency and install**

In `backend/requirements.txt`, after the line `asyncua>=1.1,<2` add:

```
bacpypes3>=0.0.98
```

Then install into the project venv and pin-check:

```bash
cd backend && pip install "bacpypes3>=0.0.98" && python -c "import bacpypes3; print(bacpypes3.__version__)"
```

Expected: prints an installed version without error. If the latest version differs significantly, keep `>=0.0.98` unless install fails.

- [ ] **Step 1.2: Write failing settings test**

Create `backend/tests/test_bacnet_adapter.py`:

```python
"""Tests for the BACnet/IP adapter (real bacpypes3 client round-trips on loopback)."""

import socket
import uuid

import pytest

pytestmark = pytest.mark.asyncio


def _free_udp_port() -> int:
    """Return an unused UDP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestBacnetSettings:
    async def test_bacnet_settings_defaults(self):
        from app.config import get_settings

        s = get_settings()
        assert s.BACNET_ADDRESS == "0.0.0.0/0"
        assert s.BACNET_PORT == 47808
        assert s.BACNET_DEVICE_INSTANCE_BASE == 100000
        assert s.BACNET_NETWORK == 100
```

- [ ] **Step 1.3: Run test to verify it fails**

```bash
cd backend && pytest tests/test_bacnet_adapter.py -v
```

Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'BACNET_ADDRESS'` (or pydantic equivalent).

- [ ] **Step 1.4: Add settings**

In `backend/app/config.py`, locate the existing OPC UA block (around `OPCUA_PORT: int = 4840`) and add after it:

```python
    # BACnet/IP
    BACNET_ADDRESS: str = "0.0.0.0/0"  # CIDR; subnet mask needed for broadcast calc
    BACNET_PORT: int = 47808
    BACNET_DEVICE_INSTANCE_BASE: int = 100000  # device instance = base + slave_id; router = base
    BACNET_NETWORK: int = 100  # virtual (VLAN) network number
```

- [ ] **Step 1.5: Run test to verify it passes**

```bash
cd backend && pytest tests/test_bacnet_adapter.py -v
```

Expected: 1 passed.

- [ ] **Step 1.6: Commit**

```bash
git add backend/requirements.txt backend/app/config.py backend/tests/test_bacnet_adapter.py
git commit -m "feat: add bacpypes3 dependency and BACnet settings"
```

---

### Task 2: Adapter skeleton — router + VLAN lifecycle

**Files:**
- Create: `backend/app/protocols/bacnet_agent.py`
- Test: `backend/tests/test_bacnet_adapter.py`

- [ ] **Step 2.1: Write failing lifecycle tests**

Append to `backend/tests/test_bacnet_adapter.py`:

```python
class TestBacnetLifecycle:
    async def test_initial_status(self):
        from app.protocols.bacnet_agent import BacnetAdapter

        adapter = BacnetAdapter(address="127.0.0.1/32", port=_free_udp_port())
        status = adapter.get_status()
        assert status["running"] is False
        assert status["device_count"] == 0
        assert status["object_count"] == 0

    async def test_start_stop(self):
        from app.protocols.bacnet_agent import BacnetAdapter

        adapter = BacnetAdapter(address="127.0.0.1/32", port=_free_udp_port())
        await adapter.start()
        try:
            status = adapter.get_status()
            assert status["running"] is True
            assert status["port"] == adapter._port
        finally:
            await adapter.stop()
        assert adapter.get_status()["running"] is False

    async def test_restart_after_stop(self):
        """VLAN name must be released on stop (VirtualNetwork._networks is global)."""
        from app.protocols.bacnet_agent import BacnetAdapter

        port = _free_udp_port()
        adapter = BacnetAdapter(address="127.0.0.1/32", port=port)
        await adapter.start()
        await adapter.stop()
        # Second start must not raise "existing network" ValueError
        await adapter.start()
        try:
            assert adapter.get_status()["running"] is True
        finally:
            await adapter.stop()
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_bacnet_adapter.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.protocols.bacnet_agent'`.

- [ ] **Step 2.3: Create the adapter skeleton**

Create `backend/app/protocols/bacnet_agent.py`:

```python
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
            ipv4_port = NetworkPortObject(
                f"{self._address}:{self._port}",
                objectIdentifier=("network-port", 1),
                objectName="NetworkPort-IPv4",
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
        raise NotImplementedError  # Task 3

    async def _do_remove_device(self, device_id: UUID) -> None:
        raise NotImplementedError  # Task 3

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
```

- [ ] **Step 2.4: Run lifecycle tests**

```bash
cd backend && pytest tests/test_bacnet_adapter.py -v
```

Expected: all 4 tests pass. **If `Application.from_object_list` or the virtual `NetworkPortObject` kwargs raise**, fall back to `Application.from_json([...])` with dicts copied verbatim from the `ip-to-vlan.json` sample shape (hyphenated keys, `"mac-address": "0xfe"` as hex string) — that path is proven by the official sample. Keep whichever works and note it in the commit message.

- [ ] **Step 2.5: Commit**

```bash
git add backend/app/protocols/bacnet_agent.py backend/tests/test_bacnet_adapter.py
git commit -m "feat: BACnet adapter skeleton with router+VLAN lifecycle"
```

---

### Task 3: add_device / remove_device + client ReadProperty

**Files:**
- Modify: `backend/app/protocols/bacnet_agent.py`
- Test: `backend/tests/test_bacnet_adapter.py`

- [ ] **Step 3.1: Add the test client helper + failing tests**

Append to `backend/tests/test_bacnet_adapter.py`:

```python
import contextlib

from bacpypes3.settings import settings as bp3_settings

# Route-aware addresses ("net:mac@router-ip:port") let the test client reach
# VLAN devices through the router on loopback without any broadcasts.
bp3_settings.route_aware = True

NETWORK = 100


@contextlib.asynccontextmanager
async def _client_app():
    """A standalone bacpypes3 client application bound to loopback."""
    from bacpypes3.app import Application
    from bacpypes3.local.device import DeviceObject
    from bacpypes3.local.networkport import NetworkPortObject

    port = _free_udp_port()
    app = Application.from_object_list([
        DeviceObject(
            objectIdentifier=("device", 4194302),
            objectName="test-client",
            vendorIdentifier=999,
        ),
        NetworkPortObject(
            f"127.0.0.1/32:{port}",
            objectIdentifier=("network-port", 1),
            objectName="client-port",
        ),
    ])
    try:
        yield app
    finally:
        app.close()


def _device_addr(router_port: int, slave_id: int):
    from bacpypes3.pdu import Address

    return Address(f"{NETWORK}:{slave_id}@127.0.0.1:{router_port}")


@contextlib.asynccontextmanager
async def _running_adapter():
    """A started BacnetAdapter bound to loopback on a free port."""
    from app.protocols.bacnet_agent import BacnetAdapter

    adapter = BacnetAdapter(
        address="127.0.0.1/32",
        port=_free_udp_port(),
        device_instance_base=100000,
        network=NETWORK,
    )
    await adapter.start()
    assert adapter.get_status()["running"] is True
    try:
        yield adapter
    finally:
        await adapter.stop()


def _regs():
    from app.protocols.base import RegisterInfo

    return [
        RegisterInfo(0, 3, "float32", "big_endian", name="voltage_l1", unit="V"),
        RegisterInfo(1, 3, "float32", "big_endian", name="active_power", unit="kW"),
        RegisterInfo(2, 3, "int16", "big_endian", name="status", unit=None),
    ]


class TestBacnetAddRemoveDevice:
    async def test_add_device_creates_objects(self):
        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            status = adapter.get_status()
            assert status["device_count"] == 1
            assert status["object_count"] == 3

    async def test_client_reads_object_name_and_units(self):
        from bacpypes3.basetypes import EngineeringUnits

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            adapter.set_device_meta(device_id, "Test Meter")
            await adapter.add_device(device_id, 1, _regs())

            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                name = await client.read_property(
                    addr, ("analog-input", 0), "object-name"
                )
                assert str(name) == "voltage_l1"
                units = await client.read_property(
                    addr, ("analog-input", 0), "units"
                )
                assert units == EngineeringUnits("volts")
                dev_name = await client.read_property(
                    addr, ("device", 100001), "object-name"
                )
                assert str(dev_name) == "Test Meter"

    async def test_device_instance_conflict_raises(self):
        from app.exceptions import ConflictException

        async with _running_adapter() as adapter:
            await adapter.add_device(uuid.uuid4(), 1, _regs())
            with pytest.raises(ConflictException):
                await adapter.add_device(uuid.uuid4(), 1, _regs())

    async def test_remove_device_clears_objects(self):
        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            await adapter.remove_device(device_id)
            status = adapter.get_status()
            assert status["device_count"] == 0
            assert status["object_count"] == 0
            # Same slave_id can be re-added after removal
            await adapter.add_device(uuid.uuid4(), 1, _regs())
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_bacnet_adapter.py::TestBacnetAddRemoveDevice -v
```

Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3.3: Implement add/remove**

Replace the two `NotImplementedError` methods in `backend/app/protocols/bacnet_agent.py`:

```python
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
            kwargs: dict = {
                "objectIdentifier": ("analog-input", reg.address),
                "objectName": reg.name or f"reg_{reg.address}",
                "presentValue": 0.0,
                "outOfService": False,
                "units": _UNIT_MAP.get(reg.unit or "", "no-units"),
            }
            ai = AnalogInputObject(**kwargs)
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
        self._objects = {
            key: obj for key, obj in self._objects.items() if key[0] != device_id
        }
        self._instance_owner = {
            inst: dev for inst, dev in self._instance_owner.items()
            if dev != device_id
        }
        self._device_meta.pop(device_id, None)
        logger.info("BACnet: removed device %s", device_id)
```

Note: if `_DeviceApplication.from_object_list(objs)` returns a plain `Application` (i.e. the classmethod doesn't honor `cls`), instead create with `Application.from_object_list` and wrap stats later in Task 5 by assigning bound wrappers — but verify first; bacpypes3 classmethods use `cls(...)` so the subclass should work.

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_bacnet_adapter.py -v
```

Expected: all pass. Known risk spots and fixes:
- `units` kwarg rejected → pass `EngineeringUnits(_UNIT_MAP...)` explicitly (`from bacpypes3.basetypes import EngineeringUnits`).
- Route-aware `Address` parse error → confirm `bp3_settings.route_aware = True` runs before any `Address(...)` construction (module import order).
- `read_property` timeout → the router isn't routing; check that the device app's `network-interface-name` matches `adapter._vlan_name` exactly, and that the router's VLAN port has `networkNumber=NETWORK` configured.

- [ ] **Step 3.5: Commit**

```bash
git add backend/app/protocols/bacnet_agent.py backend/tests/test_bacnet_adapter.py
git commit -m "feat: BACnet add/remove device with per-device VLAN applications"
```

---

### Task 4: update_register push

**Files:**
- Modify: `backend/app/protocols/bacnet_agent.py`
- Test: `backend/tests/test_bacnet_adapter.py`

- [ ] **Step 4.1: Write failing test**

Append to `backend/tests/test_bacnet_adapter.py`:

```python
class TestBacnetUpdateRegister:
    async def test_update_then_client_reads_new_value(self):
        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            await adapter.update_register(
                device_id, 0, 3, 231.5, "float32", "big_endian"
            )
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                value = await client.read_property(
                    addr, ("analog-input", 0), "present-value"
                )
                assert abs(float(value) - 231.5) < 0.01

    async def test_update_unknown_register_is_noop(self):
        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            # Unknown address: must not raise
            await adapter.update_register(
                device_id, 99, 3, 1.0, "float32", "big_endian"
            )
```

- [ ] **Step 4.2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_bacnet_adapter.py::TestBacnetUpdateRegister -v
```

Expected: FAIL with `NotImplementedError`.

- [ ] **Step 4.3: Implement**

Replace `update_register` in `backend/app/protocols/bacnet_agent.py`:

```python
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
        obj.presentValue = float(value)
```

- [ ] **Step 4.4: Run tests**

```bash
cd backend && pytest tests/test_bacnet_adapter.py -v
```

Expected: all pass.

- [ ] **Step 4.5: Commit**

```bash
git add backend/app/protocols/bacnet_agent.py backend/tests/test_bacnet_adapter.py
git commit -m "feat: BACnet update_register pushes presentValue"
```

---

### Task 5: Per-device read stats

**Files:**
- Modify: `backend/app/protocols/bacnet_agent.py` (only if Step 5.2 fails — the counting subclass already exists from Task 2)
- Test: `backend/tests/test_bacnet_adapter.py`

- [ ] **Step 5.1: Write test**

Append to `backend/tests/test_bacnet_adapter.py`:

```python
class TestBacnetStats:
    async def test_read_property_counts_stats(self):
        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                await client.read_property(addr, ("analog-input", 0), "present-value")
                await client.read_property(addr, ("analog-input", 1), "present-value")

            # client reads completed → responses already sent → stats recorded
            stats = adapter.get_stats(device_id)
            assert stats is not None
            assert stats.request_count == 2
            assert stats.success_count == 2
            assert stats.error_count == 0
            assert stats.avg_response_ms >= 0.0

    async def test_reset_stats(self):
        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                await client.read_property(addr, ("analog-input", 0), "present-value")
            adapter.reset_stats(device_id)
            assert adapter.get_stats(device_id).request_count == 0
```

- [ ] **Step 5.2: Run tests**

```bash
cd backend && pytest tests/test_bacnet_adapter.py::TestBacnetStats -v
```

Expected: PASS already (the `_DeviceApplication` subclass from Task 2 + `_count_request` wiring in Task 3 cover this). If `request_count == 0`: `from_object_list` did not honor the subclass — debug by checking `type(adapter._device_apps[device_id])`; if it is plain `Application`, switch construction to `_DeviceApplication.from_object_list` → confirm `cls` propagation, or as a last resort assign bound wrappers onto the instance after creation:

```python
        # fallback only — wrap the read handlers for stats
        import types

        orig_rp = app.do_ReadPropertyRequest
        async def counted_rp(self, apdu, _orig=orig_rp):  # noqa: ANN001
            t0 = time.monotonic()
            try:
                await _orig(apdu)
            except Exception:
                self._ghost_adapter._count_request(
                    self._ghost_device_id, (time.monotonic() - t0) * 1000.0, False)
                raise
            self._ghost_adapter._count_request(
                self._ghost_device_id, (time.monotonic() - t0) * 1000.0, True)
        app.do_ReadPropertyRequest = types.MethodType(counted_rp, app)
```

- [ ] **Step 5.3: Commit**

```bash
git add backend/tests/test_bacnet_adapter.py backend/app/protocols/bacnet_agent.py
git commit -m "test: BACnet per-device read stats"
```

---

### Task 6: Discovery (Who-Is / I-Am) + ReadPropertyMultiple

**Files:**
- Test: `backend/tests/test_bacnet_adapter.py` (Application provides Who-Is and RPM services out of the box — these tests verify, no adapter code expected)

- [ ] **Step 6.1: Write tests**

Append to `backend/tests/test_bacnet_adapter.py`:

```python
class TestBacnetDiscoveryAndRpm:
    async def test_directed_whois_returns_i_am(self):
        from bacpypes3.pdu import Address

        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            async with _client_app() as client:
                # Remote-broadcast Who-Is on the VLAN, routed via the router
                addr = Address(f"{NETWORK}:*@127.0.0.1:{adapter._port}")
                i_ams = await client.who_is(100001, 100001, addr)
                assert len(i_ams) == 1
                assert i_ams[0].iAmDeviceIdentifier[1] == 100001

    async def test_read_property_multiple(self):
        async with _running_adapter() as adapter:
            device_id = uuid.uuid4()
            await adapter.add_device(device_id, 1, _regs())
            await adapter.update_register(
                device_id, 0, 3, 220.0, "float32", "big_endian"
            )
            async with _client_app() as client:
                addr = _device_addr(adapter._port, 1)
                results = await client.read_property_multiple(
                    addr,
                    [
                        "analog-input,0", ["present-value", "object-name"],
                        "analog-input,2", ["present-value"],
                    ],
                )
                values = {
                    (str(objid), str(propid)): value
                    for objid, propid, _aidx, value in results
                }
                assert abs(float(values[("analog-input,0", "present-value")]) - 220.0) < 0.01
                assert str(values[("analog-input,0", "object-name")]) == "voltage_l1"
```

- [ ] **Step 6.2: Run tests**

```bash
cd backend && pytest tests/test_bacnet_adapter.py -v
```

Expected: all pass. Risk spots:
- `who_is` to a remote-broadcast route-aware address may need `Address(f"{NETWORK}:*@127.0.0.1:{port}")` exactly; if parsing rejects `*` with route, try directed unicast `_device_addr(...)` instead — a unicast Who-Is to the device address must also produce an I-Am.
- `read_property_multiple` parameter format follows the bacpypes3 docs sample (flat list of objid string followed by property list).
- If RPM result tuples differ (`objid` typed not str), adapt the dict keys with `str()` as shown.

- [ ] **Step 6.3: Commit**

```bash
git add backend/tests/test_bacnet_adapter.py
git commit -m "test: BACnet Who-Is discovery and ReadPropertyMultiple"
```

---

### Task 7: App integration — main.py, device_service, docker-compose

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/device_service.py`
- Modify: `docker-compose.yml`

- [ ] **Step 7.1: Register adapter in lifespan**

In `backend/app/main.py`:

Add import next to the other adapter imports (line ~33):

```python
from app.protocols.bacnet_agent import BacnetAdapter
```

After the OPC UA adapter registration block (after `protocol_manager.register_adapter("opcua", opcua_adapter)`, line ~100) add:

```python
    # Register BACnet adapter
    bacnet_adapter = BacnetAdapter(
        address=settings.BACNET_ADDRESS,
        port=settings.BACNET_PORT,
        device_instance_base=settings.BACNET_DEVICE_INSTANCE_BASE,
        network=settings.BACNET_NETWORK,
    )
    protocol_manager.register_adapter("bacnet", bacnet_adapter)
```

- [ ] **Step 7.2: Pass device display name in device_service**

In `backend/app/services/device_service.py`, the OPC UA meta block (line ~349) reads:

```python
    # OPC UA needs the device display name before the Object node is created
    if template.protocol == "opcua" and protocol_manager.is_running:
        opcua_adapter = protocol_manager.get_adapter("opcua")
        if opcua_adapter is not None:
            opcua_adapter.set_device_meta(device.id, device.name)  # type: ignore[attr-defined]
```

Add directly below it:

```python
    # BACnet needs the device display name before the device object is created
    if template.protocol == "bacnet" and protocol_manager.is_running:
        bacnet_adapter = protocol_manager.get_adapter("bacnet")
        if bacnet_adapter is not None:
            bacnet_adapter.set_device_meta(device.id, device.name)  # type: ignore[attr-defined]
```

- [ ] **Step 7.3: Surface BACnet stats in monitor_service**

`backend/app/services/monitor_service.py:118` hardcodes the request-stats source:

```python
            stats = protocol_manager.get_stats("modbus_tcp", device_id)
```

Change to fall back to BACnet (a device is registered in exactly one adapter, so the first non-None hit is the device's own protocol):

```python
            stats = protocol_manager.get_stats("modbus_tcp", device_id)
            if stats is None:
                stats = protocol_manager.get_stats("bacnet", device_id)
```

Without this, BACnet devices would always show zero request stats on the Monitor page.

- [ ] **Step 7.4: docker-compose UDP port**

In `docker-compose.yml`, find the backend service `ports:` list (it has entries like `"8000:8000"`, `"502:502"`, `"10161:10161/udp"`, `"4840:4840"`) and add:

```yaml
      - "47808:47808/udp"
```

(Match the existing indentation/format of neighboring entries, including any Tailscale IP prefix used by the deploy compose file — check how SNMP's UDP entry is written and mirror it.)

- [ ] **Step 7.5: Verify the adapter boots standalone**

```bash
cd backend && timeout 15 python -c "
import asyncio
from app.protocols.bacnet_agent import BacnetAdapter

async def main():
    a = BacnetAdapter(address='127.0.0.1/32', port=47899)
    await a.start()
    print('status:', a.get_status())
    await a.stop()

asyncio.run(main())
"
```

Expected: prints `status: {... 'running': True ...}` then exits cleanly. (Full app boot needs Postgres; the existing test suite in Step 10.1 covers lifespan wiring via other integration tests.)

- [ ] **Step 7.6: Commit**

```bash
git add backend/app/main.py backend/app/services/device_service.py backend/app/services/monitor_service.py docker-compose.yml
git commit -m "feat: wire BACnet adapter into lifespan, services, docker-compose"
```

---

### Task 8: Seed template + profile

**Files:**
- Create: `backend/app/seed/bacnet_energy_meter.json`
- Create: `backend/app/seed/profiles/bacnet_energy_meter_normal.json`

(Seed loader globs `*.json` in these directories — no loader changes needed.)

- [ ] **Step 8.1: Create the template seed**

Create `backend/app/seed/bacnet_energy_meter.json`:

```json
{
  "name": "Energy Meter (BACnet)",
  "protocol": "bacnet",
  "description": "Three-phase energy meter exposed over BACnet/IP. Each register is an analog-input object (instance = address); the device instance is 100000 + slave ID behind the GhostMeter BACnet router. Function_code/byte_order are nominal (unused by BACnet, kept for schema compatibility).",
  "registers": [
    {"name": "voltage_l1", "address": 0, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "V", "description": "Phase L1 voltage", "sort_order": 0, "oid": null},
    {"name": "voltage_l2", "address": 1, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "V", "description": "Phase L2 voltage", "sort_order": 1, "oid": null},
    {"name": "voltage_l3", "address": 2, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "V", "description": "Phase L3 voltage", "sort_order": 2, "oid": null},
    {"name": "current_l1", "address": 3, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "A", "description": "Phase L1 current", "sort_order": 3, "oid": null},
    {"name": "current_l2", "address": 4, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "A", "description": "Phase L2 current", "sort_order": 4, "oid": null},
    {"name": "current_l3", "address": 5, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "A", "description": "Phase L3 current", "sort_order": 5, "oid": null},
    {"name": "active_power_total", "address": 6, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "W", "description": "Total active power", "sort_order": 6, "oid": null},
    {"name": "power_factor", "address": 7, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": null, "description": "Power factor", "sort_order": 7, "oid": null},
    {"name": "frequency", "address": 8, "function_code": 3, "data_type": "float32", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "Hz", "description": "Line frequency", "sort_order": 8, "oid": null},
    {"name": "energy_total", "address": 9, "function_code": 3, "data_type": "float64", "byte_order": "big_endian", "scale_factor": 1.0, "unit": "kWh", "description": "Cumulative active energy", "sort_order": 9, "oid": null},
    {"name": "status", "address": 10, "function_code": 3, "data_type": "int16", "byte_order": "big_endian", "scale_factor": 1.0, "unit": null, "description": "Device status (0=ok)", "sort_order": 10, "oid": null}
  ]
}
```

- [ ] **Step 8.2: Create the profile seed**

Create `backend/app/seed/profiles/bacnet_energy_meter_normal.json`:

```json
{
  "template_name": "Energy Meter (BACnet)",
  "name": "Normal Operation",
  "description": "Physically consistent three-phase meter: ~220V per phase, daily load curve on current, power computed from V*I*PF across phases, frequency ~50Hz, energy accumulating.",
  "is_default": true,
  "configs": [
    {"register_name": "voltage_l1", "data_mode": "random", "mode_params": {"base": 220, "amplitude": 3, "distribution": "gaussian"}, "update_interval_ms": 1000, "is_enabled": true},
    {"register_name": "voltage_l2", "data_mode": "random", "mode_params": {"base": 220, "amplitude": 3, "distribution": "gaussian"}, "update_interval_ms": 1000, "is_enabled": true},
    {"register_name": "voltage_l3", "data_mode": "random", "mode_params": {"base": 220, "amplitude": 3, "distribution": "gaussian"}, "update_interval_ms": 1000, "is_enabled": true},
    {"register_name": "current_l1", "data_mode": "daily_curve", "mode_params": {"base": 8, "amplitude": 6, "peak_hour": 14}, "update_interval_ms": 1000, "is_enabled": true},
    {"register_name": "current_l2", "data_mode": "daily_curve", "mode_params": {"base": 8, "amplitude": 6, "peak_hour": 14}, "update_interval_ms": 1000, "is_enabled": true},
    {"register_name": "current_l3", "data_mode": "daily_curve", "mode_params": {"base": 8, "amplitude": 6, "peak_hour": 14}, "update_interval_ms": 1000, "is_enabled": true},
    {"register_name": "power_factor", "data_mode": "random", "mode_params": {"base": 0.95, "amplitude": 0.03, "distribution": "gaussian"}, "update_interval_ms": 1000, "is_enabled": true},
    {"register_name": "active_power_total", "data_mode": "computed", "mode_params": {"expression": "({voltage_l1}*{current_l1} + {voltage_l2}*{current_l2} + {voltage_l3}*{current_l3}) * {power_factor}"}, "update_interval_ms": 1000, "is_enabled": true},
    {"register_name": "frequency", "data_mode": "random", "mode_params": {"base": 50, "amplitude": 0.05, "distribution": "gaussian"}, "update_interval_ms": 1000, "is_enabled": true},
    {"register_name": "energy_total", "data_mode": "accumulator", "mode_params": {"start_value": 0, "increment_per_second": 0.01}, "update_interval_ms": 1000, "is_enabled": true},
    {"register_name": "status", "data_mode": "static", "mode_params": {"value": 0}, "update_interval_ms": 5000, "is_enabled": true}
  ]
}
```

- [ ] **Step 8.3: Verify against existing seed tests**

The repo has seed tests (`test_seed.py`, `test_seed_profiles.py`, `test_opcua_seed.py`). Run them — if they enumerate expected template names/counts, update those expectations to include the BACnet template:

```bash
cd backend && pytest tests/test_seed.py tests/test_seed_profiles.py -v
```

Expected: pass (after updating any count/name assertions that hard-code the template list).

- [ ] **Step 8.4: Commit**

```bash
git add backend/app/seed/bacnet_energy_meter.json backend/app/seed/profiles/bacnet_energy_meter_normal.json backend/tests/
git commit -m "feat: builtin BACnet energy meter template and normal profile"
```

---

### Task 9: Frontend protocol option

**Files:**
- Modify: `frontend/src/pages/Templates/TemplateForm.tsx:12`

- [ ] **Step 9.1: Add the option**

The protocol options array currently ends with:

```typescript
  { value: "opcua", label: "OPC UA" },
```

Add after it:

```typescript
  { value: "bacnet", label: "BACnet/IP" },
```

- [ ] **Step 9.2: Check for other protocol enumerations**

```bash
cd frontend && rg -n "opcua" src/
```

Expected: only `TemplateForm.tsx`. If other files enumerate protocols (badges, filters), add `bacnet` there the same way.

- [ ] **Step 9.3: Build check**

```bash
cd frontend && npm run build
```

Expected: build succeeds with no TypeScript errors.

- [ ] **Step 9.4: Commit**

```bash
git add frontend/src/
git commit -m "feat: add BACnet/IP to protocol options"
```

---

### Task 10: Full verification + docs

**Files:**
- Modify: `CHANGELOG.md`, `docs/development-log.md`, `docs/development-phases.md`, `README.md`

- [ ] **Step 10.1: Run the full backend suite**

```bash
cd backend && pytest
```

Expected: all green (use the project's DB env override if needed: `DATABASE_URL=postgresql+asyncpg://...@localhost:5434/...`). Fix any regressions before continuing — pay attention to tests that enumerate adapters/protocols (`test_monitor_service.py`, `test_system_export_import.py`, seed tests).

- [ ] **Step 10.2: Update CHANGELOG.md**

Under `## [Unreleased]` add (create an `### Added` heading if absent):

```markdown
### Added
- BACnet/IP protocol adapter (5th protocol): Who-Is/I-Am discovery, ReadProperty / ReadPropertyMultiple. One UDP port (47808) with a virtual-network router topology — each device is an independent BACnet device instance (`100000 + slave_id`); registers map to read-only analog-input objects with engineering units. Per-device read statistics included.
- Builtin template "Energy Meter (BACnet)" with Normal Operation profile.
```

- [ ] **Step 10.3: Update docs/development-log.md**

Append an entry dated 2026-06-10 describing: BACnet adapter implementation per spec `2026-06-10-bacnet-adapter-design.md`, the router+VLAN topology decision, the `VirtualNetwork._networks` global-registry cleanup requirement discovered during implementation, and test approach (route-aware loopback client). Follow the existing entry format in the file.

- [ ] **Step 10.4: Update docs/development-phases.md**

Mark the BACnet phase (add as Phase 9 if not present) as Complete, following the file's existing format.

- [ ] **Step 10.5: Update README.md**

In the protocols/ports table add BACnet/IP — UDP 47808. Add a "known limitation" note: BACnet broadcast discovery does not traverse docker bridge networks or routed subnets (e.g. Tailscale) — clients on a different L2 segment must configure the simulator's IP statically (unicast ReadProperty and directed Who-Is work fine); BBMD support is a future item.

- [ ] **Step 10.6: Final check + commit**

```bash
cd backend && pytest && cd ../frontend && npm run build
```

Expected: backend all green, frontend builds.

```bash
git add CHANGELOG.md docs/ README.md
git commit -m "docs: BACnet adapter changelog, dev log, phases, README"
```

---

## Out of scope (per spec — do NOT implement)

- COV subscriptions, WriteProperty (objects are read-only; bacpypes3 default rejects writes to non-commandable analog-input presentValue — no extra code needed, do not add any)
- Comm-layer fault simulation (delay/timeout/reject) — future; `apply_fault`/`remove_fault` keep the base-class no-op
- BBMD / Foreign Device registration
- DB schema or `RegisterInfo` changes — none are needed
