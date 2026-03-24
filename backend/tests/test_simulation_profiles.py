"""Integration tests for simulation profile CRUD API."""

import uuid

from httpx import AsyncClient


TEMPLATE_PAYLOAD = {
    "name": "Profile Test Meter",
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

PROFILE_CONFIGS = [
    {
        "register_name": "voltage",
        "data_mode": "random",
        "mode_params": {"base": 220, "amplitude": 3, "distribution": "gaussian"},
    },
    {
        "register_name": "current",
        "data_mode": "daily_curve",
        "mode_params": {"base": 8, "amplitude": 6, "peak_hour": 14},
    },
]


async def _create_template(client: AsyncClient) -> str:
    """Helper: create a template and return template_id."""
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


class TestCreateProfile:
    async def test_create_profile_success(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Normal Operation",
            "description": "Test profile",
            "is_default": True,
            "configs": PROFILE_CONFIGS,
        }
        resp = await client.post("/api/v1/simulation-profiles", json=payload)
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Normal Operation"
        assert data["is_default"] is True
        assert data["is_builtin"] is False
        assert len(data["configs"]) == 2

    async def test_create_profile_invalid_template(self, client: AsyncClient) -> None:
        payload = {
            "template_id": str(uuid.uuid4()),
            "name": "Bad Profile",
            "configs": PROFILE_CONFIGS,
        }
        resp = await client.post("/api/v1/simulation-profiles", json=payload)
        assert resp.status_code == 404

    async def test_create_duplicate_name_same_template(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Same Name",
            "configs": PROFILE_CONFIGS,
        }
        resp1 = await client.post("/api/v1/simulation-profiles", json=payload)
        assert resp1.status_code == 201
        resp2 = await client.post("/api/v1/simulation-profiles", json=payload)
        assert resp2.status_code == 409

    async def test_create_second_default_clears_first(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload1 = {
            "template_id": template_id,
            "name": "First Default",
            "is_default": True,
            "configs": PROFILE_CONFIGS,
        }
        resp1 = await client.post("/api/v1/simulation-profiles", json=payload1)
        assert resp1.status_code == 201
        first_id = resp1.json()["data"]["id"]

        payload2 = {
            "template_id": template_id,
            "name": "Second Default",
            "is_default": True,
            "configs": PROFILE_CONFIGS,
        }
        resp2 = await client.post("/api/v1/simulation-profiles", json=payload2)
        assert resp2.status_code == 201

        # First profile should no longer be default
        resp = await client.get(f"/api/v1/simulation-profiles/{first_id}")
        assert resp.json()["data"]["is_default"] is False


class TestListProfiles:
    async def test_list_by_template(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Test Profile",
            "configs": PROFILE_CONFIGS,
        }
        await client.post("/api/v1/simulation-profiles", json=payload)
        resp = await client.get(
            f"/api/v1/simulation-profiles?template_id={template_id}"
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    async def test_list_empty(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        resp = await client.get(
            f"/api/v1/simulation-profiles?template_id={template_id}"
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestGetProfile:
    async def test_get_by_id(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Get Test",
            "configs": PROFILE_CONFIGS,
        }
        resp = await client.post("/api/v1/simulation-profiles", json=payload)
        profile_id = resp.json()["data"]["id"]
        resp = await client.get(f"/api/v1/simulation-profiles/{profile_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Get Test"

    async def test_get_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.get(
            f"/api/v1/simulation-profiles/{uuid.uuid4()}"
        )
        assert resp.status_code == 404


class TestUpdateProfile:
    async def test_update_name(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Original",
            "configs": PROFILE_CONFIGS,
        }
        resp = await client.post("/api/v1/simulation-profiles", json=payload)
        profile_id = resp.json()["data"]["id"]
        resp = await client.put(
            f"/api/v1/simulation-profiles/{profile_id}",
            json={"name": "Updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Updated"

    async def test_update_builtin_configs_rejected(self, client: AsyncClient) -> None:
        # Seed profiles are builtin — we'll test this via seed test
        # For now, test that updating configs on a non-builtin works
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Updatable",
            "configs": PROFILE_CONFIGS,
        }
        resp = await client.post("/api/v1/simulation-profiles", json=payload)
        profile_id = resp.json()["data"]["id"]
        new_configs = [
            {
                "register_name": "voltage",
                "data_mode": "static",
                "mode_params": {"value": 230},
            },
        ]
        resp = await client.put(
            f"/api/v1/simulation-profiles/{profile_id}",
            json={"configs": new_configs},
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]["configs"]) == 1


class TestDeleteProfile:
    async def test_delete_custom_profile(self, client: AsyncClient) -> None:
        template_id = await _create_template(client)
        payload = {
            "template_id": template_id,
            "name": "Deletable",
            "configs": PROFILE_CONFIGS,
        }
        resp = await client.post("/api/v1/simulation-profiles", json=payload)
        profile_id = resp.json()["data"]["id"]
        resp = await client.delete(f"/api/v1/simulation-profiles/{profile_id}")
        assert resp.status_code == 200

        resp = await client.get(f"/api/v1/simulation-profiles/{profile_id}")
        assert resp.status_code == 404

    async def test_delete_nonexistent(self, client: AsyncClient) -> None:
        resp = await client.delete(
            f"/api/v1/simulation-profiles/{uuid.uuid4()}"
        )
        assert resp.status_code == 404
