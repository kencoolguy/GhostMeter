import json

from httpx import AsyncClient

TEMPLATE_PAYLOAD = {
    "name": "Test Meter",
    "protocol": "modbus_tcp",
    "description": "A test template",
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


async def create_template(client: AsyncClient, payload: dict | None = None) -> dict:
    """Helper to create a template and return the response data."""
    response = await client.post(
        "/api/v1/templates", json=payload or TEMPLATE_PAYLOAD
    )
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    return body["data"]


class TestCreateTemplate:
    async def test_create_template_success(self, client: AsyncClient) -> None:
        data = await create_template(client)
        assert data["name"] == "Test Meter"
        assert len(data["registers"]) == 2
        assert data["is_builtin"] is False

    async def test_create_template_validates_empty_registers(
        self, client: AsyncClient,
    ) -> None:
        payload = {**TEMPLATE_PAYLOAD, "registers": []}
        response = await client.post("/api/v1/templates", json=payload)
        assert response.status_code == 422

    async def test_create_template_validates_invalid_data_type(
        self, client: AsyncClient,
    ) -> None:
        payload = {
            **TEMPLATE_PAYLOAD,
            "registers": [{**TEMPLATE_PAYLOAD["registers"][0], "data_type": "invalid"}],
        }
        response = await client.post("/api/v1/templates", json=payload)
        assert response.status_code == 422

    async def test_create_template_validates_address_overlap(
        self, client: AsyncClient,
    ) -> None:
        payload = {
            **TEMPLATE_PAYLOAD,
            "registers": [
                {**TEMPLATE_PAYLOAD["registers"][0], "address": 0},
                {**TEMPLATE_PAYLOAD["registers"][1], "name": "overlap", "address": 1},
            ],
        }
        response = await client.post("/api/v1/templates", json=payload)
        assert response.status_code == 422
        assert "overlap" in response.json()["detail"].lower()

    async def test_create_template_duplicate_name(
        self, client: AsyncClient,
    ) -> None:
        await create_template(client)
        response = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
        assert response.status_code == 422
        assert "already exists" in response.json()["detail"]


class TestListTemplates:
    async def test_list_templates_empty(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/templates")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == []

    async def test_list_templates_with_data(self, client: AsyncClient) -> None:
        await create_template(client)
        response = await client.get("/api/v1/templates")
        body = response.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["register_count"] == 2


class TestGetTemplate:
    async def test_get_template_success(self, client: AsyncClient) -> None:
        created = await create_template(client)
        response = await client.get(f"/api/v1/templates/{created['id']}")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["name"] == "Test Meter"
        assert len(body["data"]["registers"]) == 2

    async def test_get_template_not_found(self, client: AsyncClient) -> None:
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/v1/templates/{fake_id}")
        assert response.status_code == 404
        assert response.json()["error_code"] == "TEMPLATE_NOT_FOUND"


class TestUpdateTemplate:
    async def test_update_template_success(self, client: AsyncClient) -> None:
        created = await create_template(client)
        update_payload = {
            **TEMPLATE_PAYLOAD,
            "name": "Updated Meter",
            "registers": [TEMPLATE_PAYLOAD["registers"][0]],
        }
        response = await client.put(
            f"/api/v1/templates/{created['id']}", json=update_payload
        )
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["name"] == "Updated Meter"
        assert len(body["data"]["registers"]) == 1


class TestDeleteTemplate:
    async def test_delete_template_success(self, client: AsyncClient) -> None:
        created = await create_template(client)
        response = await client.delete(f"/api/v1/templates/{created['id']}")
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Verify deleted
        response = await client.get(f"/api/v1/templates/{created['id']}")
        assert response.status_code == 404

    async def test_delete_template_not_found(self, client: AsyncClient) -> None:
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await client.delete(f"/api/v1/templates/{fake_id}")
        assert response.status_code == 404


class TestCloneTemplate:
    async def test_clone_template_default_name(self, client: AsyncClient) -> None:
        created = await create_template(client)
        response = await client.post(f"/api/v1/templates/{created['id']}/clone")
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["name"] == "Copy of Test Meter"
        assert body["data"]["is_builtin"] is False
        assert len(body["data"]["registers"]) == 2

    async def test_clone_template_custom_name(self, client: AsyncClient) -> None:
        created = await create_template(client)
        response = await client.post(
            f"/api/v1/templates/{created['id']}/clone",
            json={"new_name": "My Clone"},
        )
        assert response.status_code == 201
        assert response.json()["data"]["name"] == "My Clone"


class TestExportImport:
    async def test_export_template(self, client: AsyncClient) -> None:
        created = await create_template(client)
        response = await client.get(f"/api/v1/templates/{created['id']}/export")
        assert response.status_code == 200
        assert "attachment" in response.headers.get("content-disposition", "")
        export_data = response.json()
        assert "id" not in export_data
        assert export_data["name"] == "Test Meter"
        assert len(export_data["registers"]) == 2
        for reg in export_data["registers"]:
            assert "id" not in reg

    async def test_import_template(self, client: AsyncClient) -> None:
        import_data = {
            "name": "Imported Meter",
            "protocol": "modbus_tcp",
            "registers": [TEMPLATE_PAYLOAD["registers"][0]],
        }
        response = await client.post(
            "/api/v1/templates/import",
            files={"file": ("template.json", json.dumps(import_data), "application/json")},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["data"]["name"] == "Imported Meter"

    async def test_import_template_name_conflict(self, client: AsyncClient) -> None:
        await create_template(client)
        import_data = {**TEMPLATE_PAYLOAD}
        response = await client.post(
            "/api/v1/templates/import",
            files={"file": ("template.json", json.dumps(import_data), "application/json")},
        )
        assert response.status_code == 422
        assert "already exists" in response.json()["detail"]
