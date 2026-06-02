# OPC UA Server Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an OPC UA server protocol adapter so EMS/SCADA OPC UA clients can browse the address space, read live simulated register values, and subscribe to value changes.

**Architecture:** A single shared `asyncua.Server` (endpoint `opc.tcp://0.0.0.0:4840/ghostmeter/server/`, Anonymous + SecurityPolicy None). Each device becomes an Object node under a `GhostMeter` folder; each register becomes a read-only Variable node. Value sync is **push**: the simulation engine's `update_register` call writes into the node, and asyncua delivers subscription notifications automatically. Wiring mirrors the existing Modbus/SNMP/MQTT adapters via `ProtocolManager`.

**Tech Stack:** Python 3.12, FastAPI, `asyncua` (FreeOpcUa async OPC UA), pytest + pytest-asyncio, SQLAlchemy 2.0. Frontend: React + Ant Design (one dropdown option).

**Spec:** `docs/superpowers/specs/2026-06-03-opcua-adapter-design.md`

---

## File Structure

**Create:**
- `backend/app/protocols/opcua_agent.py` — `OpcUaAdapter` (server lifecycle, node management, value push)
- `backend/app/seed/opcua_energy_meter.json` — built-in OPC UA template
- `backend/app/seed/profiles/opcua_energy_meter_normal.json` — built-in profile
- `backend/tests/test_opcua_adapter.py` — adapter unit/integration tests (real asyncua client)
- `backend/tests/test_opcua_seed.py` — seed JSON validation tests

**Modify:**
- `backend/requirements.txt` — add `asyncua`
- `backend/app/protocols/base.py` — extend `RegisterInfo` with `name`, `unit`
- `backend/app/config.py` — OPC UA settings
- `backend/.env.example` — OPC UA env vars
- `backend/app/main.py` — register adapter + resume-path wiring
- `backend/app/services/device_service.py` — `set_device_meta` + `RegisterInfo` name/unit
- `backend/tests/test_seed.py` — bump builtin template count 4 → 5
- `docker-compose.yml` — expose port 4840
- `frontend/src/pages/Templates/TemplateForm.tsx` — add OPC UA protocol option
- `CHANGELOG.md`, `docs/development-log.md`, `docs/development-phases.md` — docs

---

## Task 1: Add asyncua dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add the dependency**

Add this line to `backend/requirements.txt` (alongside the other protocol libs like `pymodbus`, `pysnmp`):

```
asyncua>=1.1,<2
```

- [ ] **Step 2: Install it**

Run: `cd backend && pip install -r requirements.txt`
Expected: `asyncua` installs successfully (pulls `cryptography`, `aiofiles`, etc.)

- [ ] **Step 3: Verify import works**

Run: `cd backend && python -c "from asyncua import Server, Client, ua; print('ok')"`
Expected: prints `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore: add asyncua dependency for OPC UA adapter"
```

---

## Task 2: Extend RegisterInfo with name and unit

**Files:**
- Modify: `backend/app/protocols/base.py:8-16`
- Test: `backend/tests/test_opcua_adapter.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_opcua_adapter.py` with this module header and first test:

```python
"""Tests for the OPC UA server adapter (real asyncua client round-trips)."""

import asyncio
import socket
import uuid

import pytest

pytestmark = pytest.mark.asyncio


def _free_port() -> int:
    """Return an unused TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _SubHandler:
    """Collects datachange notifications from an asyncua subscription."""

    def __init__(self) -> None:
        self.values: list = []

    def datachange_notification(self, node, val, data) -> None:  # noqa: ANN001
        self.values.append(val)


class TestRegisterInfoExtension:
    async def test_registerinfo_accepts_name_and_unit(self):
        from app.protocols.base import RegisterInfo

        reg = RegisterInfo(0, 3, "float32", "big_endian", name="voltage_l1", unit="V")
        assert reg.name == "voltage_l1"
        assert reg.unit == "V"

    async def test_registerinfo_name_unit_default_none(self):
        """Existing callers that omit name/unit still work (backward compat)."""
        from app.protocols.base import RegisterInfo

        reg = RegisterInfo(0, 3, "float32", "big_endian")
        assert reg.name is None
        assert reg.unit is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestRegisterInfoExtension -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'name'`

- [ ] **Step 3: Extend the dataclass**

