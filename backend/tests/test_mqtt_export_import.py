"""Tests for MQTT brokers and publish configs in system export/import."""

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


def _broker_payload(name: str, host: str = "mqtt.example.com", **overrides) -> dict:
    payload = {
        "name": name,
        "host": host,
        "port": 1883,
        "username": "admin",
        "password": "secret123",
        "client_id": "export-test",
        "use_tls": False,
    }
    payload.update(overrides)
    return payload


async def _create_broker(client: AsyncClient, name: str, **overrides) -> dict:
    resp = await client.post(
        "/api/v1/system/mqtt/brokers", json=_broker_payload(name, **overrides),
    )
    assert resp.status_code == 201
    return resp.json()["data"]


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


async def _put_config(
    client: AsyncClient, device_id: str, broker_id: str, **overrides,
) -> None:
    payload = {
        "topic_template": "meters/{device_name}/data",
        "payload_mode": "batch",
        "publish_interval_seconds": 10,
        "qos": 1,
        "retain": True,
    }
    payload.update(overrides)
    resp = await client.put(
        f"/api/v1/system/devices/{device_id}/mqtt/{broker_id}", json=payload,
    )
    assert resp.status_code == 200


class TestMqttExport:
    """Tests for MQTT data in system export."""

    async def test_export_without_mqtt(self, client: AsyncClient):
        """Export without MQTT settings returns empty lists."""
        resp = await client.get("/api/v1/system/export")
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data["mqtt_brokers"] == []
        assert data["mqtt_publish_configs"] == []

    async def test_export_includes_brokers(self, client: AsyncClient):
        """Export includes every broker with its real (unmasked) password."""
        await _create_broker(client, "emqx-a", port=8883, use_tls=True)
        await _create_broker(client, "emqx-b", host="other.example.com")

        resp = await client.get("/api/v1/system/export")
        data = json.loads(resp.content)
        brokers = {b["name"]: b for b in data["mqtt_brokers"]}
        assert set(brokers) == {"emqx-a", "emqx-b"}
        assert brokers["emqx-a"]["port"] == 8883
        assert brokers["emqx-a"]["password"] == "secret123"  # not masked in export
        assert brokers["emqx-a"]["use_tls"] is True
        assert brokers["emqx-b"]["host"] == "other.example.com"

    async def test_export_includes_publish_configs(self, client: AsyncClient):
        """Export includes per-(device, broker) publish configs by name."""
        broker = await _create_broker(client, "cfg-broker")
        _, device = await _setup_template_and_device(client)
        await _put_config(client, device["id"], broker["id"])

        resp = await client.get("/api/v1/system/export")
        data = json.loads(resp.content)
        configs = data["mqtt_publish_configs"]
        assert len(configs) == 1
        assert configs[0]["device_name"] == "export-dev-1"
        assert configs[0]["broker_name"] == "cfg-broker"
        assert configs[0]["topic_template"] == "meters/{device_name}/data"
        assert configs[0]["qos"] == 1


