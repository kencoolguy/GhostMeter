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


# === Broker CRUD Tests ===


def _broker_payload(name: str = "broker-a", **overrides) -> dict:
    payload = {
        "name": name,
        "host": "broker.example.com",
        "port": 1883,
        "username": "user1",
        "password": "secret",
        "client_id": "my-meter",
        "use_tls": False,
    }
    payload.update(overrides)
    return payload


async def _create_broker(client: AsyncClient, name: str = "broker-a", **overrides) -> dict:
    resp = await client.post("/api/v1/system/mqtt/brokers", json=_broker_payload(name, **overrides))
    assert resp.status_code == 201
    return resp.json()["data"]


class TestBrokerCrud:
    """Tests for /api/v1/system/mqtt/brokers CRUD."""

    async def test_list_empty(self, client: AsyncClient):
        """GET returns an empty list when no brokers are configured."""
        resp = await client.get("/api/v1/system/mqtt/brokers")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_create_broker(self, client: AsyncClient):
        """POST creates a broker and masks the password."""
        data = await _create_broker(client, "emqx-prod", port=8883, use_tls=True)
        assert data["name"] == "emqx-prod"
        assert data["host"] == "broker.example.com"
        assert data["port"] == 8883
        assert data["password"] == "****"
        assert data["use_tls"] is True
        assert "id" in data
        assert data["connected"] is False  # no real broker in tests

    async def test_list_after_create(self, client: AsyncClient):
        """GET lists created brokers."""
        await _create_broker(client, "b-one")
        await _create_broker(client, "b-two", host="other.example.com")
        resp = await client.get("/api/v1/system/mqtt/brokers")
        names = [b["name"] for b in resp.json()["data"]]
        assert names == ["b-one", "b-two"]  # ordered by name

    async def test_create_duplicate_name(self, client: AsyncClient):
        """POST with an existing name is rejected."""
        await _create_broker(client, "dup")
        resp = await client.post("/api/v1/system/mqtt/brokers", json=_broker_payload("dup"))
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "DUPLICATE_NAME"

    async def test_update_broker(self, client: AsyncClient):
        """PUT updates fields on an existing broker."""
        broker = await _create_broker(client, "upd")
        resp = await client.put(
            f"/api/v1/system/mqtt/brokers/{broker['id']}",
            json=_broker_payload("upd-renamed", host="new-host.example.com"),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "upd-renamed"
        assert data["host"] == "new-host.example.com"

    async def test_update_unknown_broker(self, client: AsyncClient):
        """PUT on a missing broker id returns 404."""
        resp = await client.put(
            f"/api/v1/system/mqtt/brokers/{uuid.uuid4()}", json=_broker_payload("x"),
        )
        assert resp.status_code == 404

    async def test_update_duplicate_name(self, client: AsyncClient):
        """PUT renaming onto another broker's name is rejected."""
        await _create_broker(client, "first")
        broker = await _create_broker(client, "second")
        resp = await client.put(
            f"/api/v1/system/mqtt/brokers/{broker['id']}", json=_broker_payload("first"),
        )
        assert resp.status_code == 409

    async def test_delete_broker(self, client: AsyncClient):
        """DELETE removes an unreferenced broker."""
        broker = await _create_broker(client, "gone")
        resp = await client.delete(f"/api/v1/system/mqtt/brokers/{broker['id']}")
        assert resp.status_code == 200
        resp = await client.get("/api/v1/system/mqtt/brokers")
        assert resp.json()["data"] == []

    async def test_delete_unknown_broker(self, client: AsyncClient):
        """DELETE on a missing broker id returns 404."""
        resp = await client.delete(f"/api/v1/system/mqtt/brokers/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_delete_broker_with_configs(self, client: AsyncClient):
        """DELETE is refused while publish configs still reference the broker."""
        broker = await _create_broker(client, "referenced")
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        import app.database as db
        from app.models.mqtt import MqttPublishConfig

        async with db.async_session_factory() as session:
            session.add(MqttPublishConfig(
                device_id=uuid.UUID(device["id"]),
                broker_id=uuid.UUID(broker["id"]),
            ))
            await session.commit()

        resp = await client.delete(f"/api/v1/system/mqtt/brokers/{broker['id']}")
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "BROKER_IN_USE"

    async def test_legacy_single_settings_endpoints_removed(self, client: AsyncClient):
        """The old single-settings GET/PUT /system/mqtt endpoints are gone."""
        resp = await client.get("/api/v1/system/mqtt")
        assert resp.status_code in (404, 405)
        resp = await client.put("/api/v1/system/mqtt", json=_broker_payload())
        assert resp.status_code in (404, 405)


class TestBrokerValidation:
    """Tests for broker schema validation."""

    async def test_invalid_port_zero(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/system/mqtt/brokers", json=_broker_payload(port=0),
        )
        assert resp.status_code == 422

    async def test_invalid_port_too_high(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/system/mqtt/brokers", json=_broker_payload(port=70000),
        )
        assert resp.status_code == 422

    async def test_empty_name(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/system/mqtt/brokers", json=_broker_payload(name=""),
        )
        assert resp.status_code == 422


# === Publish Config Tests ===


class TestPublishConfig:
    """Tests for per-(device, broker) MQTT publish config CRUD."""

    async def test_list_empty(self, client: AsyncClient):
        """GET returns an empty list when a device has no configs."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        resp = await client.get(f"/api/v1/system/devices/{device['id']}/mqtt")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_upsert_publish_config(self, client: AsyncClient):
        """PUT creates a publish config for a (device, broker) pair."""
        broker = await _create_broker(client, "cfg-broker")
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        resp = await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt/{broker['id']}",
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
        assert data["broker_id"] == broker["id"]
        assert data["broker_name"] == "cfg-broker"
        assert data["topic_template"] == "telemetry/{device_name}"
        assert data["publish_interval_seconds"] == 10
        assert data["qos"] == 1
        assert data["retain"] is True
        assert data["enabled"] is False  # default

    async def test_upsert_unknown_broker(self, client: AsyncClient):
        """PUT against a nonexistent broker returns 404."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        resp = await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt/{uuid.uuid4()}",
            json={
                "topic_template": "telemetry/{device_name}",
                "payload_mode": "batch",
                "publish_interval_seconds": 5,
                "qos": 0,
                "retain": False,
            },
        )
        assert resp.status_code == 404

    async def test_update_existing_config(self, client: AsyncClient):
        """PUT updates an existing (device, broker) config in place."""
        broker = await _create_broker(client, "upd-broker")
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        await _put_publish_config(client, device["id"], broker["id"])
        resp = await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt/{broker['id']}",
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

        # Still exactly one config for this pair
        resp = await client.get(f"/api/v1/system/devices/{device['id']}/mqtt")
        assert len(resp.json()["data"]) == 1

    async def test_one_device_two_brokers(self, client: AsyncClient):
        """A device can hold independent configs for two brokers."""
        b1 = await _create_broker(client, "alpha")
        b2 = await _create_broker(client, "beta")
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        await _put_publish_config(client, device["id"], b1["id"])
        resp = await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt/{b2['id']}",
            json={
                "topic_template": "other/{device_name}",
                "payload_mode": "per_register",
                "publish_interval_seconds": 30,
                "qos": 1,
                "retain": False,
            },
        )
        assert resp.status_code == 200

        resp = await client.get(f"/api/v1/system/devices/{device['id']}/mqtt")
        data = resp.json()["data"]
        assert [c["broker_name"] for c in data] == ["alpha", "beta"]
        assert data[0]["topic_template"] == "gm/{device_name}"
        assert data[1]["topic_template"] == "other/{device_name}"

    async def test_delete_config(self, client: AsyncClient):
        """DELETE removes one (device, broker) config."""
        b1 = await _create_broker(client, "keep")
        b2 = await _create_broker(client, "remove")
        template = await _create_template(client)
        device = await _create_device(client, template["id"])
        await _put_publish_config(client, device["id"], b1["id"])
        await _put_publish_config(client, device["id"], b2["id"])

        resp = await client.delete(
            f"/api/v1/system/devices/{device['id']}/mqtt/{b2['id']}"
        )
        assert resp.status_code == 200

        resp = await client.get(f"/api/v1/system/devices/{device['id']}/mqtt")
        assert [c["broker_name"] for c in resp.json()["data"]] == ["keep"]

    async def test_delete_nonexistent_config(self, client: AsyncClient):
        """DELETE on missing config returns 404."""
        broker = await _create_broker(client, "no-cfg")
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        resp = await client.delete(
            f"/api/v1/system/devices/{device['id']}/mqtt/{broker['id']}"
        )
        assert resp.status_code == 404


