"""Tests for SNMP adapter OID mapping, conflict detection, and template CRUD with OID."""

import json
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

SNMP_TEMPLATE_PAYLOAD = {
    "name": "Test-UPS-SNMP",
    "protocol": "snmp",
    "description": "Test SNMP template",
    "registers": [
        {
            "name": "input_voltage",
            "address": 0,
            "function_code": 4,
            "data_type": "float32",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "V",
            "description": "Input Voltage",
            "sort_order": 0,
            "oid": "1.3.6.1.2.1.33.1.3.3.1.3.1",
        },
        {
            "name": "battery_status",
            "address": 1,
            "function_code": 4,
            "data_type": "int16",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": None,
            "description": "Battery Status",
            "sort_order": 1,
            "oid": "1.3.6.1.2.1.33.1.2.1.0",
        },
    ],
}


async def _create_snmp_template(client: AsyncClient) -> dict:
    resp = await client.post("/api/v1/templates", json=SNMP_TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["data"]


async def _create_device(
    client: AsyncClient, template_id: str, slave_id: int,
) -> dict:
    resp = await client.post("/api/v1/devices", json={
        "name": f"ups-{slave_id}",
        "template_id": template_id,
        "slave_id": slave_id,
        "port": 502,
    })
    assert resp.status_code == 201
    return resp.json()["data"]


class TestSnmpTemplate:
    """Tests for SNMP template CRUD with OID field."""

    async def test_create_snmp_template_with_oid(self, client: AsyncClient):
        """Create a template with protocol=snmp and OID fields."""
        template = await _create_snmp_template(client)
        assert template["protocol"] == "snmp"
        assert len(template["registers"]) == 2
        assert template["registers"][0]["oid"] == "1.3.6.1.2.1.33.1.3.3.1.3.1"
        assert template["registers"][1]["oid"] == "1.3.6.1.2.1.33.1.2.1.0"

    async def test_modbus_template_has_null_oid(self, client: AsyncClient):
        """Modbus templates have null OID by default."""
        resp = await client.post("/api/v1/templates", json={
            "name": "Modbus-OID-Test",
            "protocol": "modbus_tcp",
            "registers": [
                {
                    "name": "voltage",
                    "address": 0,
                    "function_code": 4,
                    "data_type": "float32",
                    "byte_order": "big_endian",
                    "scale_factor": 1.0,
                    "sort_order": 0,
                },
            ],
        })
        assert resp.status_code == 201
        reg = resp.json()["data"]["registers"][0]
        assert reg["oid"] is None

    async def test_device_registers_include_oid(self, client: AsyncClient):
        """Device register detail includes OID field."""
        template = await _create_snmp_template(client)
        device = await _create_device(client, template["id"], 1)

        resp = await client.get(f"/api/v1/devices/{device['id']}/registers")
        assert resp.status_code == 200
        regs = resp.json()["data"]
        assert regs[0]["oid"] == "1.3.6.1.2.1.33.1.3.3.1.3.1"


class TestSnmpAdapterUnit:
    """Unit tests for SnmpAdapter logic (no real SNMP engine)."""

    async def test_initial_status(self):
        from app.protocols.snmp_agent import SnmpAdapter

        adapter = SnmpAdapter(port=10161, community="public")
        status = adapter.get_status()
        assert status["running"] is False
        assert status["registered_oids"] == 0
        assert status["registered_devices"] == 0

    async def test_add_remove_device(self):
        """Add then remove device clears OID mappings."""
        from app.protocols.base import RegisterInfo
        from app.protocols.snmp_agent import SnmpAdapter

        adapter = SnmpAdapter()
        device_id = uuid.uuid4()
        regs = [
            RegisterInfo(0, 4, "float32", "big_endian", oid="1.3.6.1.2.1.33.1.3.3.1.3.1"),
            RegisterInfo(1, 4, "int16", "big_endian", oid="1.3.6.1.2.1.33.1.2.1.0"),
        ]

        await adapter.add_device(device_id, 1, regs)
        assert adapter.get_status()["registered_oids"] == 2
        assert adapter.get_status()["registered_devices"] == 1

        await adapter.remove_device(device_id)
        assert adapter.get_status()["registered_oids"] == 0
        assert adapter.get_status()["registered_devices"] == 0

    async def test_oid_conflict_detection(self):
        """Adding two devices with same OIDs raises ConflictException."""
        from app.exceptions import ConflictException
        from app.protocols.base import RegisterInfo
        from app.protocols.snmp_agent import SnmpAdapter

        adapter = SnmpAdapter()
        device1 = uuid.uuid4()
        device2 = uuid.uuid4()
        regs = [
            RegisterInfo(0, 4, "float32", "big_endian", oid="1.3.6.1.2.1.33.1.2.1.0"),
        ]

        await adapter.add_device(device1, 1, regs)

        with pytest.raises(ConflictException, match="OID.*already registered"):
            await adapter.add_device(device2, 2, regs)

    async def test_no_conflict_same_device(self):
        """Re-adding same device doesn't conflict with itself."""
        from app.protocols.base import RegisterInfo
        from app.protocols.snmp_agent import SnmpAdapter

        adapter = SnmpAdapter()
        device_id = uuid.uuid4()
        regs = [
            RegisterInfo(0, 4, "float32", "big_endian", oid="1.3.6.1.2.1.33.1.2.1.0"),
        ]

        await adapter.add_device(device_id, 1, regs)
        # Re-add same device should not raise
        await adapter.add_device(device_id, 1, regs)

    async def test_sorted_oids(self):
        """OIDs are sorted by numeric components."""
        from app.protocols.base import RegisterInfo
        from app.protocols.snmp_agent import SnmpAdapter

        adapter = SnmpAdapter()
        device_id = uuid.uuid4()
        regs = [
            RegisterInfo(0, 4, "float32", "big_endian", oid="1.3.6.1.2.1.33.1.4.4.1.2.1"),
            RegisterInfo(1, 4, "int16", "big_endian", oid="1.3.6.1.2.1.33.1.2.1.0"),
        ]
        await adapter.add_device(device_id, 1, regs)
        sorted_oids = adapter.get_sorted_oids()
        assert sorted_oids[0] == "1.3.6.1.2.1.33.1.2.1.0"
        assert sorted_oids[1] == "1.3.6.1.2.1.33.1.4.4.1.2.1"

    async def test_set_register_names(self):
        """set_register_names updates OID→name mapping."""
        from app.protocols.base import RegisterInfo
        from app.protocols.snmp_agent import SnmpAdapter

        adapter = SnmpAdapter()
        device_id = uuid.uuid4()
        regs = [
            RegisterInfo(0, 4, "float32", "big_endian", oid="1.3.6.1.2.1.33.1.2.1.0"),
        ]
        await adapter.add_device(device_id, 1, regs)

        adapter.set_register_names(device_id, {
            "1.3.6.1.2.1.33.1.2.1.0": "battery_status",
        })

        # Verify the mapping was updated
        entry = adapter._oid_map.get("1.3.6.1.2.1.33.1.2.1.0")
        assert entry is not None
        assert entry[1] == "battery_status"

    async def test_to_snmp_value_int(self):
        """Integer types convert to Integer32."""
        from pysnmp.proto.rfc1902 import Integer32
        from app.protocols.snmp_agent import SnmpAdapter

        val = SnmpAdapter.to_snmp_value(42.0, "int32")
        assert isinstance(val, Integer32)
        assert int(val) == 42

    async def test_to_snmp_value_uint(self):
        """Unsigned types convert to Gauge32."""
        from pysnmp.proto.rfc1902 import Gauge32
        from app.protocols.snmp_agent import SnmpAdapter

        val = SnmpAdapter.to_snmp_value(1000.0, "uint32")
        assert isinstance(val, Gauge32)
        assert int(val) == 1000

    async def test_to_snmp_value_float(self):
        """Float types convert to string representation."""
        from app.protocols.snmp_agent import SnmpAdapter

        val = SnmpAdapter.to_snmp_value(230.5678, "float32")
        assert val == "230.5678"

    async def test_update_register_is_noop(self):
        from app.protocols.snmp_agent import SnmpAdapter

        adapter = SnmpAdapter()
        await adapter.update_register(
            uuid.uuid4(), 0, 4, 1.0, "float32", "big_endian",
        )

    async def test_registers_without_oid_are_skipped(self):
        """Registers with oid=None are not added to OID map."""
        from app.protocols.base import RegisterInfo
        from app.protocols.snmp_agent import SnmpAdapter

        adapter = SnmpAdapter()
        device_id = uuid.uuid4()
        regs = [
            RegisterInfo(0, 3, "float32", "big_endian"),  # no oid
            RegisterInfo(1, 4, "int16", "big_endian", oid="1.3.6.1.2.1.33.1.2.1.0"),
        ]
        await adapter.add_device(device_id, 1, regs)
        assert adapter.get_status()["registered_oids"] == 1


class TestSnmpSeedValidation:
    """Validate seed JSON files are well-formed."""

    def test_ups_template_seed_valid(self):
        seed_file = Path(__file__).parent.parent / "app" / "seed" / "snmp_ups.json"
        data = json.loads(seed_file.read_text())
        assert data["name"] == "UPS (SNMP)"
        assert data["protocol"] == "snmp"
        assert len(data["registers"]) == 10
        for reg in data["registers"]:
            assert "oid" in reg
            assert reg["oid"].startswith("1.3.6.1")
            assert reg["function_code"] == 4

    def test_ups_profile_seed_valid(self):
        seed_file = (
            Path(__file__).parent.parent
            / "app"
            / "seed"
            / "profiles"
            / "snmp_ups_normal.json"
        )
        data = json.loads(seed_file.read_text())
        assert data["template_name"] == "UPS (SNMP)"
        assert data["name"] == "Normal Operation"
        assert data["is_default"] is True
        assert len(data["configs"]) == 10
