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
                {"register_name": "voltage", "data_mode": "static", "mode_params": {"value": 230.0}},
            ],
        })
        assert resp.status_code == 200

        # Verify config persisted
        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1
        assert resp.json()["data"][0]["data_mode"] == "static"

    async def test_fault_api_roundtrip(self, client: AsyncClient):
        """Set fault, get it, clear it."""
        device_id = "00000000-0000-0000-0000-000000000001"

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
