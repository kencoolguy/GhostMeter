import uuid

from httpx import AsyncClient

from app.config import get_settings

# Reuse template creation helper
TEMPLATE_PAYLOAD = {
    "name": "Test Meter",
    "protocol": "modbus_tcp",
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


async def create_template(client: AsyncClient) -> dict:
    """Helper: create a template and return its data."""
    response = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert response.status_code == 201
    return response.json()["data"]


async def create_device(
    client: AsyncClient,
    template_id: str,
    name: str = "Test Device",
    slave_id: int = 1,
) -> dict:
    """Helper: create a device and return its data."""
    response = await client.post(
        "/api/v1/devices",
        json={
            "template_id": template_id,
            "name": name,
            "slave_id": slave_id,
        },
    )
    assert response.status_code == 201
    return response.json()["data"]


async def create_protocol_template(
    client: AsyncClient, protocol: str, name: str,
) -> dict:
    """Helper: create a template for a given protocol and return its data."""
    payload = {**TEMPLATE_PAYLOAD, "protocol": protocol, "name": name}
    response = await client.post("/api/v1/templates", json=payload)
    assert response.status_code == 201
    return response.json()["data"]


class TestCreateDevice:
    async def test_create_device_success(self, client: AsyncClient) -> None:
        template = await create_template(client)
        data = await create_device(client, template["id"])
        assert data["name"] == "Test Device"
        assert data["slave_id"] == 1
        assert data["status"] == "stopped"
        assert data["template_name"] == "Test Meter"

    async def test_create_device_invalid_slave_id(self, client: AsyncClient) -> None:
        template = await create_template(client)
        response = await client.post(
            "/api/v1/devices",
            json={"template_id": template["id"], "name": "Bad", "slave_id": 0},
        )
        assert response.status_code == 422

    async def test_create_device_slave_id_too_high(self, client: AsyncClient) -> None:
        template = await create_template(client)
        response = await client.post(
            "/api/v1/devices",
            json={"template_id": template["id"], "name": "Bad", "slave_id": 248},
        )
        assert response.status_code == 422

    async def test_create_device_duplicate_slave_id(self, client: AsyncClient) -> None:
        template = await create_template(client)
        await create_device(client, template["id"], slave_id=1)
        response = await client.post(
            "/api/v1/devices",
            json={"template_id": template["id"], "name": "Dup", "slave_id": 1},
        )
        assert response.status_code == 422
        assert "already in use" in response.json()["detail"]

    async def test_create_device_invalid_template(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/devices",
            json={
                "template_id": "00000000-0000-0000-0000-000000000000",
                "name": "Bad",
                "slave_id": 1,
            },
        )
        assert response.status_code == 404


class TestBatchCreateDevices:
    async def test_batch_create_success(self, client: AsyncClient) -> None:
        template = await create_template(client)
        response = await client.post(
            "/api/v1/devices/batch",
            json={
                "template_id": template["id"],
                "slave_id_start": 1,
                "slave_id_end": 3,
            },
        )
        assert response.status_code == 201
        devices = response.json()["data"]
        assert len(devices) == 3
        assert devices[0]["name"] == "Test Meter - Slave 1"

    async def test_batch_create_with_prefix(self, client: AsyncClient) -> None:
        template = await create_template(client)
        response = await client.post(
            "/api/v1/devices/batch",
            json={
                "template_id": template["id"],
                "slave_id_start": 10,
                "slave_id_end": 11,
                "name_prefix": "Floor 3",
            },
        )
        assert response.status_code == 201
        devices = response.json()["data"]
        # Name format is "{prefix}{slave_id}" — no space between prefix and slave ID
        # (updated in commit 4c8cefa to avoid double spacing when the prefix ends in " ")
        assert devices[0]["name"] == "Floor 310"

    async def test_batch_create_invalid_range(self, client: AsyncClient) -> None:
        template = await create_template(client)
        response = await client.post(
            "/api/v1/devices/batch",
            json={
                "template_id": template["id"],
                "slave_id_start": 5,
                "slave_id_end": 3,
            },
        )
        assert response.status_code == 422

    async def test_batch_create_too_many(self, client: AsyncClient) -> None:
        template = await create_template(client)
        response = await client.post(
            "/api/v1/devices/batch",
            json={
                "template_id": template["id"],
                "slave_id_start": 1,
                "slave_id_end": 51,
            },
        )
        assert response.status_code == 422

    async def test_batch_create_partial_conflict(self, client: AsyncClient) -> None:
        template = await create_template(client)
        await create_device(client, template["id"], slave_id=2)
        response = await client.post(
            "/api/v1/devices/batch",
            json={
                "template_id": template["id"],
                "slave_id_start": 1,
                "slave_id_end": 3,
            },
        )
        assert response.status_code == 422


class TestProtocolSlaveIdLimits:
    """Modbus/BACnet keep the protocol-mandated 1-247 ceiling; SNMP/OPC UA/MQTT
    don't need one, and each protocol now gets its own port so the (slave_id,
    port) uniqueness check no longer collides across protocols."""

    async def test_bacnet_slave_id_too_high_rejected(self, client: AsyncClient) -> None:
        template = await create_protocol_template(client, "bacnet", "BACnet Meter")
        response = await client.post(
            "/api/v1/devices",
            json={"template_id": template["id"], "name": "Bad", "slave_id": 248},
        )
        assert response.status_code == 422

    async def test_snmp_slave_id_above_247_allowed(self, client: AsyncClient) -> None:
        template = await create_protocol_template(client, "snmp", "SNMP Meter")
        response = await client.post(
            "/api/v1/devices",
            json={"template_id": template["id"], "name": "Big", "slave_id": 300},
        )
        assert response.status_code == 201
        assert response.json()["data"]["slave_id"] == 300

    async def test_opcua_slave_id_above_247_allowed(self, client: AsyncClient) -> None:
        template = await create_protocol_template(client, "opcua", "OPCUA Meter")
        response = await client.post(
            "/api/v1/devices",
            json={"template_id": template["id"], "name": "Big", "slave_id": 1000},
        )
        assert response.status_code == 201

    async def test_mqtt_slave_id_above_247_allowed(self, client: AsyncClient) -> None:
        template = await create_protocol_template(client, "mqtt", "MQTT Meter")
        response = await client.post(
            "/api/v1/devices",
            json={"template_id": template["id"], "name": "Big", "slave_id": 5000},
        )
        assert response.status_code == 201

    async def test_devices_on_different_protocols_can_share_slave_id(
        self, client: AsyncClient,
    ) -> None:
        modbus_template = await create_protocol_template(client, "modbus_tcp", "Modbus Meter")
        bacnet_template = await create_protocol_template(client, "bacnet", "BACnet Meter")

        modbus_resp = await client.post(
            "/api/v1/devices",
            json={"template_id": modbus_template["id"], "name": "M5", "slave_id": 5},
        )
        assert modbus_resp.status_code == 201

        bacnet_resp = await client.post(
            "/api/v1/devices",
            json={"template_id": bacnet_template["id"], "name": "B5", "slave_id": 5},
        )
        assert bacnet_resp.status_code == 201

    async def test_device_port_reflects_protocol(self, client: AsyncClient) -> None:
        settings = get_settings()
        cases = [
            ("modbus_tcp", settings.MODBUS_PORT),
            ("snmp", settings.SNMP_PORT),
            ("opcua", settings.OPCUA_PORT),
            ("bacnet", settings.BACNET_PORT),
        ]
        for protocol, expected_port in cases:
            template = await create_protocol_template(client, protocol, f"{protocol} Meter")
            response = await client.post(
                "/api/v1/devices",
                json={"template_id": template["id"], "name": "Dev", "slave_id": 1},
            )
            assert response.status_code == 201
            assert response.json()["data"]["port"] == expected_port


class TestBatchProtocolSlaveIdLimits:
    async def test_bacnet_batch_range_exceeding_limit_rejected(
        self, client: AsyncClient,
    ) -> None:
        template = await create_protocol_template(client, "bacnet", "BACnet Batch")
        response = await client.post(
            "/api/v1/devices/batch",
            json={"template_id": template["id"], "slave_id_start": 240, "slave_id_end": 248},
        )
        assert response.status_code == 422

    async def test_snmp_batch_range_above_247_allowed(self, client: AsyncClient) -> None:
        template = await create_protocol_template(client, "snmp", "SNMP Batch")
        response = await client.post(
            "/api/v1/devices/batch",
            json={"template_id": template["id"], "slave_id_start": 300, "slave_id_end": 310},
        )
        assert response.status_code == 201
        assert len(response.json()["data"]) == 11


class TestListDevices:
    async def test_list_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/devices")
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_list_with_data(self, client: AsyncClient) -> None:
        template = await create_template(client)
        await create_device(client, template["id"])
        response = await client.get("/api/v1/devices")
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["template_name"] == "Test Meter"


class TestGetDevice:
    async def test_get_device_detail(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        response = await client.get(f"/api/v1/devices/{device['id']}")
        assert response.status_code == 200
        detail = response.json()["data"]
        assert detail["name"] == "Test Device"
        assert len(detail["registers"]) == 1
        assert detail["registers"][0]["name"] == "voltage"
        assert detail["registers"][0]["value"] is None
        assert "byte_order" in detail["registers"][0]
        assert "scale_factor" in detail["registers"][0]

    async def test_get_device_not_found(self, client: AsyncClient) -> None:
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/v1/devices/{fake_id}")
        assert response.status_code == 404
        assert response.json()["error_code"] == "DEVICE_NOT_FOUND"


class TestUpdateDevice:
    async def test_update_success(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        response = await client.put(
            f"/api/v1/devices/{device['id']}",
            json={"name": "Updated", "slave_id": 5},
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated"
        assert response.json()["data"]["slave_id"] == 5

    async def test_update_running_device_blocked(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        await client.post(f"/api/v1/devices/{device['id']}/start")
        response = await client.put(
            f"/api/v1/devices/{device['id']}",
            json={"name": "Updated", "slave_id": 1},
        )
        assert response.status_code == 409


class TestDeleteDevice:
    async def test_delete_success(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        response = await client.delete(f"/api/v1/devices/{device['id']}")
        assert response.status_code == 200

    async def test_delete_running_blocked(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        await client.post(f"/api/v1/devices/{device['id']}/start")
        response = await client.delete(f"/api/v1/devices/{device['id']}")
        assert response.status_code == 409


class TestStartStop:
    async def test_start_device(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        response = await client.post(f"/api/v1/devices/{device['id']}/start")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "running"

    async def test_stop_device(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        await client.post(f"/api/v1/devices/{device['id']}/start")
        response = await client.post(f"/api/v1/devices/{device['id']}/stop")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "stopped"

    async def test_start_already_running(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        await client.post(f"/api/v1/devices/{device['id']}/start")
        response = await client.post(f"/api/v1/devices/{device['id']}/start")
        assert response.status_code == 409

    async def test_stop_already_stopped(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        response = await client.post(f"/api/v1/devices/{device['id']}/stop")
        assert response.status_code == 409

    async def test_start_error_state_blocked(self, client: AsyncClient) -> None:
        """Devices in error state cannot be started (only stopped)."""
        # Phase 3 has no API to set error state directly;
        # we test via direct DB manipulation
        pass  # Covered in Phase 4 when error state can be triggered


class TestDeviceMqttPublishing:
    async def test_list_devices_includes_mqtt_publishing_false_by_default(
        self, client: AsyncClient,
    ) -> None:
        """Device without MQTT config should have mqtt_publishing=False."""
        template = await create_template(client)
        await create_device(client, template["id"])
        response = await client.get("/api/v1/devices")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["mqtt_publishing"] is False

    async def test_list_devices_mqtt_publishing_reflects_enabled_config(
        self, client: AsyncClient,
    ) -> None:
        """mqtt_publishing is False for disabled configs, True once any is enabled."""
        broker_resp = await client.post("/api/v1/system/mqtt/brokers", json={
            "name": "list-broker", "host": "localhost", "port": 1883,
            "username": "", "password": "", "client_id": "gm", "use_tls": False,
        })
        assert broker_resp.status_code == 201
        broker = broker_resp.json()["data"]

        template = await create_template(client)
        device = await create_device(client, template["id"])
        # PUT an MQTT config — enabled defaults to false
        response = await client.put(
            f"/api/v1/system/devices/{device['id']}/mqtt/{broker['id']}",
            json={"topic_template": "test/{device_name}", "payload_mode": "batch"},
        )
        assert response.status_code == 200

        response = await client.get("/api/v1/devices")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["mqtt_publishing"] is False

        # Enable it directly in the DB — the flag must flip to True (and the
        # multi-config join must not duplicate the device row)
        import app.database as db
        from sqlalchemy import update as sa_update

        from app.models.mqtt import MqttPublishConfig

        async with db.async_session_factory() as session:
            await session.execute(
                sa_update(MqttPublishConfig)
                .where(MqttPublishConfig.device_id == uuid.UUID(device["id"]))
                .values(enabled=True)
            )
            await session.commit()

        response = await client.get("/api/v1/devices")
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["mqtt_publishing"] is True


class TestGetRegisters:
    async def test_get_registers(self, client: AsyncClient) -> None:
        template = await create_template(client)
        device = await create_device(client, template["id"])
        response = await client.get(f"/api/v1/devices/{device['id']}/registers")
        assert response.status_code == 200
        regs = response.json()["data"]
        assert len(regs) == 1
        assert regs[0]["name"] == "voltage"
        assert regs[0]["value"] is None
