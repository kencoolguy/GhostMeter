"""Integration test: simulation config + device lifecycle."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestDeviceSimulationIntegration:
    async def test_set_config_on_stopped_device(self, client: AsyncClient):
        """Set simulation config on a stopped device, verify persistence."""
        # Create template
        template_data = {
            "name": "Integration Meter",
            "protocol": "modbus_tcp",
            "registers": [
                {
                    "name": "voltage",
                    "address": 0,
                    "function_code": 3,
                    "data_type": "float32",
                    "byte_order": "big_endian",
                    "scale_factor": 1.0,
                    "unit": "V",
                    "sort_order": 0,
                },
            ],
        }
        resp = await client.post("/api/v1/templates", json=template_data)
        assert resp.status_code == 201
        template_id = resp.json()["data"]["id"]

        # Create device
        resp = await client.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "Integration Device",
            "slave_id": 99,
        })
        assert resp.status_code == 201
        device_id = resp.json()["data"]["id"]

        # Set simulation config while stopped
        resp = await client.put(f"/api/v1/devices/{device_id}/simulation", json={
            "configs": [
                {
                    "register_name": "voltage",
                    "data_mode": "static",
                    "mode_params": {"value": 230.0},
                },
            ],
        })
        assert resp.status_code == 200

        # Verify config persisted
        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1
        assert resp.json()["data"][0]["data_mode"] == "static"

    async def _create_device(self, client: AsyncClient) -> str:
        """Create a stopped modbus device and return its id."""
        resp = await client.post("/api/v1/templates", json={
            "name": "Fault Roundtrip Meter",
            "protocol": "modbus_tcp",
            "registers": [
                {
                    "name": "voltage",
                    "address": 0,
                    "function_code": 3,
                    "data_type": "float32",
                    "byte_order": "big_endian",
                    "scale_factor": 1.0,
                    "unit": "V",
                    "sort_order": 0,
                },
            ],
        })
        assert resp.status_code == 201
        template_id = resp.json()["data"]["id"]
        resp = await client.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "Fault Roundtrip Device",
            "slave_id": 88,
        })
        assert resp.status_code == 201
        return resp.json()["data"]["id"]

    async def test_fault_api_roundtrip(self, client: AsyncClient):
        """Set fault, get it, clear it — on a real device."""
        # The fault set/clear endpoints resolve the device's protocol, so the
        # device must exist (a Modbus device suffices: its adapter hook is a no-op).
        device_id = await self._create_device(client)

        # Set fault
        resp = await client.put(f"/api/v1/devices/{device_id}/fault", json={
            "fault_type": "delay", "params": {"delay_ms": 200},
        })
        assert resp.status_code == 200

        # Get fault
        resp = await client.get(f"/api/v1/devices/{device_id}/fault")
        assert resp.json()["data"]["fault_type"] == "delay"

        # Clear fault
        resp = await client.delete(f"/api/v1/devices/{device_id}/fault")
        assert resp.status_code == 200

        # Verify cleared
        resp = await client.get(f"/api/v1/devices/{device_id}/fault")
        assert resp.json()["data"] is None

    async def test_set_fault_on_unknown_device_returns_404(self, client: AsyncClient):
        """Setting a fault on a non-existent device is rejected (404), since the
        endpoint now resolves the device's protocol before applying the fault."""
        unknown = "00000000-0000-0000-0000-000000000001"
        resp = await client.put(f"/api/v1/devices/{unknown}/fault", json={
            "fault_type": "delay", "params": {"delay_ms": 200},
        })
        assert resp.status_code == 404

        # The rejected request must not have left an orphan fault entry.
        resp = await client.get(f"/api/v1/devices/{unknown}/fault")
        assert resp.json()["data"] is None

    async def test_fault_api_rejects_invalid_params(self, client: AsyncClient):
        """Malformed fault params are rejected with 422 at the API boundary
        (body validation runs before the handler, so device need not exist)."""
        dev = "00000000-0000-0000-0000-000000000009"
        for body in (
            {"fault_type": "delay", "params": {"delay_ms": -100}},
            {"fault_type": "delay", "params": {"delay_ms": "abc"}},
            {"fault_type": "intermittent", "params": {"failure_rate": 1.5}},
            {"fault_type": "intermittent", "params": {"failure_rate": "x"}},
        ):
            resp = await client.put(f"/api/v1/devices/{dev}/fault", json=body)
            assert resp.status_code == 422, (body, resp.status_code)
