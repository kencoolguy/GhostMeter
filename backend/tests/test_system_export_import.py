"""Tests for system config export/import."""

from httpx import AsyncClient

TEMPLATE_PAYLOAD = {
    "name": "Export Test Meter",
    "protocol": "modbus_tcp",
    "description": "For export testing",
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


async def _create_template(client: AsyncClient, payload: dict | None = None) -> dict:
    """Helper: create a template."""
    resp = await client.post("/api/v1/templates", json=payload or TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["data"]


async def _create_device(
    client: AsyncClient, template_id: str, name: str = "Dev-01", slave_id: int = 1
) -> dict:
    """Helper: create a device."""
    resp = await client.post(
        "/api/v1/devices",
        json={
            "name": name,
            "template_id": template_id,
            "slave_id": slave_id,
            "port": 502,
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]


class TestSystemExport:
    async def test_export_empty_system(self, client: AsyncClient) -> None:
        """Export with no user data returns only built-in templates."""
        resp = await client.get("/api/v1/system/export")
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")
        data = resp.json()
        assert data["version"] == "1.0"
        assert "exported_at" in data
        assert isinstance(data["templates"], list)
        assert data["devices"] == []
        assert data["simulation_configs"] == []
        assert data["anomaly_schedules"] == []

    async def test_export_with_template_and_device(self, client: AsyncClient) -> None:
        """Export includes user-created templates and devices."""
        template = await _create_template(client)
        await _create_device(client, template["id"])

        resp = await client.get("/api/v1/system/export")
        assert resp.status_code == 200
        data = resp.json()

        # Find our template in export
        names = [t["name"] for t in data["templates"]]
        assert "Export Test Meter" in names

        # Device references template by name
        assert len(data["devices"]) == 1
        assert data["devices"][0]["template_name"] == "Export Test Meter"
        assert data["devices"][0]["slave_id"] == 1

        # No IDs in export
        for t in data["templates"]:
            assert "id" not in t
        for d in data["devices"]:
            assert "id" not in d
            assert "template_id" not in d

    async def test_export_includes_simulation_configs(self, client: AsyncClient) -> None:
        """Export includes simulation configs referencing device by name."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        # Set simulation config
        await client.put(
            f"/api/v1/devices/{device['id']}/simulation",
            json={
                "configs": [
                    {
                        "register_name": "voltage",
                        "data_mode": "static",
                        "mode_params": {"value": 230.0},
                        "is_enabled": True,
                        "update_interval_ms": 1000,
                    }
                ]
            },
        )

        resp = await client.get("/api/v1/system/export")
        data = resp.json()
        assert len(data["simulation_configs"]) == 1
        assert data["simulation_configs"][0]["device_name"] == "Dev-01"
        assert data["simulation_configs"][0]["register_name"] == "voltage"

    async def test_export_includes_anomaly_schedules(self, client: AsyncClient) -> None:
        """Export includes anomaly schedules referencing device by name."""
        template = await _create_template(client)
        device = await _create_device(client, template["id"])

        # Set anomaly schedule
        await client.put(
            f"/api/v1/devices/{device['id']}/anomaly/schedules",
            json={
                "schedules": [
                    {
                        "register_name": "voltage",
                        "anomaly_type": "spike",
                        "anomaly_params": {"multiplier": 3.0, "probability": 0.1},
                        "trigger_after_seconds": 60,
                        "duration_seconds": 30,
                        "is_enabled": True,
                    }
                ]
            },
        )

        resp = await client.get("/api/v1/system/export")
        data = resp.json()
        assert len(data["anomaly_schedules"]) == 1
        assert data["anomaly_schedules"][0]["device_name"] == "Dev-01"
        assert data["anomaly_schedules"][0]["anomaly_type"] == "spike"