class TestMqttImport:
    """Tests for MQTT data in system import."""

    async def test_import_brokers(self, client: AsyncClient):
        """Import creates MQTT brokers from the mqtt_brokers list."""
        resp = await client.post("/api/v1/system/import", json={
            "version": "1.0",
            "templates": [],
            "devices": [],
            "mqtt_brokers": [
                _broker_payload("imported-a", host="imported-a.local"),
                _broker_payload("imported-b", host="imported-b.local"),
            ],
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["mqtt_brokers_set"] == 2

        resp = await client.get("/api/v1/system/mqtt/brokers")
        brokers = {b["name"]: b for b in resp.json()["data"]}
        assert set(brokers) == {"imported-a", "imported-b"}
        assert brokers["imported-a"]["host"] == "imported-a.local"

    async def test_import_updates_existing_broker_by_name(self, client: AsyncClient):
        """Import upserts brokers by name; masked password keeps the stored one."""
        await _create_broker(client, "shared", host="old.local", password="original")

        resp = await client.post("/api/v1/system/import", json={
            "version": "1.0",
            "templates": [],
            "devices": [],
            "mqtt_brokers": [
                _broker_payload("shared", host="new.local", password="****"),
            ],
        })
        assert resp.status_code == 200

        resp = await client.get("/api/v1/system/mqtt/brokers")
        brokers = resp.json()["data"]
        assert len(brokers) == 1
        assert brokers[0]["host"] == "new.local"

        # Export exposes the real password — it must still be the original
        resp = await client.get("/api/v1/system/export")
        exported = json.loads(resp.content)
        assert exported["mqtt_brokers"][0]["password"] == "original"

    async def test_import_publish_configs(self, client: AsyncClient):
        """Import attaches publish configs to brokers by name."""
        resp = await client.post("/api/v1/system/import", json={
            "version": "1.0",
            "templates": [{**TEMPLATE_PAYLOAD, "is_builtin": False}],
            "devices": [{
                "name": "import-dev-1",
                "template_name": "Export-Test-Meter",
                "slave_id": 10,
                "port": 502,
            }],
            "mqtt_brokers": [_broker_payload("target-broker")],
            "mqtt_publish_configs": [{
                "device_name": "import-dev-1",
                "broker_name": "target-broker",
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
        assert result["mqtt_brokers_set"] == 1
        assert result["mqtt_publish_configs_set"] == 1

    async def test_import_config_with_unknown_broker_is_skipped(
        self, client: AsyncClient,
    ):
        """A config referencing an unknown broker name is skipped, not fatal."""
        resp = await client.post("/api/v1/system/import", json={
            "version": "1.0",
            "templates": [{**TEMPLATE_PAYLOAD, "is_builtin": False}],
            "devices": [{
                "name": "import-dev-2",
                "template_name": "Export-Test-Meter",
                "slave_id": 11,
                "port": 502,
            }],
            "mqtt_publish_configs": [{
                "device_name": "import-dev-2",
                "broker_name": "does-not-exist",
                "topic_template": "data/{slave_id}",
                "payload_mode": "batch",
                "publish_interval_seconds": 5,
                "qos": 0,
                "retain": False,
                "enabled": False,
            }],
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["mqtt_publish_configs_set"] == 0

    async def test_import_legacy_single_broker_shape(self, client: AsyncClient):
        """Legacy exports (single mqtt_broker_settings object) become 'default'."""
        resp = await client.post("/api/v1/system/import", json={
            "version": "1.0",
            "templates": [{**TEMPLATE_PAYLOAD, "is_builtin": False}],
            "devices": [{
                "name": "legacy-dev",
                "template_name": "Export-Test-Meter",
                "slave_id": 12,
                "port": 502,
            }],
            "mqtt_broker_settings": {
                "host": "legacy-broker.local",
                "port": 1883,
                "username": "user1",
                "password": "pass1",
                "client_id": "legacy",
                "use_tls": False,
            },
            # Legacy configs carry no broker_name — they attach to 'default'
            "mqtt_publish_configs": [{
                "device_name": "legacy-dev",
                "topic_template": "legacy/{device_name}",
                "payload_mode": "batch",
                "publish_interval_seconds": 5,
                "qos": 0,
                "retain": False,
                "enabled": True,
            }],
        })
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert result["mqtt_brokers_set"] == 1
        assert result["mqtt_publish_configs_set"] == 1

        resp = await client.get("/api/v1/system/mqtt/brokers")
        brokers = resp.json()["data"]
        assert len(brokers) == 1
        assert brokers[0]["name"] == "default"
        assert brokers[0]["host"] == "legacy-broker.local"

    async def test_import_without_mqtt_is_backward_compatible(self, client: AsyncClient):
        """Import without mqtt fields works (backward compatibility)."""
        resp = await client.post("/api/v1/system/import", json={
            "version": "1.0",
            "templates": [],
            "devices": [],
        })
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert result["mqtt_brokers_set"] == 0
        assert result["mqtt_publish_configs_set"] == 0

    async def test_roundtrip_export_import_with_mqtt(self, client: AsyncClient):
        """Full roundtrip: two brokers, one device publishing to both."""
        b1 = await _create_broker(client, "rt-a", host="rt-a.local")
        b2 = await _create_broker(client, "rt-b", host="rt-b.local")
        _, device = await _setup_template_and_device(client)
        await _put_config(client, device["id"], b1["id"], topic_template="rt/{device_name}")
        await _put_config(client, device["id"], b2["id"], topic_template="rt2/{device_name}")

        resp = await client.get("/api/v1/system/export")
        exported = json.loads(resp.content)
        assert {b["name"] for b in exported["mqtt_brokers"]} == {"rt-a", "rt-b"}
        assert len(exported["mqtt_publish_configs"]) == 2

        # Import into the same instance (upsert path)
        resp = await client.post("/api/v1/system/import", json=exported)
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert result["mqtt_brokers_set"] == 2
        assert result["mqtt_publish_configs_set"] == 2

        # Still exactly one config per (device, broker) pair
        resp = await client.get(f"/api/v1/system/devices/{device['id']}/mqtt")
        configs = resp.json()["data"]
        assert [c["broker_name"] for c in configs] == ["rt-a", "rt-b"]
        assert configs[0]["topic_template"] == "rt/{device_name}"