# === Publish Config Validation ===


class TestPublishConfigValidation:
    """Tests for publish config schema validation."""

    async def _put(self, client: AsyncClient, payload: dict):
        broker = await _create_broker(client, f"val-{uuid.uuid4().hex[:6]}")
        template = await _create_template(client)
        device = await _create_device(client, template["id"])
        return await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt/{broker['id']}",
            json=payload,
        )

    async def test_invalid_payload_mode(self, client: AsyncClient):
        """Invalid payload_mode is rejected."""
        resp = await self._put(client, {
            "topic_template": "telemetry/{device_name}",
            "payload_mode": "invalid_mode",
            "publish_interval_seconds": 5,
            "qos": 0,
            "retain": False,
        })
        assert resp.status_code == 422

    async def test_invalid_qos(self, client: AsyncClient):
        """QoS must be 0, 1, or 2."""
        resp = await self._put(client, {
            "topic_template": "telemetry/{device_name}",
            "payload_mode": "batch",
            "publish_interval_seconds": 5,
            "qos": 3,
            "retain": False,
        })
        assert resp.status_code == 422

    async def test_invalid_interval(self, client: AsyncClient):
        """Interval must be >= 1."""
        resp = await self._put(client, {
            "topic_template": "telemetry/{device_name}",
            "payload_mode": "batch",
            "publish_interval_seconds": 0,
            "qos": 0,
            "retain": False,
        })
        assert resp.status_code == 422


