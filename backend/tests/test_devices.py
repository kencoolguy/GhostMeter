from httpx import AsyncClient

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
        assert devices[0]["name"] == "Floor 3 10"

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
