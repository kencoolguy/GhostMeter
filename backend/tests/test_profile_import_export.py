"""Tests for simulation profile import/export and blank template download."""

import json

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

TEMPLATE_PAYLOAD = {
    "name": "Export-Profile-Meter",
    "protocol": "modbus_tcp",
    "description": "Template for profile import/export test",
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


async def _create_template(client: AsyncClient) -> dict:
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["data"]


async def _create_profile(client: AsyncClient, template_id: str) -> dict:
    resp = await client.post("/api/v1/simulation-profiles", json={
        "template_id": template_id,
        "name": "Test Normal",
        "description": "Normal operation profile",
        "configs": [
            {
                "register_name": "voltage",
                "data_mode": "random",
                "mode_params": {"base": 230, "amplitude": 5},
                "is_enabled": True,
                "update_interval_ms": 1000,
            },
            {
                "register_name": "current",
                "data_mode": "static",
                "mode_params": {"value": 10},
                "is_enabled": True,
                "update_interval_ms": 2000,
            },
        ],
    })
    assert resp.status_code == 201
    return resp.json()["data"]


class TestExportProfile:
    async def test_export_profile(self, client: AsyncClient):
        """Export a profile as JSON file download."""
        template = await _create_template(client)
        profile = await _create_profile(client, template["id"])

        resp = await client.get(
            f"/api/v1/simulation-profiles/{profile['id']}/export"
        )
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]

        data = json.loads(resp.content)
        assert data["name"] == "Test Normal"
        assert data["description"] == "Normal operation profile"
        assert data["template_name"] == "Export-Profile-Meter"
        assert len(data["configs"]) == 2
        assert data["configs"][0]["register_name"] == "voltage"

    async def test_export_nonexistent_profile(self, client: AsyncClient):
        """Export a non-existent profile returns 404."""
        resp = await client.get(
            "/api/v1/simulation-profiles/00000000-0000-0000-0000-000000000000/export"
        )
        assert resp.status_code == 404


class TestBlankProfile:
    async def test_download_blank_profile(self, client: AsyncClient):
        """Download blank profile template with all registers as static."""
        template = await _create_template(client)

        resp = await client.get(
            f"/api/v1/simulation-profiles/template/{template['id']}"
        )
        assert resp.status_code == 200
        assert "attachment" in resp.headers["content-disposition"]
        assert "blank_profile" in resp.headers["content-disposition"]

        data = json.loads(resp.content)
        assert data["name"] == "My Profile"
        assert data["template_name"] == "Export-Profile-Meter"
        assert len(data["configs"]) == 2

        # All registers should be static with defaults
        for cfg in data["configs"]:
            assert cfg["data_mode"] == "static"
            assert cfg["is_enabled"] is True
            assert cfg["update_interval_ms"] == 1000

        # Register names should match template
        names = [c["register_name"] for c in data["configs"]]
        assert "voltage" in names
        assert "current" in names

    async def test_blank_profile_nonexistent_template(self, client: AsyncClient):
        """Blank profile for non-existent template returns 404."""
        resp = await client.get(
            "/api/v1/simulation-profiles/template/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404


class TestImportProfile:
    async def test_import_profile(self, client: AsyncClient):
        """Import a profile from JSON file."""
        template = await _create_template(client)

        profile_json = json.dumps({
            "name": "Imported Profile",
            "description": "From file",
            "template_name": "Export-Profile-Meter",
            "configs": [
                {
                    "register_name": "voltage",
                    "data_mode": "daily_curve",
                    "mode_params": {"base": 230, "amplitude": 10, "peak_hour": 14},
                    "is_enabled": True,
                    "update_interval_ms": 1000,
                },
                {
                    "register_name": "current",
                    "data_mode": "random",
                    "mode_params": {"base": 15, "amplitude": 3},
                    "is_enabled": True,
                    "update_interval_ms": 1000,
                },
            ],
        })

        resp = await client.post(
            f"/api/v1/simulation-profiles/import?template_id={template['id']}",
            files={"file": ("profile.json", profile_json, "application/json")},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Imported Profile"
        assert data["template_id"] == template["id"]
        assert len(data["configs"]) == 2

    async def test_import_invalid_json(self, client: AsyncClient):
        """Import with invalid JSON returns 422."""
        template = await _create_template(client)

        resp = await client.post(
            f"/api/v1/simulation-profiles/import?template_id={template['id']}",
            files={"file": ("bad.json", "not json{{{", "application/json")},
        )
        assert resp.status_code == 422

    async def test_import_empty_name(self, client: AsyncClient):
        """Import with empty name returns 422."""
        template = await _create_template(client)

        profile_json = json.dumps({
            "name": "",
            "configs": [
                {
                    "register_name": "voltage",
                    "data_mode": "static",
                    "mode_params": {},
                    "is_enabled": True,
                    "update_interval_ms": 1000,
                },
            ],
        })

        resp = await client.post(
            f"/api/v1/simulation-profiles/import?template_id={template['id']}",
            files={"file": ("profile.json", profile_json, "application/json")},
        )
        assert resp.status_code == 422

    async def test_roundtrip_export_import(self, client: AsyncClient):
        """Export a profile then import it as a new profile."""
        template = await _create_template(client)
        original = await _create_profile(client, template["id"])

        # Export
        resp = await client.get(
            f"/api/v1/simulation-profiles/{original['id']}/export"
        )
        exported = json.loads(resp.content)

        # Modify name to avoid conflict
        exported["name"] = "Imported Copy"

        # Import
        resp = await client.post(
            f"/api/v1/simulation-profiles/import?template_id={template['id']}",
            files={
                "file": ("profile.json", json.dumps(exported), "application/json")
            },
        )
        assert resp.status_code == 201
        imported = resp.json()["data"]
        assert imported["name"] == "Imported Copy"
        assert len(imported["configs"]) == len(original["configs"])

    async def test_import_blank_then_modify(self, client: AsyncClient):
        """Download blank template, modify, and import."""
        template = await _create_template(client)

        # Download blank
        resp = await client.get(
            f"/api/v1/simulation-profiles/template/{template['id']}"
        )
        blank = json.loads(resp.content)

        # Modify
        blank["name"] = "Custom Profile"
        blank["configs"][0]["data_mode"] = "random"
        blank["configs"][0]["mode_params"] = {"base": 220, "amplitude": 10}

        # Import
        resp = await client.post(
            f"/api/v1/simulation-profiles/import?template_id={template['id']}",
            files={
                "file": ("profile.json", json.dumps(blank), "application/json")
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Custom Profile"
