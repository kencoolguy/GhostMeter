"""Tests for MQTT broker settings and publish configs in system export/import."""

import json

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

TEMPLATE_PAYLOAD = {
    "name": "Export-Test-Meter",
    "protocol": "modbus_tcp",
    "description": "Template for export test",
    "registers": [
        {
            "name": "voltage",
            "address": 0,
            "function_code": 4,
            "data_type": "float32",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "V",
            "description": "Voltage",
            "sort_order": 0,
        },
    ],
}


async def _setup_template_and_device(client: AsyncClient) -> tuple[dict, dict]:
    """Create a template and a device, return both."""
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    template = resp.json()["data"]

    resp = await client.post("/api/v1/devices", json={
        "name": "export-dev-1",
        "template_id": template["id"],
        "slave_id": 1,
        "port": 502,
    })
    assert resp.status_code == 201
    device = resp.json()["data"]
    return template, device


class TestMqttExport:
    """Tests for MQTT data in system export."""

    async def test_export_without_mqtt(self, client: AsyncClient):
        """Export without MQTT settings returns null / empty."""
        resp = await client.get("/api/v1/system/export")
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data["mqtt_broker_settings"] is None
        assert data["mqtt_publish_configs"] == []

    async def test_export_includes_broker_settings(self, client: AsyncClient):
        """Export includes MQTT broker settings when configured."""
        await client.put("/api/v1/system/mqtt", json={
            "host": "mqtt.example.com",
            "port": 8883,
            "username": "admin",
            "password": "secret123",
            "client_id": "export-test",
            "use_tls": True,
        })

        resp = await client.get("/api/v1/system/export")
        data = json.loads(resp.content)
        broker = data["mqtt_broker_settings"]
        assert broker is not None
        assert broker["host"] == "mqtt.example.com"
        assert broker["port"] == 8883
        assert broker["username"] == "admin"
        assert broker["password"] == "secret123"  # not masked in export
        assert broker["use_tls"] is True

    async def test_export_includes_publish_configs(self, client: AsyncClient):
        """Export includes per-device MQTT publish configs."""
        _, device = await _setup_template_and_device(client)

        await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt",
            json={
                "topic_template": "meters/{device_name}/data",
                "payload_mode": "batch",
                "publish_interval_seconds": 10,
                "qos": 1,
                "retain": True,
            },
        )

        resp = await client.get("/api/v1/system/export")
        data = json.loads(resp.content)
        configs = data["mqtt_publish_configs"]
        assert len(configs) == 1
        assert configs[0]["device_name"] == "export-dev-1"
        assert configs[0]["topic_template"] == "meters/{device_name}/data"
        assert configs[0]["qos"] == 1


class TestMqttImport:
    """Tests for MQTT data in system import."""

    async def test_import_broker_settings(self, client: AsyncClient):
        """Import creates MQTT broker settings."""
        resp = await client.post("/api/v1/system/import", json={
            "version": "1.0",
            "templates": [],
            "devices": [],
            "mqtt_broker_settings": {
                "host": "imported-broker.local",
                "port": 1883,
                "username": "user1",
                "password": "pass1",
                "client_id": "imported",
                "use_tls": False,
            },
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["mqtt_broker_settings_set"] is True

        # Verify via GET
        resp = await client.get("/api/v1/system/mqtt")
        data = resp.json()["data"]
        assert data["host"] == "imported-broker.local"
        assert data["client_id"] == "imported"

    async def test_import_updates_existing_broker(self, client: AsyncClient):
        """Import updates existing MQTT broker settings."""
        # Create initial
        await client.put("/api/v1/system/mqtt", json={
            "host": "old-broker.local",
            "port": 1883,
            "username": "",
            "password": "",
            "client_id": "ghostmeter",
            "use_tls": False,
        })

        # Import new
        resp = await client.post("/api/v1/system/import", json={
            "version": "1.0",
            "templates": [],
            "devices": [],
            "mqtt_broker_settings": {
                "host": "new-broker.local",
                "port": 8883,
                "username": "admin",
                "password": "newsecret",
                "client_id": "updated",
                "use_tls": True,
            },
        })
        assert resp.status_code == 200

        resp = await client.get("/api/v1/system/mqtt")
        data = resp.json()["data"]
        assert data["host"] == "new-broker.local"
        assert data["port"] == 8883
        assert data["use_tls"] is True

    async def test_import_publish_configs(self, client: AsyncClient):
        """Import creates per-device MQTT publish configs."""
        resp = await client.post("/api/v1/system/import", json={
            "version": "1.0",
            "templates": [{**TEMPLATE_PAYLOAD, "is_builtin": False}],
            "devices": [{
                "name": "import-dev-1",
                "template_name": "Export-Test-Meter",
                "slave_id": 10,
                "port": 502,
            }],
            "mqtt_publish_configs": [{
                "device_name": "import-dev-1",
                "topic_template": "data/{slave_id}",
                "payload_mode": "per_register",
                "publish_interval_seconds": 15,
                "qos": 2,
                "retain": False,
                "enabled": False,
            }],
        })
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert result["mqtt_publish_configs_set"] == 1

    async def test_import_without_mqtt_is_backward_compatible(self, client: AsyncClient):
        """Import without mqtt fields works (backward compatibility)."""
        resp = await client.post("/api/v1/system/import", json={
            "version": "1.0",
            "templates": [],
            "devices": [],
        })
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert result["mqtt_broker_settings_set"] is False
        assert result["mqtt_publish_configs_set"] == 0

    async def test_roundtrip_export_import_with_mqtt(self, client: AsyncClient):
        """Full roundtrip: setup MQTT → export → wipe → import → verify."""
        _, device = await _setup_template_and_device(client)

        # Setup broker
        await client.put("/api/v1/system/mqtt", json={
            "host": "roundtrip.local",
            "port": 1883,
            "username": "rt",
            "password": "rtpass",
            "client_id": "roundtrip",
            "use_tls": False,
        })

        # Setup publish config
        await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt",
            json={
                "topic_template": "rt/{device_name}",
                "payload_mode": "batch",
                "publish_interval_seconds": 5,
                "qos": 0,
                "retain": False,
            },
        )

        # Export
        resp = await client.get("/api/v1/system/export")
        exported = json.loads(resp.content)

        assert exported["mqtt_broker_settings"]["host"] == "roundtrip.local"
        assert len(exported["mqtt_publish_configs"]) == 1

        # Import into clean state (the import endpoint handles upsert)
        resp = await client.post("/api/v1/system/import", json=exported)
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert result["mqtt_broker_settings_set"] is True
        assert result["mqtt_publish_configs_set"] == 1