# === MQTT Adapter Unit Tests ===


def _connect_fake_broker(adapter, name: str = "test-broker"):
    """Register a fake connected broker on the adapter; returns its id."""
    broker_id = uuid.uuid4()
    adapter._clients[broker_id] = object()  # never used by these tests
    adapter._broker_info[broker_id] = {
        "name": name, "host": "fake", "port": 1883, "connected": True,
    }
    return broker_id


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
        """Initial status shows no brokers and nothing publishing."""
        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        status = adapter.get_status()
        assert status["connected"] is False
        assert status["available"] is False
        assert status["brokers"] == []
        assert status["publishing_devices"] == 0

    async def test_get_status_lists_brokers(self):
        """Status lists each broker with its connection state."""
        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        b1 = _connect_fake_broker(adapter, "emqx-a")
        adapter._broker_info[uuid.uuid4()] = {
            "name": "emqx-b", "host": "down", "port": 1883, "connected": False,
        }
        status = adapter.get_status()
        assert status["connected"] is True  # at least one connected
        names = {b["name"]: b["connected"] for b in status["brokers"]}
        assert names == {"emqx-a": True, "emqx-b": False}
        assert any(b["id"] == str(b1) for b in status["brokers"])

    async def test_set_device_meta(self):
        """set_device_meta stores metadata for topic rendering."""
        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        device_id = uuid.uuid4()
        adapter.set_device_meta(device_id, "Test-Device", 10, "Solar Inverter")
        assert adapter._device_meta[device_id]["device_name"] == "Test-Device"
        assert adapter._device_meta[device_id]["slave_id"] == 10

    async def test_start_publishing_fails_without_broker_connection(self):
        """start_publishing raises when the target broker is not connected."""
        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        with pytest.raises(RuntimeError, match="not connected"):
            await adapter.start_publishing(uuid.uuid4(), uuid.uuid4(), None)

    async def test_stop_publishing_only_targets_given_broker(self):
        """stop_publishing(device, broker) leaves other brokers' tasks running."""
        import asyncio

        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        dev = uuid.uuid4()
        b1, b2 = uuid.uuid4(), uuid.uuid4()
        adapter._publish_tasks[(dev, b1)] = asyncio.create_task(asyncio.sleep(3600))
        adapter._publish_tasks[(dev, b2)] = asyncio.create_task(asyncio.sleep(3600))

        await adapter.stop_publishing(dev, b1)
        assert (dev, b1) not in adapter._publish_tasks
        assert (dev, b2) in adapter._publish_tasks

        # No broker given -> all of the device's tasks stop
        await adapter.stop_publishing(dev)
        assert not adapter._publish_tasks

    async def test_disconnect_broker_cancels_only_its_tasks(self):
        """Disconnecting one broker leaves other brokers' publish tasks alone."""
        import asyncio

        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        b1 = _connect_fake_broker(adapter, "gone")
        b2 = _connect_fake_broker(adapter, "stays")
        d1, d2 = uuid.uuid4(), uuid.uuid4()
        adapter._publish_tasks[(d1, b1)] = asyncio.create_task(asyncio.sleep(3600))
        adapter._publish_tasks[(d2, b2)] = asyncio.create_task(asyncio.sleep(3600))

        await adapter.disconnect_broker(b1)
        assert (d1, b1) not in adapter._publish_tasks
        assert (d2, b2) in adapter._publish_tasks
        assert b1 not in adapter._broker_info
        assert adapter.is_broker_connected(b2)
        await adapter.stop_publishing(d2)

    async def test_publishing_devices_counts_distinct_devices(self):
        """A device publishing to two brokers counts once."""
        import asyncio

        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        dev = uuid.uuid4()
        b1, b2 = uuid.uuid4(), uuid.uuid4()
        adapter._publish_tasks[(dev, b1)] = asyncio.create_task(asyncio.sleep(3600))
        adapter._publish_tasks[(dev, b2)] = asyncio.create_task(asyncio.sleep(3600))
        assert adapter.get_status()["publishing_devices"] == 1
        await adapter.stop_publishing(dev)

    async def test_update_register_is_noop(self):
        """update_register is a no-op for MQTT (reads from SimulationEngine)."""
        from app.protocols.mqtt_adapter import MqttAdapter

        adapter = MqttAdapter()
        # Should not raise
        await adapter.update_register(
            uuid.uuid4(), address=0, function_code=3,
            value=1.0, data_type="float32", byte_order="big",
        )


