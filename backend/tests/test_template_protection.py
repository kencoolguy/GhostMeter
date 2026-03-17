from httpx import AsyncClient


TEMPLATE_PAYLOAD = {
    "name": "Protected Meter",
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
            "sort_order": 0,
        },
    ],
}


class TestTemplateProtection:
    async def test_cannot_delete_template_in_use(self, client: AsyncClient) -> None:
        # Create template
        resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
        template_id = resp.json()["data"]["id"]

        # Create device using this template
        await client.post(
            "/api/v1/devices",
            json={"template_id": template_id, "name": "Dev 1", "slave_id": 1},
        )

        # Try to delete template
        resp = await client.delete(f"/api/v1/templates/{template_id}")
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "TEMPLATE_IN_USE"
        assert "1 device(s)" in resp.json()["detail"]

    async def test_can_delete_template_after_devices_removed(
        self, client: AsyncClient,
    ) -> None:
        resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
        template_id = resp.json()["data"]["id"]

        resp = await client.post(
            "/api/v1/devices",
            json={"template_id": template_id, "name": "Dev 1", "slave_id": 1},
        )
        device_id = resp.json()["data"]["id"]

        # Delete device first
        await client.delete(f"/api/v1/devices/{device_id}")

        # Now template can be deleted
        resp = await client.delete(f"/api/v1/templates/{template_id}")
        assert resp.status_code == 200