In `backend/app/protocols/base.py`, replace the `RegisterInfo` dataclass body (lines 8-16) with:

```python
@dataclass
class RegisterInfo:
    """Lightweight register descriptor passed to protocol adapters."""

    address: int
    function_code: int  # 3=holding, 4=input
    data_type: str      # int16, uint16, int32, uint32, float32, float64
    byte_order: str     # big_endian, little_endian, etc.
    oid: str | None = None   # SNMP OID string, null for Modbus
    name: str | None = None  # register name → OPC UA browse/display name
    unit: str | None = None  # → OPC UA node Description (interim EngineeringUnits)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestRegisterInfoExtension -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Confirm no regression in existing adapters**

Run: `cd backend && pytest tests/test_snmp.py tests/test_modbus.py -q`
Expected: PASS (existing adapter tests still green)

- [ ] **Step 6: Commit**

```bash
git add backend/app/protocols/base.py backend/tests/test_opcua_adapter.py
git commit -m "feat: extend RegisterInfo with optional name and unit fields"
```

---

## Task 3: Add OPC UA configuration settings

**Files:**
- Modify: `backend/app/config.py:33-35` (after the SNMP block)
- Modify: `backend/.env.example`
- Test: `backend/tests/test_opcua_adapter.py`

- [ ] **Step 1: Write the failing test**

Append this class to `backend/tests/test_opcua_adapter.py`:

```python
class TestOpcUaSettings:
    async def test_opcua_settings_defaults(self):
        from app.config import get_settings

        s = get_settings()
        assert s.OPCUA_PORT == 4840
        assert s.OPCUA_HOST == "0.0.0.0"
        assert s.OPCUA_NAMESPACE_URI == "http://ghostmeter.local/opcua/"
        assert s.OPCUA_ENDPOINT_PATH == "/ghostmeter/server/"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestOpcUaSettings -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'OPCUA_PORT'`

- [ ] **Step 3: Add the settings**

In `backend/app/config.py`, immediately after the SNMP block (line 35, after `SNMP_COMMUNITY`), insert:

```python

    # OPC UA
    OPCUA_HOST: str = "0.0.0.0"
    OPCUA_PORT: int = 4840
    OPCUA_ENDPOINT_PATH: str = "/ghostmeter/server/"
    OPCUA_SERVER_NAME: str = "GhostMeter OPC UA Server"
    OPCUA_NAMESPACE_URI: str = "http://ghostmeter.local/opcua/"
```

- [ ] **Step 4: Add to .env.example**

In the canonical root `.env.example` (NOT `backend/.env.example` — config uses `env_file="../.env"` and the README references the root file), add after the Modbus block:

```
# OPC UA
OPCUA_HOST=0.0.0.0
OPCUA_PORT=4840
OPCUA_ENDPOINT_PATH=/ghostmeter/server/
OPCUA_SERVER_NAME=GhostMeter OPC UA Server
OPCUA_NAMESPACE_URI=http://ghostmeter.local/opcua/
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestOpcUaSettings -v`
Expected: PASS (1 passed). Note: `get_settings` is `@lru_cache`d; a fresh test process picks up the new defaults.

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/.env.example backend/tests/test_opcua_adapter.py
git commit -m "feat: add OPC UA server configuration settings"
```

---

## Task 4: OpcUaAdapter — server start/stop lifecycle

**Files:**
- Create: `backend/app/protocols/opcua_agent.py`
- Test: `backend/tests/test_opcua_adapter.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_opcua_adapter.py`:

```python
class TestOpcUaLifecycle:
    async def test_initial_status(self):
        from app.protocols.opcua_agent import OpcUaAdapter

        adapter = OpcUaAdapter(host="127.0.0.1", port=_free_port())
        status = adapter.get_status()
        assert status["running"] is False
        assert status["device_count"] == 0
        assert status["node_count"] == 0

    async def test_start_then_client_can_connect(self):
        from asyncua import Client

        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        try:
            assert adapter.get_status()["running"] is True
            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                assert ns >= 0
                # GhostMeter folder exists under Objects
                folder = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                assert folder is not None
        finally:
            await adapter.stop()
        assert adapter.get_status()["running"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestOpcUaLifecycle -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.protocols.opcua_agent'`