# === Route ↔ Adapter Integration Tests (fake adapter) ===


class FakeMqttAdapter:
    """Records adapter calls so route behavior can be asserted without a broker."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.connected = True

    def set_device_meta(
        self, device_id, device_name, slave_id=0, template_name="",
    ) -> None:
        self.calls.append(
            ("set_device_meta", device_id, device_name, slave_id, template_name)
        )

    async def start_publishing(self, device_id, broker_id, config) -> None:
        self.calls.append(
            ("start_publishing", device_id, broker_id, config.topic_template)
        )

    async def stop_publishing(self, device_id, broker_id=None) -> None:
        self.calls.append(("stop_publishing", device_id, broker_id))

    async def connect_broker(self, broker_id, settings) -> bool:
        self.calls.append(("connect_broker", broker_id, settings.host, settings.password))
        return self.connected

    async def reconnect_broker(self, broker_id, settings) -> bool:
        self.calls.append(
            ("reconnect_broker", broker_id, settings.host, settings.password)
        )
        return self.connected

    async def disconnect_broker(self, broker_id) -> None:
        self.calls.append(("disconnect_broker", broker_id))

    def is_broker_connected(self, broker_id) -> bool:
        return self.connected

    def get_status(self) -> dict:
        return {
            "connected": self.connected,
            "available": self.connected,
            "brokers": [],
            "publishing_devices": 0,
        }


@pytest.fixture
def fake_mqtt_adapter():
    """Swap a recording fake in for the mqtt adapter; restore afterwards."""
    from app.protocols import protocol_manager

    fake = FakeMqttAdapter()
    prev = protocol_manager._adapters.get("mqtt")
    protocol_manager.register_adapter("mqtt", fake)
    yield fake
    if prev is None:
        protocol_manager._adapters.pop("mqtt", None)
    else:
        protocol_manager._adapters["mqtt"] = prev


async def _put_publish_config(
    client: AsyncClient, device_id: str, broker_id: str,
) -> None:
    resp = await client.put(
        f"/api/v1/system/devices/{device_id}/mqtt/{broker_id}",
        json={
            "topic_template": "gm/{device_name}",
            "payload_mode": "batch",
            "publish_interval_seconds": 5,
            "qos": 0,
            "retain": False,
        },
    )
    assert resp.status_code == 200


async def _set_device_status(device_id: str, status: str) -> None:
    """Flip a device's status directly in the (test) DB."""
    from sqlalchemy import update

    import app.database as db
    from app.models.device import DeviceInstance

    async with db.async_session_factory() as session:
        await session.execute(
            update(DeviceInstance)
            .where(DeviceInstance.id == uuid.UUID(device_id))
            .values(status=status)
        )
        await session.commit()


