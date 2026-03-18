"""Integration tests for simulation config and fault control API routes."""

import uuid

from httpx import AsyncClient


TEMPLATE_PAYLOAD = {
    "name": "Sim Test Meter",
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
        {
            "name": "current",
            "address": 2,
            "function_code": 4,
            "data_type": "float32",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "A",
            "description": "Current",
            "sort_order": 1,
        },
    ],
}


async def _create_template_and_device(client: AsyncClient) -> tuple[str, str]:
    """Helper: create a template + device and return (template_id, device_id)."""
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    template_id = resp.json()["data"]["id"]

    resp = await client.post(
        "/api/v1/devices",
        json={"template_id": template_id, "name": "Sim Device", "slave_id": 10},
    )
    assert resp.status_code == 201
    device_id = resp.json()["data"]["id"]
    return template_id, device_id


# --- Simulation Config Tests ---


class TestGetSimulationConfigs:
    async def test_empty_configs(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    async def test_nonexistent_device_returns_404(self, client: AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/devices/{fake_id}/simulation")
        assert resp.status_code == 404


class TestSetSimulationConfigs:
    async def test_put_configs_success(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "configs": [
                {
                    "register_name": "voltage",
                    "data_mode": "static",
                    "mode_params": {"value": 220.0},
                },
                {
                    "register_name": "current",
                    "data_mode": "random",
                    "mode_params": {"min": 0, "max": 10},
                },
            ]
        }
        resp = await client.put(
            f"/api/v1/devices/{device_id}/simulation", json=payload
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        names = {c["register_name"] for c in data}
        assert names == {"voltage", "current"}

    async def test_put_replaces_existing(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        # Set initial config
        payload1 = {
            "configs": [
                {"register_name": "voltage", "data_mode": "static", "mode_params": {"value": 220}},
                {"register_name": "current", "data_mode": "static", "mode_params": {"value": 5}},
            ]
        }
        await client.put(f"/api/v1/devices/{device_id}/simulation", json=payload1)

        # Replace with only one config
        payload2 = {
            "configs": [
                {"register_name": "voltage", "data_mode": "random", "mode_params": {"min": 200, "max": 240}},
            ]
        }
        resp = await client.put(
            f"/api/v1/devices/{device_id}/simulation", json=payload2
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["register_name"] == "voltage"
        assert data[0]["data_mode"] == "random"

    async def test_put_invalid_register_name(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "configs": [
                {"register_name": "nonexistent_reg", "data_mode": "static", "mode_params": {}},
            ]
        }
        resp = await client.put(
            f"/api/v1/devices/{device_id}/simulation", json=payload
        )
        assert resp.status_code == 422

    async def test_put_invalid_data_mode(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "configs": [
                {"register_name": "voltage", "data_mode": "invalid_mode", "mode_params": {}},
            ]
        }
        resp = await client.put(
            f"/api/v1/devices/{device_id}/simulation", json=payload
        )
        assert resp.status_code == 422

    async def test_put_duplicate_register_names(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "configs": [
                {"register_name": "voltage", "data_mode": "static", "mode_params": {"value": 220}},
                {"register_name": "voltage", "data_mode": "random", "mode_params": {"min": 200, "max": 240}},
            ]
        }
        resp = await client.put(
            f"/api/v1/devices/{device_id}/simulation", json=payload
        )
        assert resp.status_code == 422


class TestUpdateSimulationConfig:
    async def test_patch_creates_new_config(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "register_name": "voltage",
            "data_mode": "static",
            "mode_params": {"value": 230.0},
        }
        resp = await client.patch(
            f"/api/v1/devices/{device_id}/simulation/voltage", json=payload
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["register_name"] == "voltage"
        assert data["data_mode"] == "static"

    async def test_patch_updates_existing(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "register_name": "voltage",
            "data_mode": "static",
            "mode_params": {"value": 220},
        }
        await client.patch(
            f"/api/v1/devices/{device_id}/simulation/voltage", json=payload
        )

        # Update same register
        payload2 = {
            "register_name": "voltage",
            "data_mode": "random",
            "mode_params": {"min": 200, "max": 240},
        }
        resp = await client.patch(
            f"/api/v1/devices/{device_id}/simulation/voltage", json=payload2
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["data_mode"] == "random"

        # Verify only one config exists
        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert len(resp.json()["data"]) == 1

    async def test_patch_invalid_register_name(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {
            "register_name": "nonexistent",
            "data_mode": "static",
            "mode_params": {},
        }
        resp = await client.patch(
            f"/api/v1/devices/{device_id}/simulation/nonexistent", json=payload
        )
        assert resp.status_code == 422


class TestDeleteSimulationConfigs:
    async def test_delete_clears_all(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        # Create configs first
        payload = {
            "configs": [
                {"register_name": "voltage", "data_mode": "static", "mode_params": {"value": 220}},
            ]
        }
        await client.put(f"/api/v1/devices/{device_id}/simulation", json=payload)

        # Delete all
        resp = await client.delete(f"/api/v1/devices/{device_id}/simulation")
        assert resp.status_code == 200

        # Verify empty
        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert resp.json()["data"] == []

    async def test_delete_nonexistent_device_returns_404(self, client: AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.delete(f"/api/v1/devices/{fake_id}/simulation")
        assert resp.status_code == 404


# --- Fault Control Tests ---


class TestFaultControl:
    async def test_put_fault_success(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {"fault_type": "delay", "params": {"delay_ms": 500}}
        resp = await client.put(
            f"/api/v1/devices/{device_id}/fault", json=payload
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["fault_type"] == "delay"
        assert data["params"] == {"delay_ms": 500}

    async def test_get_fault_after_set(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {"fault_type": "timeout", "params": {}}
        await client.put(f"/api/v1/devices/{device_id}/fault", json=payload)

        resp = await client.get(f"/api/v1/devices/{device_id}/fault")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["fault_type"] == "timeout"

    async def test_get_fault_when_none_set(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        resp = await client.get(f"/api/v1/devices/{device_id}/fault")
        assert resp.status_code == 200
        assert resp.json()["data"] is None

    async def test_delete_fault_clears(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        # Set a fault
        await client.put(
            f"/api/v1/devices/{device_id}/fault",
            json={"fault_type": "exception", "params": {"exception_code": 4}},
        )

        # Clear it
        resp = await client.delete(f"/api/v1/devices/{device_id}/fault")
        assert resp.status_code == 200

        # Verify cleared
        resp = await client.get(f"/api/v1/devices/{device_id}/fault")
        assert resp.json()["data"] is None

    async def test_put_invalid_fault_type(self, client: AsyncClient) -> None:
        _, device_id = await _create_template_and_device(client)
        payload = {"fault_type": "invalid_type", "params": {}}
        resp = await client.put(
            f"/api/v1/devices/{device_id}/fault", json=payload
        )
        assert resp.status_code == 422