- [ ] **Step 3: Create the adapter file**

Create `backend/app/protocols/opcua_agent.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestOpcUaLifecycle -v`
Expected: PASS (2 passed). If the connect test fails on endpoint URL, confirm the server advertises `127.0.0.1` (host param), not `0.0.0.0`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/protocols/opcua_agent.py backend/tests/test_opcua_adapter.py
git commit -m "feat: add OpcUaAdapter server start/stop lifecycle"
```

---

## Task 5: OpcUaAdapter — add_device creates nodes

**Files:**
- Modify: `backend/app/protocols/opcua_agent.py` (`_do_add_device`)
- Test: `backend/tests/test_opcua_adapter.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_opcua_adapter.py`:

```python
class TestOpcUaAddDevice:
    async def test_add_device_creates_named_nodes(self):
        from asyncua import Client

        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        device_id = uuid.uuid4()
        regs = [
            RegisterInfo(0, 3, "float32", "big_endian", name="voltage_l1", unit="V"),
            RegisterInfo(1, 3, "uint32", "big_endian", name="active_power", unit="W"),
        ]
        try:
            adapter.set_device_meta(device_id, "Test Meter")
            await adapter.add_device(device_id, 1, regs)

            status = adapter.get_status()
            assert status["device_count"] == 1
            assert status["node_count"] == 2

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                dev = await gm.get_child([f"{ns}:Test Meter"])
                var = await dev.get_child([f"{ns}:voltage_l1"])
                assert await var.read_value() == 0.0
        finally:
            await adapter.stop()

    async def test_add_device_falls_back_to_slave_name(self):
        """When set_device_meta is not called, object is named Device_<slave_id>."""
        from asyncua import Client

        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        device_id = uuid.uuid4()
        regs = [RegisterInfo(0, 3, "float32", "big_endian", name="frequency")]
        try:
            await adapter.add_device(device_id, 7, regs)
            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                dev = await gm.get_child([f"{ns}:Device_7"])
                assert dev is not None
        finally:
            await adapter.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestOpcUaAddDevice -v`
Expected: FAIL — `node_count == 0` (placeholder) / `get_child` raises BadNoMatch (no node created)

- [ ] **Step 3: Implement _do_add_device**

In `backend/app/protocols/opcua_agent.py`, replace the `_do_add_device` placeholder with:

```python
    async def _do_add_device(
        self,
        device_id: UUID,
        slave_id: int,
        registers: list[RegisterInfo],
    ) -> None:
        """Create an Object node for the device and a Variable node per register."""
        if self._server is None or self._folder is None:
            raise RuntimeError("OPC UA server not started")

        display_name = self._device_meta.get(device_id) or f"Device_{slave_id}"
        dev_obj = await self._folder.add_object(self._ns_idx, display_name)
        self._device_objects[device_id] = dev_obj

        for reg in registers:
            node_name = reg.name or f"reg_{reg.address}"
            vtype, caster = _TYPE_MAP.get(reg.data_type, (ua.VariantType.Double, float))
            var = await dev_obj.add_variable(
                self._ns_idx,
                node_name,
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

        logger.info(
            "OPC UA: added device %s (%s) with %d nodes",
            display_name, device_id, len(registers),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestOpcUaAddDevice -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/protocols/opcua_agent.py backend/tests/test_opcua_adapter.py
git commit -m "feat: OpcUaAdapter creates device object and register variable nodes"
```

---

## Task 6: OpcUaAdapter — update_register pushes values (all data types)

**Files:**
- Modify: `backend/app/protocols/opcua_agent.py` (`update_register`)
- Test: `backend/tests/test_opcua_adapter.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_opcua_adapter.py`:

```python
class TestOpcUaUpdateRegister:
    @pytest.mark.parametrize(
        "data_type,written,expected",
        [
            ("float32", 220.5, 220.5),
            ("float64", 49.985, 49.985),
            ("int16", -123.0, -123),
            ("uint16", 1000.0, 1000),
            ("int32", -70000.0, -70000),
            ("uint32", 250000.0, 250000),
        ],
    )
    async def test_update_register_round_trips(self, data_type, written, expected):
        from asyncua import Client

        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        device_id = uuid.uuid4()
        regs = [RegisterInfo(0, 3, data_type, "big_endian", name="value")]
        try:
            adapter.set_device_meta(device_id, "DT")
            await adapter.add_device(device_id, 1, regs)
            await adapter.update_register(device_id, 0, 3, written, data_type, "big_endian")

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                dev = await gm.get_child([f"{ns}:DT"])
                var = await dev.get_child([f"{ns}:value"])
                read = await var.read_value()
                assert abs(read - expected) < 0.01
        finally:
            await adapter.stop()

    async def test_update_unknown_register_is_noop(self):
        """Writing to a non-existent (device, addr, fc) does not raise."""
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        try:
            await adapter.update_register(
                uuid.uuid4(), 99, 3, 1.0, "float32", "big_endian"
            )
        finally:
            await adapter.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestOpcUaUpdateRegister -v`
Expected: FAIL — read values stay `0` (placeholder `update_register` does nothing)

- [ ] **Step 3: Implement update_register**

In `backend/app/protocols/opcua_agent.py`, replace the `update_register` placeholder body with:

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
        """Push a value into the variable node (byte_order is irrelevant for OPC UA)."""
        node = self._nodes.get((device_id, address, function_code))
        if node is None:
            logger.debug(
                "OPC UA: no node for device %s addr %d fc %d",
                device_id, address, function_code,
            )
            return
        vtype, caster = _TYPE_MAP.get(data_type, (ua.VariantType.Double, float))
        await node.write_value(ua.Variant(caster(value), vtype))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestOpcUaUpdateRegister -v`
Expected: PASS (7 passed — 6 parametrized + 1 noop)

- [ ] **Step 5: Commit**

```bash
git add backend/app/protocols/opcua_agent.py backend/tests/test_opcua_adapter.py
git commit -m "feat: OpcUaAdapter update_register pushes typed values to nodes"
```

---

## Task 7: OpcUaAdapter — subscription notification (push-model proof)

**Files:**
- Test only: `backend/tests/test_opcua_adapter.py` (no production code change — verifies Task 6 behavior end-to-end)

- [ ] **Step 1: Write the test**

Append to `backend/tests/test_opcua_adapter.py`:

```python
class TestOpcUaSubscription:
    async def test_subscription_fires_on_value_change(self):
        """A subscribed client receives a notification when update_register runs.

        This is the core OPC UA value-add: the push model makes Subscribe work.
        """
        from asyncua import Client

        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        device_id = uuid.uuid4()
        regs = [RegisterInfo(0, 3, "float32", "big_endian", name="voltage")]
        try:
            adapter.set_device_meta(device_id, "SubMeter")
            await adapter.add_device(device_id, 1, regs)

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                dev = await gm.get_child([f"{ns}:SubMeter"])
                var = await dev.get_child([f"{ns}:voltage"])

                handler = _SubHandler()
                sub = await client.create_subscription(50, handler)
                await sub.subscribe_data_change(var)
                # initial notification arrives with value 0
                await asyncio.sleep(0.3)

                await adapter.update_register(
                    device_id, 0, 3, 231.4, "float32", "big_endian"
                )
                await asyncio.sleep(0.5)
                await sub.delete()

                assert any(abs(v - 231.4) < 0.05 for v in handler.values), (
                    f"expected 231.4 in notifications, got {handler.values}"
                )
        finally:
            await adapter.stop()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestOpcUaSubscription -v`
Expected: PASS (1 passed). If it flakes, increase the post-update sleep to `1.0`s. If notifications never arrive, confirm `update_register` writes a *changed* value (asyncua only notifies on change).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_opcua_adapter.py
git commit -m "test: verify OPC UA subscription fires on register value change"
```

---

## Task 8: OpcUaAdapter — remove_device cleans up nodes

**Files:**
- Modify: `backend/app/protocols/opcua_agent.py` (`_do_remove_device`)
- Test: `backend/tests/test_opcua_adapter.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_opcua_adapter.py`:

```python
class TestOpcUaRemoveDevice:
    async def test_remove_device_clears_nodes(self):
        from asyncua import Client, ua
        from asyncua.ua.uaerrors import BadNoMatch

        from app.protocols.base import RegisterInfo
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        await adapter.start()
        device_id = uuid.uuid4()
        regs = [
            RegisterInfo(0, 3, "float32", "big_endian", name="voltage_l1"),
            RegisterInfo(1, 3, "float32", "big_endian", name="voltage_l2"),
        ]
        try:
            adapter.set_device_meta(device_id, "Gone")
            await adapter.add_device(device_id, 1, regs)
            assert adapter.get_status()["node_count"] == 2

            await adapter.remove_device(device_id)
            status = adapter.get_status()
            assert status["device_count"] == 0
            assert status["node_count"] == 0

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as client:
                ns = await client.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                gm = await client.nodes.objects.get_child([f"{ns}:GhostMeter"])
                with pytest.raises(BadNoMatch):
                    await gm.get_child([f"{ns}:Gone"])
        finally:
            await adapter.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestOpcUaRemoveDevice -v`
Expected: FAIL — `device_count`/`node_count` still non-zero (placeholder `_do_remove_device`)

- [ ] **Step 3: Implement _do_remove_device**

In `backend/app/protocols/opcua_agent.py`, replace the `_do_remove_device` placeholder with:

```python
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
        logger.info("OPC UA: removed device %s", device_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestOpcUaRemoveDevice -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the whole adapter test file**

Run: `cd backend && pytest tests/test_opcua_adapter.py -q`
Expected: PASS (all classes green)

- [ ] **Step 6: Commit**

```bash
git add backend/app/protocols/opcua_agent.py backend/tests/test_opcua_adapter.py
git commit -m "feat: OpcUaAdapter remove_device deletes nodes and clears maps"
```

---

## Task 9: Built-in OPC UA template seed

**Files:**
- Create: `backend/app/seed/opcua_energy_meter.json`
- Create: `backend/tests/test_opcua_seed.py`
- Modify: `backend/tests/test_seed.py:15,29` (count 4 → 5) and `:17-20` (add name assertion)

- [ ] **Step 1: Write the failing seed-validation test**

Create `backend/tests/test_opcua_seed.py`:

```python
"""Validate the OPC UA built-in template and profile seed JSON files."""

import json
from pathlib import Path

SEED = Path(__file__).parent.parent / "app" / "seed"


def test_opcua_template_seed_valid():
    data = json.loads((SEED / "opcua_energy_meter.json").read_text())
    assert data["name"] == "Energy Meter (OPC UA)"
    assert data["protocol"] == "opcua"
    assert len(data["registers"]) == 11
    addrs = set()
    for reg in data["registers"]:
        assert reg["name"]                    # OPC UA needs a real name
        assert reg["oid"] is None             # no OID for OPC UA
        key = (reg["address"], reg["function_code"])
        assert key not in addrs, f"duplicate (address, fc): {key}"
        addrs.add(key)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_opcua_seed.py::test_opcua_template_seed_valid -v`
Expected: FAIL — `FileNotFoundError: ... opcua_energy_meter.json`

- [ ] **Step 3: Create the template seed JSON**

Create `backend/app/seed/opcua_energy_meter.json`:

```json
{
  "name": "Energy Meter (OPC UA)",
  "protocol": "opcua",
  "description": "Three-phase energy meter exposed over OPC UA. Registers are surfaced as browsable Variable nodes. Address/function_code are nominal (unused by OPC UA, kept for schema compatibility).",
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

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_opcua_seed.py::test_opcua_template_seed_valid -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Update the builtin template count in test_seed.py**

In `backend/tests/test_seed.py`:
- Line 15: change `assert len(builtin) == 4` → `assert len(builtin) == 5`
- Line 29: change `assert len(builtin) == 4` → `assert len(builtin) == 5`
- After line 20 (`assert "SunSpec Solar Inverter" in names`), add:

```python
        assert "Energy Meter (OPC UA)" in names
```

- [ ] **Step 6: Run the seed test to verify it passes**

Run: `cd backend && pytest tests/test_seed.py -q`
Expected: PASS (the new OPC UA template is loaded by the glob-based loader; count is now 5)

- [ ] **Step 7: Commit**

```bash
git add backend/app/seed/opcua_energy_meter.json backend/tests/test_opcua_seed.py backend/tests/test_seed.py
git commit -m "feat: add built-in Energy Meter (OPC UA) template seed"
```

---

## Task 10: Built-in OPC UA profile seed

**Files:**
- Create: `backend/app/seed/profiles/opcua_energy_meter_normal.json`
- Modify: `backend/tests/test_opcua_seed.py` (add profile test)

- [ ] **Step 1: Write the failing profile-validation test**

Append to `backend/tests/test_opcua_seed.py`:

```python
def test_opcua_profile_seed_valid():
    data = json.loads(
        (SEED / "profiles" / "opcua_energy_meter_normal.json").read_text()
    )
    assert data["template_name"] == "Energy Meter (OPC UA)"
    assert data["name"] == "Normal Operation"
    assert data["is_default"] is True

    template = json.loads((SEED / "opcua_energy_meter.json").read_text())
    reg_names = {r["name"] for r in template["registers"]}
    config_names = {c["register_name"] for c in data["configs"]}
    # every profile config must reference a real register
    assert config_names <= reg_names, f"unknown registers: {config_names - reg_names}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_opcua_seed.py::test_opcua_profile_seed_valid -v`
Expected: FAIL — `FileNotFoundError: ... opcua_energy_meter_normal.json`

- [ ] **Step 3: Create the profile seed JSON**

Create `backend/app/seed/profiles/opcua_energy_meter_normal.json`:

```json
{
  "template_name": "Energy Meter (OPC UA)",
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

> Param names verified against `backend/app/simulation/data_generator.py`: `random`→`base`/`amplitude`/`distribution`; `daily_curve`→`base`/`amplitude`/`peak_hour`; `computed`→`expression`; `accumulator`→`start_value`/`increment_per_second`; `static`→`value`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_opcua_seed.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Verify the profile loads and links via the seed loader**

Run: `cd backend && pytest tests/test_seed_profiles.py -q`
Expected: PASS (`test_seed_creates_profiles` now also covers the OPC UA template — it asserts every builtin template has exactly one default builtin profile)

- [ ] **Step 6: Commit**

```bash
git add backend/app/seed/profiles/opcua_energy_meter_normal.json backend/tests/test_opcua_seed.py
git commit -m "feat: add built-in Normal Operation profile for OPC UA energy meter"
```

---

## Task 11: Wire OpcUaAdapter into the app

**Files:**
- Modify: `backend/app/main.py:32` (import), `:79-87` (register), `:100-112` (resume wiring)
- Modify: `backend/app/services/device_service.py:326-335` (RegisterInfo name/unit), insert opcua block before `:338`
- Test: `backend/tests/test_opcua_adapter.py`

- [ ] **Step 1: Write the failing integration test**

Append to `backend/tests/test_opcua_adapter.py`:

```python
class TestOpcUaDeviceWiring:
    async def test_started_device_appears_as_named_nodes(self, client):
        """Creating + starting an opcua device registers named nodes via device_service.

        Proves the glue: device_service builds RegisterInfo with name/unit and
        calls set_device_meta before add_device.
        """
        from asyncua import Client

        from app.protocols import protocol_manager
        from app.protocols.opcua_agent import OpcUaAdapter

        port = _free_port()
        adapter = OpcUaAdapter(host="127.0.0.1", port=port)
        protocol_manager.register_adapter("opcua", adapter)
        await protocol_manager.start_all()  # only opcua is registered in test process
        try:
            # Create an OPC UA template via the API
            tpl_resp = await client.post("/api/v1/templates", json={
                "name": "Wire-OPCUA",
                "protocol": "opcua",
                "registers": [
                    {"name": "voltage_l1", "address": 0, "function_code": 3,
                     "data_type": "float32", "byte_order": "big_endian",
                     "scale_factor": 1.0, "unit": "V", "sort_order": 0},
                    {"name": "active_power_total", "address": 1, "function_code": 3,
                     "data_type": "float32", "byte_order": "big_endian",
                     "scale_factor": 1.0, "unit": "W", "sort_order": 1},
                ],
            })
            assert tpl_resp.status_code == 201
            template_id = tpl_resp.json()["data"]["id"]

            dev_resp = await client.post("/api/v1/devices", json={
                "name": "MyOpcMeter",
                "template_id": template_id,
                "slave_id": 1,
                "port": 4840,
            })
            assert dev_resp.status_code == 201
            device_id = dev_resp.json()["data"]["id"]

            start_resp = await client.post(f"/api/v1/devices/{device_id}/start")
            assert start_resp.status_code == 200

            assert adapter.get_status()["device_count"] == 1

            url = f"opc.tcp://127.0.0.1:{port}/ghostmeter/server/"
            async with Client(url=url) as opc:
                ns = await opc.get_namespace_index(
                    "http://ghostmeter.local/opcua/"
                )
                gm = await opc.nodes.objects.get_child([f"{ns}:GhostMeter"])
                dev = await gm.get_child([f"{ns}:MyOpcMeter"])     # proves set_device_meta
                var = await dev.get_child([f"{ns}:voltage_l1"])    # proves RegisterInfo.name
                val = await var.read_value()
                assert isinstance(val, (int, float))
        finally:
            await protocol_manager.stop_all()
            protocol_manager._adapters.pop("opcua", None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestOpcUaDeviceWiring -v`
Expected: FAIL — device object is named `Device_1` (set_device_meta not wired), so `get_child([f"{ns}:MyOpcMeter"])` raises `BadNoMatch`

- [ ] **Step 3: Wire the resume path and registration in main.py**

In `backend/app/main.py`:

(a) After line 32 (`from app.protocols.snmp_agent import SnmpAdapter`), add:

```python
from app.protocols.opcua_agent import OpcUaAdapter
```

(b) After the SNMP registration block (line 84, `protocol_manager.register_adapter("snmp", snmp_adapter)`), and before `await protocol_manager.start_all()`, add:

```python

    # Register OPC UA adapter
    opcua_adapter = OpcUaAdapter(
        host=settings.OPCUA_HOST,
        port=settings.OPCUA_PORT,
        endpoint_path=settings.OPCUA_ENDPOINT_PATH,
        server_name=settings.OPCUA_SERVER_NAME,
        namespace_uri=settings.OPCUA_NAMESPACE_URI,
    )
    protocol_manager.register_adapter("opcua", opcua_adapter)
```

(c) In the resume loop, update the `RegisterInfo` construction (lines 100-109) to include `name`/`unit`, and call `set_device_meta` before `add_device`. Replace lines 100-112 with:

```python
                register_infos = [
                    RegisterInfo(
                        address=reg.address,
                        function_code=reg.function_code,
                        data_type=reg.data_type,
                        byte_order=reg.byte_order,
                        oid=reg.oid,
                        name=reg.name,
                        unit=reg.unit,
                    )
                    for reg in template.registers
                ]
                if template.protocol == "opcua":
                    opcua_adapter.set_device_meta(device.id, device.name)
                await protocol_manager.add_device(
                    template.protocol, device.id, device.slave_id, register_infos,
                )
```

- [ ] **Step 4: Wire device_service.start_device**

In `backend/app/services/device_service.py`:

(a) Update the `RegisterInfo` construction (lines 326-335) to include `name`/`unit`:

```python
    register_infos = [
        RegisterInfo(
            address=reg.address,
            function_code=reg.function_code,
            data_type=reg.data_type,
            byte_order=reg.byte_order,
            oid=reg.oid,
            name=reg.name,
            unit=reg.unit,
        )
        for reg in template.registers
    ]
```

(b) Immediately before the `if protocol_manager.is_running:` add_device block (line 337), insert the OPC UA pre-add hook:

```python
    # OPC UA needs the device display name before the Object node is created
    if template.protocol == "opcua" and protocol_manager.is_running:
        opcua_adapter = protocol_manager.get_adapter("opcua")
        if opcua_adapter is not None:
            opcua_adapter.set_device_meta(device.id, device.name)  # type: ignore[attr-defined]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/test_opcua_adapter.py::TestOpcUaDeviceWiring -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Run the full backend test suite**

Run: `cd backend && pytest -q`
Expected: PASS (all tests green, including the existing 229 + new OPC UA tests)

- [ ] **Step 7: Lint**

Run: `cd backend && ruff check app tests`
Expected: no errors (fix any import-order / line-length issues ruff flags)

- [ ] **Step 8: Commit**

```bash
git add backend/app/main.py backend/app/services/device_service.py backend/tests/test_opcua_adapter.py
git commit -m "feat: wire OpcUaAdapter into app startup, resume, and device lifecycle"
```

---

## Task 12: Frontend protocol option

**Files:**
- Modify: `frontend/src/pages/Templates/TemplateForm.tsx:10-11`

- [ ] **Step 1: Add the OPC UA option**

In `frontend/src/pages/Templates/TemplateForm.tsx`, the protocol options array (lines 10-11) currently is:

```tsx
  { value: "modbus_tcp", label: "Modbus TCP" },
  { value: "snmp", label: "SNMP" },
```

Add a third entry:

```tsx
  { value: "modbus_tcp", label: "Modbus TCP" },
  { value: "snmp", label: "SNMP" },
  { value: "opcua", label: "OPC UA" },
```

- [ ] **Step 2: Type-check the frontend**

Run: `cd frontend && npx tsc -b`
Expected: no type errors

- [ ] **Step 3: Build the frontend**

Run: `cd frontend && npm run build`
Expected: build succeeds

- [ ] **Step 4: Manual verification**

Run the app (`docker compose up -d` or `npm run dev`), open Templates → Create, and confirm the Protocol dropdown lists "OPC UA". Creating a template with protocol OPC UA and registers (name + data_type) saves successfully.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Templates/TemplateForm.tsx
git commit -m "feat: add OPC UA option to template protocol selector"
```

---

## Task 13: Docker Compose port + documentation

**Files:**
- Modify: `docker-compose.yml:31` (add port)
- Modify: `CHANGELOG.md`, `docs/development-log.md`, `docs/development-phases.md`

- [ ] **Step 1: Expose port 4840 in docker-compose**

In `docker-compose.yml`, in the `backend` service `ports:` list (after line 31, `- "161:10161/udp"`), add:

```yaml
      - "4840:4840"
```

- [ ] **Step 2: Update CHANGELOG.md**

Under `## [Unreleased]` → `### Added` in `CHANGELOG.md`, add:

```markdown
- OPC UA server adapter: exposes simulated devices as browsable Variable nodes (Read + Subscribe, Anonymous + SecurityPolicy None) via asyncua
- Built-in "Energy Meter (OPC UA)" template (11 registers) + Normal Operation profile
- OPC UA protocol option in template creation
- OPC UA server port 4840 exposed in docker-compose
```

- [ ] **Step 3: Update development-log.md**

Add a dated entry to `docs/development-log.md` summarizing:
- What: OPC UA server adapter (4th protocol).
- Key decisions: single shared asyncua server; **push** value-sync (vs SNMP pull) because asyncua subscriptions require real node value changes; Anonymous/None for MVP; `RegisterInfo` extended with `name`/`unit` because OPC UA nodes need meaningful browse names; device display name passed via `set_device_meta` before `add_device` (MQTT pattern).
- Out of scope: writable nodes, methods/alarms, certificates, OPC UA comm-layer faults, per-request stats.

- [ ] **Step 4: Update development-phases.md**

In `docs/development-phases.md`, add a new milestone after 8.8:

```markdown
### Milestone 8.9：OPC UA Server Adapter ✅
- [x] OpcUaAdapter extending ProtocolAdapter (asyncua, single shared server, Anonymous/None)
- [x] Push value-sync: simulation engine update_register → variable node; subscriptions fire automatically
- [x] RegisterInfo extended with name/unit; device name via set_device_meta pre-add hook
- [x] Built-in "Energy Meter (OPC UA)" template (11 registers) + Normal Operation profile
- [x] Frontend OPC UA protocol option; docker-compose port 4840
- [x] Integration tests: server lifecycle, node CRUD, typed value round-trip, subscription, device wiring
```

- [ ] **Step 5: Final full verification**

Run: `cd backend && pytest -q && ruff check app tests`
Then: `cd ../frontend && npx tsc -b && npm run build`
Expected: backend all green + lint clean; frontend type-checks and builds.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml CHANGELOG.md docs/development-log.md docs/development-phases.md
git commit -m "docs: document OPC UA adapter; expose port 4840 in docker-compose"
```

---

## Done

All tasks complete. The branch `feature/claude-opcua-adapter-20260603` now has:
- A working OPC UA server adapter (Read + Subscribe) registered in the protocol manager
- A built-in OPC UA template + profile, seeded at startup
- Frontend protocol option, docker port, and full docs
- Full test coverage (adapter lifecycle, node CRUD, typed round-trips, subscription, end-to-end device wiring)

Push the branch and open a PR to `dev` for human review (per CLAUDE.md — no direct merge).