class TestPublishStartStop:
    """POST /mqtt/start and /mqtt/stop with and without a broker filter."""

    async def _device_with_two_configs(self, client: AsyncClient):
        b1 = await _create_broker(client, f"s1-{uuid.uuid4().hex[:6]}")
        b2 = await _create_broker(client, f"s2-{uuid.uuid4().hex[:6]}")
        template = await _create_template(client)
        device = await _create_device(client, template["id"])
        await _put_publish_config(client, device["id"], b1["id"])
        await _put_publish_config(client, device["id"], b2["id"])
        return device, b1, b2, template

    async def test_start_all_brokers(
        self, client: AsyncClient, fake_mqtt_adapter: FakeMqttAdapter,
    ):
        device, b1, b2, _ = await self._device_with_two_configs(client)

        resp = await client.post(f"/api/v1/system/devices/{device['id']}/mqtt/start")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        assert all(c["enabled"] for c in data)

        starts = [c for c in fake_mqtt_adapter.calls if c[0] == "start_publishing"]
        started_brokers = {c[2] for c in starts}
        assert started_brokers == {uuid.UUID(b1["id"]), uuid.UUID(b2["id"])}

    async def test_start_single_broker(
        self, client: AsyncClient, fake_mqtt_adapter: FakeMqttAdapter,
    ):
        device, b1, b2, _ = await self._device_with_two_configs(client)

        resp = await client.post(
            f"/api/v1/system/devices/{device['id']}/mqtt/start",
            params={"broker_id": b1["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["broker_id"] == b1["id"]

        starts = [c for c in fake_mqtt_adapter.calls if c[0] == "start_publishing"]
        assert {c[2] for c in starts} == {uuid.UUID(b1["id"])}

        # The other pair's config stays disabled
        resp = await client.get(f"/api/v1/system/devices/{device['id']}/mqtt")
        enabled = {c["broker_id"]: c["enabled"] for c in resp.json()["data"]}
        assert enabled[b1["id"]] is True
        assert enabled[b2["id"]] is False

    async def test_stop_single_broker(
        self, client: AsyncClient, fake_mqtt_adapter: FakeMqttAdapter,
    ):
        device, b1, b2, _ = await self._device_with_two_configs(client)
        await client.post(f"/api/v1/system/devices/{device['id']}/mqtt/start")

        resp = await client.post(
            f"/api/v1/system/devices/{device['id']}/mqtt/stop",
            params={"broker_id": b1["id"]},
        )
        assert resp.status_code == 200

        stops = [c for c in fake_mqtt_adapter.calls if c[0] == "stop_publishing"]
        assert (uuid.UUID(device["id"]), uuid.UUID(b1["id"])) in {
            (c[1], c[2]) for c in stops
        }

        resp = await client.get(f"/api/v1/system/devices/{device['id']}/mqtt")
        enabled = {c["broker_id"]: c["enabled"] for c in resp.json()["data"]}
        assert enabled[b1["id"]] is False
        assert enabled[b2["id"]] is True

    async def test_start_without_configs_404(
        self, client: AsyncClient, fake_mqtt_adapter: FakeMqttAdapter,
    ):
        template = await _create_template(client)
        device = await _create_device(client, template["id"])
        resp = await client.post(f"/api/v1/system/devices/{device['id']}/mqtt/start")
        assert resp.status_code == 404

    async def test_start_sets_meta_before_publishing(
        self, client: AsyncClient, fake_mqtt_adapter: FakeMqttAdapter,
    ):
        """POST /mqtt/start must give the adapter device meta first (#82)."""
        broker = await _create_broker(client, "meta-broker")
        template = await _create_template(client)
        device = await _create_device(client, template["id"])
        await _put_publish_config(client, device["id"], broker["id"])

        resp = await client.post(f"/api/v1/system/devices/{device['id']}/mqtt/start")
        assert resp.status_code == 200

        kinds = [c[0] for c in fake_mqtt_adapter.calls]
        assert "set_device_meta" in kinds, "adapter never received device meta"
        meta_call = next(
            c for c in fake_mqtt_adapter.calls if c[0] == "set_device_meta"
        )
        assert meta_call[1] == uuid.UUID(device["id"])
        assert meta_call[2] == device["name"]
        assert meta_call[3] == device["slave_id"]
        assert meta_call[4] == template["name"]
        # Meta must be in place before the publish loop starts
        assert kinds.index("set_device_meta") < kinds.index("start_publishing")


class TestBrokerAdapterWiring:
    """Broker CRUD must apply changes to the running adapter (#81, #87)."""

    async def test_create_connects_adapter(
        self, client: AsyncClient, fake_mqtt_adapter: FakeMqttAdapter,
    ):
        broker = await _create_broker(client, "wired")
        connects = [c for c in fake_mqtt_adapter.calls if c[0] == "connect_broker"]
        assert connects, "adapter.connect_broker() was never called"
        assert connects[-1][1] == uuid.UUID(broker["id"])
        assert connects[-1][2] == "broker.example.com"

    async def test_update_reconnects_only_that_broker(
        self, client: AsyncClient, fake_mqtt_adapter: FakeMqttAdapter,
    ):
        broker = await _create_broker(client, "target")
        fake_mqtt_adapter.calls.clear()
        resp = await client.put(
            f"/api/v1/system/mqtt/brokers/{broker['id']}",
            json=_broker_payload("target", host="new-host"),
        )
        assert resp.status_code == 200
        reconnects = [c for c in fake_mqtt_adapter.calls if c[0] == "reconnect_broker"]
        assert reconnects and reconnects[-1][1] == uuid.UUID(broker["id"])
        assert reconnects[-1][2] == "new-host"

    async def test_reconnect_uses_stored_password_when_masked(
        self, client: AsyncClient, fake_mqtt_adapter: FakeMqttAdapter,
    ):
        broker = await _create_broker(client, "masked", password="real-secret")
        # Frontend echoes the masked value back on unrelated edits
        resp = await client.put(
            f"/api/v1/system/mqtt/brokers/{broker['id']}",
            json=_broker_payload("masked", host="h2", password="****"),
        )
        assert resp.status_code == 200
        reconnects = [c for c in fake_mqtt_adapter.calls if c[0] == "reconnect_broker"]
        assert reconnects[-1][3] == "real-secret", (
            "reconnect must use the stored password, not the '****' mask"
        )

    async def test_delete_disconnects_adapter(
        self, client: AsyncClient, fake_mqtt_adapter: FakeMqttAdapter,
    ):
        broker = await _create_broker(client, "bye")
        resp = await client.delete(f"/api/v1/system/mqtt/brokers/{broker['id']}")
        assert resp.status_code == 200
        disconnects = [c for c in fake_mqtt_adapter.calls if c[0] == "disconnect_broker"]
        assert disconnects and disconnects[-1][1] == uuid.UUID(broker["id"])

    async def test_crud_without_adapter_still_persists(self, client: AsyncClient):
        """No mqtt adapter registered (e.g. startup failure) → settings still save."""
        from app.protocols import protocol_manager

        prev = protocol_manager._adapters.pop("mqtt", None)
        try:
            broker = await _create_broker(client, "no-adapter")
            resp = await client.put(
                f"/api/v1/system/mqtt/brokers/{broker['id']}",
                json=_broker_payload("no-adapter", host="h4"),
            )
            assert resp.status_code == 200
            assert resp.json()["data"]["host"] == "h4"
        finally:
            if prev is not None:
                protocol_manager.register_adapter("mqtt", prev)


class TestStartupResume:
    """Startup resume must bring MQTT publish tasks back (#84)."""

    async def test_resume_running_devices_resumes_publishing(
        self, client: AsyncClient, fake_mqtt_adapter: FakeMqttAdapter,
    ):
        broker = await _create_broker(client, "resume-broker")
        template = await _create_template(client)
        device = await _create_device(client, template["id"])
        await _put_publish_config(client, device["id"], broker["id"])
        resp = await client.post(f"/api/v1/system/devices/{device['id']}/mqtt/start")
        assert resp.status_code == 200
        await _set_device_status(device["id"], "running")
        fake_mqtt_adapter.calls.clear()

        # Simulates the lifespan startup path after a backend restart
        import app.database as db
        from app.services import device_service

        async with db.async_session_factory() as session:
            await device_service.resume_running_devices(session)

        kinds = [c[0] for c in fake_mqtt_adapter.calls]
        assert "start_publishing" in kinds, (
            "startup resume did not restart enabled MQTT publishing"
        )
        assert kinds.index("set_device_meta") < kinds.index("start_publishing")

    async def test_resume_skips_publishing_for_stopped_devices(
        self, client: AsyncClient, fake_mqtt_adapter: FakeMqttAdapter,
    ):
        broker = await _create_broker(client, "stopped-broker")
        template = await _create_template(client)
        device = await _create_device(client, template["id"])
        await _put_publish_config(client, device["id"], broker["id"])
        resp = await client.post(f"/api/v1/system/devices/{device['id']}/mqtt/start")
        assert resp.status_code == 200
        # Device stays "stopped" — enabled config alone must not publish
        fake_mqtt_adapter.calls.clear()

        import app.database as db
        from app.services import device_service

        async with db.async_session_factory() as session:
            await device_service.resume_running_devices(session)

        kinds = [c[0] for c in fake_mqtt_adapter.calls]
        assert "start_publishing" not in kinds

    async def test_resume_filtered_by_broker(
        self, client: AsyncClient, fake_mqtt_adapter: FakeMqttAdapter,
    ):
        """resume_enabled_publishing(broker_id) only touches that broker."""
        b1 = await _create_broker(client, "filter-a")
        b2 = await _create_broker(client, "filter-b")
        template = await _create_template(client)
        device = await _create_device(client, template["id"])
        await _put_publish_config(client, device["id"], b1["id"])
        await _put_publish_config(client, device["id"], b2["id"])
        await client.post(f"/api/v1/system/devices/{device['id']}/mqtt/start")
        await _set_device_status(device["id"], "running")
        fake_mqtt_adapter.calls.clear()

        import app.database as db
        from app.services import mqtt_service

        async with db.async_session_factory() as session:
            started = await mqtt_service.resume_enabled_publishing(
                session, uuid.UUID(b1["id"]),
            )

        assert started == 1
        starts = [c for c in fake_mqtt_adapter.calls if c[0] == "start_publishing"]
        assert {c[2] for c in starts} == {uuid.UUID(b1["id"])}
