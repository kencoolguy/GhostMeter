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


class TestSystemImport:
    async def test_import_empty_payload(self, client: AsyncClient) -> None:
        """Import with no data returns zero counts."""
        resp = await client.post(
            "/api/v1/system/import",
            json={"version": "1.0", "templates": [], "devices": []},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["templates_created"] == 0
        assert data["devices_created"] == 0

    async def test_import_invalid_version(self, client: AsyncClient) -> None:
        """Import with unsupported version returns 422."""
        resp = await client.post(
            "/api/v1/system/import",
            json={"version": "99.0", "templates": []},
        )
        assert resp.status_code == 422

    async def test_import_template(self, client: AsyncClient) -> None:
        """Import creates a new template."""
        payload = {
            "version": "1.0",
            "templates": [
                {
                    "name": "Imported Meter",
                    "protocol": "modbus_tcp",
                    "description": "Imported",
                    "is_builtin": False,
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
                        }
                    ],
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["templates_created"] == 1

        # Verify template exists
        resp = await client.get("/api/v1/templates")
        names = [t["name"] for t in resp.json()["data"]]
        assert "Imported Meter" in names

    async def test_import_skips_builtin_templates(self, client: AsyncClient) -> None:
        """Import skips templates marked as built-in."""
        payload = {
            "version": "1.0",
            "templates": [
                {
                    "name": "Should Be Skipped",
                    "protocol": "modbus_tcp",
                    "is_builtin": True,
                    "registers": [
                        {
                            "name": "v",
                            "address": 0,
                            "function_code": 4,
                            "data_type": "float32",
                            "byte_order": "big_endian",
                            "scale_factor": 1.0,
                            "sort_order": 0,
                        }
                    ],
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        data = resp.json()["data"]
        assert data["templates_skipped"] == 1
        assert data["templates_created"] == 0

    async def test_import_device_with_template(self, client: AsyncClient) -> None:
        """Import creates template and device together."""
        payload = {
            "version": "1.0",
            "templates": [
                {
                    "name": "Import Template",
                    "protocol": "modbus_tcp",
                    "is_builtin": False,
                    "registers": [
                        {
                            "name": "voltage",
                            "address": 0,
                            "function_code": 4,
                            "data_type": "float32",
                            "byte_order": "big_endian",
                            "scale_factor": 1.0,
                            "sort_order": 0,
                        }
                    ],
                }
            ],
            "devices": [
                {
                    "name": "Import Device",
                    "template_name": "Import Template",
                    "slave_id": 10,
                    "port": 502,
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["templates_created"] == 1
        assert data["devices_created"] == 1

    async def test_import_device_unknown_template_fails(self, client: AsyncClient) -> None:
        """Import fails if device references nonexistent template."""
        payload = {
            "version": "1.0",
            "devices": [
                {
                    "name": "Orphan Device",
                    "template_name": "NonexistentTemplate",
                    "slave_id": 99,
                    "port": 502,
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        assert resp.status_code == 422

    async def test_import_simulation_configs(self, client: AsyncClient) -> None:
        """Import creates simulation configs for devices."""
        payload = {
            "version": "1.0",
            "templates": [
                {
                    "name": "SimTemplate",
                    "protocol": "modbus_tcp",
                    "is_builtin": False,
                    "registers": [
                        {
                            "name": "voltage",
                            "address": 0,
                            "function_code": 4,
                            "data_type": "float32",
                            "byte_order": "big_endian",
                            "scale_factor": 1.0,
                            "sort_order": 0,
                        }
                    ],
                }
            ],
            "devices": [
                {
                    "name": "SimDevice",
                    "template_name": "SimTemplate",
                    "slave_id": 20,
                    "port": 502,
                }
            ],
            "simulation_configs": [
                {
                    "device_name": "SimDevice",
                    "register_name": "voltage",
                    "data_mode": "static",
                    "mode_params": {"value": 230.0},
                    "is_enabled": True,
                    "update_interval_ms": 1000,
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["simulation_configs_set"] == 1

    async def test_roundtrip_export_import(self, client: AsyncClient) -> None:
        """Export then import produces identical system state."""
        # Create template + device + simulation config
        template = await _create_template(client)
        device = await _create_device(client, template["id"])
        await client.put(
            f"/api/v1/devices/{device['id']}/simulation",
            json={
                "configs": [
                    {
                        "register_name": "voltage",
                        "data_mode": "random",
                        "mode_params": {"base": 230.0, "amplitude": 5.0},
                        "is_enabled": True,
                        "update_interval_ms": 500,
                    }
                ]
            },
        )

        # Export
        resp = await client.get("/api/v1/system/export")
        export_data = resp.json()

        # Delete everything (device first due to FK)
        await client.delete(f"/api/v1/devices/{device['id']}")
        await client.delete(f"/api/v1/templates/{template['id']}")

        # Import back
        resp = await client.post("/api/v1/system/import", json=export_data)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["templates_created"] >= 1
        assert data["devices_created"] == 1
        assert data["simulation_configs_set"] == 1


class TestSystemImportEdgeCases:
    async def test_import_updates_existing_template(self, client: AsyncClient) -> None:
        """Import updates template if name already exists."""
        await _create_template(client)

        payload = {
            "version": "1.0",
            "templates": [
                {
                    "name": "Export Test Meter",
                    "protocol": "modbus_tcp",
                    "description": "Updated via import",
                    "is_builtin": False,
                    "registers": [
                        {
                            "name": "current",
                            "address": 10,
                            "function_code": 4,
                            "data_type": "float32",
                            "byte_order": "big_endian",
                            "scale_factor": 1.0,
                            "unit": "A",
                            "sort_order": 0,
                        }
                    ],
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["templates_updated"] == 1
        assert data["templates_created"] == 0

    async def test_import_updates_existing_device(self, client: AsyncClient) -> None:
        """Import updates device if (slave_id, port) already exists."""
        template = await _create_template(client)
        await _create_device(client, template["id"])

        payload = {
            "version": "1.0",
            "devices": [
                {
                    "name": "Updated Device",
                    "template_name": "Export Test Meter",
                    "slave_id": 1,
                    "port": 502,
                    "description": "Updated via import",
                }
            ],
        }
        resp = await client.post("/api/v1/system/import", json=payload)
        data = resp.json()["data"]
        assert data["devices_updated"] == 1
        assert data["devices_created"] == 0
