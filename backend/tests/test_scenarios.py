"""Tests for scenario CRUD and execution."""

from httpx import AsyncClient

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


async def create_template(client: AsyncClient) -> dict:
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["data"]


def make_scenario_payload(template_id: str) -> dict:
    return {
        "template_id": template_id,
        "name": "Test Scenario",
        "description": "A test scenario",
        "steps": [
            {
                "register_name": "voltage",
                "anomaly_type": "out_of_range",
                "anomaly_params": {"value": 0},
                "trigger_at_seconds": 0,
                "duration_seconds": 10,
                "sort_order": 0,
            },
            {
                "register_name": "current",
                "anomaly_type": "flatline",
                "anomaly_params": {"value": 0},
                "trigger_at_seconds": 5,
                "duration_seconds": 10,
                "sort_order": 1,
            },
        ],
    }


class TestScenarioCRUD:
    async def test_create_scenario(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        resp = await client.post("/api/v1/scenarios", json=payload)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Test Scenario"
        assert data["total_duration_seconds"] == 15  # max(0+10, 5+10)
        assert len(data["steps"]) == 2

    async def test_list_scenarios(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        await client.post("/api/v1/scenarios", json=payload)
        resp = await client.get("/api/v1/scenarios")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    async def test_list_scenarios_filter_by_template(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        await client.post("/api/v1/scenarios", json=payload)
        resp = await client.get(f"/api/v1/scenarios?template_id={template['id']}")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1
        # Non-existent template returns empty
        resp2 = await client.get("/api/v1/scenarios?template_id=00000000-0000-0000-0000-000000000000")
        assert resp2.status_code == 200
        assert len(resp2.json()["data"]) == 0

    async def test_get_scenario_detail(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        create_resp = await client.post("/api/v1/scenarios", json=payload)
        scenario_id = create_resp.json()["data"]["id"]
        resp = await client.get(f"/api/v1/scenarios/{scenario_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Test Scenario"
        assert len(data["steps"]) == 2

    async def test_update_scenario(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        create_resp = await client.post("/api/v1/scenarios", json=payload)
        scenario_id = create_resp.json()["data"]["id"]
        update_payload = {
            "name": "Updated Scenario",
            "description": "Updated",
            "steps": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "spike",
                    "anomaly_params": {"probability": 0.8, "multiplier": 1.5},
                    "trigger_at_seconds": 0,
                    "duration_seconds": 20,
                    "sort_order": 0,
                },
            ],
        }
        resp = await client.put(f"/api/v1/scenarios/{scenario_id}", json=update_payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Updated Scenario"
        assert data["total_duration_seconds"] == 20
        assert len(data["steps"]) == 1

    async def test_delete_scenario(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        create_resp = await client.post("/api/v1/scenarios", json=payload)
        scenario_id = create_resp.json()["data"]["id"]
        resp = await client.delete(f"/api/v1/scenarios/{scenario_id}")
        assert resp.status_code == 200
        # Verify gone
        resp2 = await client.get(f"/api/v1/scenarios/{scenario_id}")
        assert resp2.status_code == 404

    async def test_invalid_register_name_rejected(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = {
            "template_id": template["id"],
            "name": "Bad Scenario",
            "steps": [
                {
                    "register_name": "nonexistent_register",
                    "anomaly_type": "spike",
                    "anomaly_params": {},
                    "trigger_at_seconds": 0,
                    "duration_seconds": 10,
                },
            ],
        }
        resp = await client.post("/api/v1/scenarios", json=payload)
        assert resp.status_code == 422

    async def test_overlapping_steps_rejected(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = {
            "template_id": template["id"],
            "name": "Overlap Scenario",
            "steps": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "spike",
                    "anomaly_params": {},
                    "trigger_at_seconds": 0,
                    "duration_seconds": 20,
                },
                {
                    "register_name": "voltage",
                    "anomaly_type": "drift",
                    "anomaly_params": {},
                    "trigger_at_seconds": 10,
                    "duration_seconds": 15,
                },
            ],
        }
        resp = await client.post("/api/v1/scenarios", json=payload)
        assert resp.status_code == 422

    async def test_export_scenario(self, client: AsyncClient) -> None:
        template = await create_template(client)
        payload = make_scenario_payload(template["id"])
        create_resp = await client.post("/api/v1/scenarios", json=payload)
        scenario_id = create_resp.json()["data"]["id"]
        resp = await client.post(f"/api/v1/scenarios/{scenario_id}/export")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "Test Scenario"
        assert data["template_name"] == "Test Meter"
        assert len(data["steps"]) == 2

    async def test_import_scenario(self, client: AsyncClient) -> None:
        template = await create_template(client)
        import_payload = {
            "name": "Imported Scenario",
            "description": None,
            "template_name": "Test Meter",
            "steps": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "out_of_range",
                    "anomaly_params": {"value": 0},
                    "trigger_at_seconds": 0,
                    "duration_seconds": 10,
                },
            ],
        }
        resp = await client.post("/api/v1/scenarios/import", json=import_payload)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Imported Scenario"
        assert data["template_id"] == template["id"]
