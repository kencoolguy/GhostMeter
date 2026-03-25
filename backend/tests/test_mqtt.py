"""Tests for MQTT broker settings and per-device publish config APIs."""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# === Helpers ===

async def _create_template(client: AsyncClient) -> dict:
    """Create a minimal template and return its data."""
    resp = await client.post("/api/v1/templates", json={
        "name": f"mqtt-test-{uuid.uuid4().hex[:6]}",
        "protocol": "modbus_tcp",
        "description": "Test template for MQTT",
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
            }
        ],
    })
    assert resp.status_code == 201
    return resp.json()["data"]


async def _create_device(client: AsyncClient, template_id: str) -> dict:
    """Create a device from a template and return its data."""
    resp = await client.post("/api/v1/devices", json={
        "name": f"mqtt-dev-{uuid.uuid4().hex[:6]}",
        "template_id": template_id,
        "slave_id": 1,
        "port": 502,
    })
    assert resp.status_code == 201
    return resp.json()["data"]


# === Broker Settings Tests ===


class TestBrokerSettings:
    """Tests for GET/PUT /api/v1/system/mqtt."""

    async def test_get_default_settings(self, client: AsyncClient):
        """GET returns defaults when no settings are saved."""
        resp = await client.get("/api/v1/system/mqtt")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["host"] == "localhost"
        assert data["port"] == 1883
        assert data["client_id"] == "ghostmeter"
        assert data["use_tls"] is False

    async def test_upsert_broker_settings(self, client: AsyncClient):
        """PUT creates settings on first call."""
        resp = await client.put("/api/v1/system/mqtt", json={
            "host": "broker.example.com",
            "port": 8883,
            "username": "user1",
            "password": "secret",
            "client_id": "my-meter",
            "use_tls": True,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["host"] == "broker.example.com"
        assert data["port"] == 8883
        assert data["username"] == "user1"
        assert data["password"] == "****"  # masked
        assert data["client_id"] == "my-meter"
        assert data["use_tls"] is True

    async def test_update_preserves_password_on_mask(self, client: AsyncClient):
        """PUT with '****' password keeps the existing password."""
        # Create initial settings
        await client.put("/api/v1/system/mqtt", json={
            "host": "broker.example.com",
            "port": 1883,
            "username": "user1",
            "password": "real-secret",
            "client_id": "ghostmeter",
            "use_tls": False,
        })

        # Update with masked password
        resp = await client.put("/api/v1/system/mqtt", json={
            "host": "broker2.example.com",
            "port": 1883,
            "username": "user1",
            "password": "****",
            "client_id": "ghostmeter",
            "use_tls": False,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["host"] == "broker2.example.com"
        # Password should still be masked (meaning it was preserved, not overwritten)
        assert resp.json()["data"]["password"] == "****"

    async def test_get_after_upsert(self, client: AsyncClient):
        """GET returns saved settings after PUT."""
        await client.put("/api/v1/system/mqtt", json={
            "host": "mqtt.local",
            "port": 1883,
            "username": "",
            "password": "",
            "client_id": "test-client",
            "use_tls": False,
        })

        resp = await client.get("/api/v1/system/mqtt")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["host"] == "mqtt.local"
        assert data["client_id"] == "test-client"


# === Broker Settings Validation ===


class TestBrokerSettingsValidation:
    """Tests for broker settings schema validation."""

    async def test_invalid_port_zero(self, client: AsyncClient):
        """Port 0 is rejected."""
        resp = await client.put("/api/v1/system/mqtt", json={
            "host": "localhost",
            "port": 0,
            "username": "",
            "password": "",
            "client_id": "ghostmeter",
            "use_tls": False,
        })
        assert resp.status_code == 422

    async def test_invalid_port_too_high(self, client: AsyncClient):
        """Port > 65535 is rejected."""
        resp = await client.put("/api/v1/system/mqtt", json={
            "host": "localhost",
            "port": 70000,
            "username": "",
            "password": "",
            "client_id": "ghostmeter",
            "use_tls": False,
        })
        assert resp.status_code == 422


# === Publish Config Tests ===


class TestPublishConfig:
    """Tests for per-device MQTT publish config CRUD."""

    async def test_get_no_config(self, client: AsyncClient):
        """GET returns null when no config exists for a device."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        resp = await client.get(f"/api/v1/system/devices/{device['id']}/mqtt")
        assert resp.status_code == 200
        assert resp.json()["data"] is None

    async def test_upsert_publish_config(self, client: AsyncClient):
        """PUT creates a publish config for a device."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        resp = await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt",
            json={
                "topic_template": "telemetry/{device_name}",
                "payload_mode": "batch",
                "publish_interval_seconds": 10,
                "qos": 1,
                "retain": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["device_id"] == device["id"]
        assert data["topic_template"] == "telemetry/{device_name}"
        assert data["payload_mode"] == "batch"
        assert data["publish_interval_seconds"] == 10
        assert data["qos"] == 1
        assert data["retain"] is True
        assert data["enabled"] is False  # default

    async def test_update_existing_config(self, client: AsyncClient):
        """PUT updates an existing publish config."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        # Create
        await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt",
            json={
                "topic_template": "telemetry/{device_name}",
                "payload_mode": "batch",
                "publish_interval_seconds": 5,
                "qos": 0,
                "retain": False,
            },
        )

        # Update
        resp = await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt",
            json={
                "topic_template": "data/{slave_id}",
                "payload_mode": "per_register",
                "publish_interval_seconds": 15,
                "qos": 2,
                "retain": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["topic_template"] == "data/{slave_id}"
        assert data["payload_mode"] == "per_register"
        assert data["publish_interval_seconds"] == 15
        assert data["qos"] == 2

    async def test_get_after_upsert(self, client: AsyncClient):
        """GET returns saved config after PUT."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt",
            json={
                "topic_template": "meter/{device_name}/data",
                "payload_mode": "batch",
                "publish_interval_seconds": 3,
                "qos": 0,
                "retain": False,
            },
        )

        resp = await client.get(f"/api/v1/system/devices/{device['id']}/mqtt")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["topic_template"] == "meter/{device_name}/data"
        assert data["publish_interval_seconds"] == 3

    async def test_delete_config(self, client: AsyncClient):
        """DELETE removes publish config."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        # Create
        await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt",
            json={
                "topic_template": "telemetry/{device_name}",
                "payload_mode": "batch",
                "publish_interval_seconds": 5,
                "qos": 0,
                "retain": False,
            },
        )

        # Delete
        resp = await client.delete(f"/api/v1/system/devices/{device['id']}/mqtt")
        assert resp.status_code == 200

        # Verify gone
        resp = await client.get(f"/api/v1/system/devices/{device['id']}/mqtt")
        assert resp.json()["data"] is None

    async def test_delete_nonexistent_config(self, client: AsyncClient):
        """DELETE on missing config returns 404."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        resp = await client.delete(f"/api/v1/system/devices/{device['id']}/mqtt")
        assert resp.status_code == 404


# === Publish Config Validation ===


class TestPublishConfigValidation:
    """Tests for publish config schema validation."""

    async def test_invalid_payload_mode(self, client: AsyncClient):
        """Invalid payload_mode is rejected."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        resp = await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt",
            json={
                "topic_template": "telemetry/{device_name}",
                "payload_mode": "invalid_mode",
                "publish_interval_seconds": 5,
                "qos": 0,
                "retain": False,
            },
        )
        assert resp.status_code == 422

    async def test_invalid_qos(self, client: AsyncClient):
        """QoS must be 0, 1, or 2."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        resp = await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt",
            json={
                "topic_template": "telemetry/{device_name}",
                "payload_mode": "batch",
                "publish_interval_seconds": 5,
                "qos": 3,
                "retain": False,
            },
        )
        assert resp.status_code == 422

    async def test_invalid_interval(self, client: AsyncClient):
        """Interval must be >= 1."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        resp = await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt",
            json={
                "topic_template": "telemetry/{device_name}",
                "payload_mode": "batch",
                "publish_interval_seconds": 0,
                "qos": 0,
                "retain": False,
            },
        )
        assert resp.status_code == 422


# === MQTT Adapter Unit Tests ===


class TestMqttAdapter:
    """Unit tests for MqttAdapter logic (no real broker needed)."""

    async def test_render_topic_batch(self):
        """Topic template renders device metadata correctly."""
        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        meta = {
            "device_name": "Meter-01",
            "slave_id": 5,
            "template_name": "Three-Phase Meter",
        }
        topic = adapter._render_topic("telemetry/{device_name}", meta)
        assert topic == "telemetry/Meter-01"

    async def test_render_topic_with_register(self):
        """Topic template renders register_name for per_register mode."""
        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        meta = {"device_name": "Meter-01", "slave_id": 5, "template_name": "TPM"}
        topic = adapter._render_topic(
            "devices/{slave_id}/{register_name}", meta, "voltage_l1",
        )
        assert topic == "devices/5/voltage_l1"

    async def test_render_topic_missing_meta(self):
        """Missing meta defaults to 'unknown' / 0."""
        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        topic = adapter._render_topic("data/{device_name}/{slave_id}", {})
        assert topic == "data/unknown/0"

    async def test_get_status_initial(self):
        """Initial status shows not connected."""
        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        status = adapter.get_status()
        assert status["connected"] is False
        assert status["available"] is False
        assert status["publishing_devices"] == 0

    async def test_set_device_meta(self):
        """set_device_meta stores metadata for topic rendering."""
        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        device_id = uuid.uuid4()
        adapter.set_device_meta(device_id, "Test-Device", 10, "Solar Inverter")
        assert adapter._device_meta[device_id]["device_name"] == "Test-Device"
        assert adapter._device_meta[device_id]["slave_id"] == 10

    async def test_start_publishing_fails_without_connection(self):
        """start_publishing raises when not connected."""
        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        with pytest.raises(RuntimeError, match="not connected"):
            await adapter.start_publishing(uuid.uuid4(), None)

    async def test_update_register_is_noop(self):
        """update_register is a no-op for MQTT (reads from SimulationEngine)."""
        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        # Should not raise
        await adapter.update_register(
            uuid.uuid4(), address=0, function_code=3,
            value=1.0, data_type="float32", byte_order="big",
        )
