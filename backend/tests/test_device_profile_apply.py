"""Tests for profile auto-apply on device creation."""

import uuid

from httpx import AsyncClient


TEMPLATE_PAYLOAD = {
    "name": "Apply Test Meter",
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
        "data_mode": "static",
        "mode_params": {"value": 10},
    },
]


async def _setup(client: AsyncClient) -> tuple[str, str]:
    """Create template + default profile, return (template_id, profile_id)."""
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    template_id = resp.json()["data"]["id"]

    resp = await client.post("/api/v1/simulation-profiles", json={
        "template_id": template_id,
        "name": "Default",
        "is_default": True,
        "configs": PROFILE_CONFIGS,
    })
    profile_id = resp.json()["data"]["id"]
    return template_id, profile_id


class TestAutoApplyDefaultProfile:
    async def test_device_gets_default_profile_configs(
        self, client: AsyncClient,
    ) -> None:
        """Creating a device without profile_id auto-applies default profile."""
        template_id, _ = await _setup(client)
        resp = await client.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "Auto Device",
            "slave_id": 1,
        })
        assert resp.status_code == 201
        device_id = resp.json()["data"]["id"]

        # Check simulation configs were created
        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert resp.status_code == 200
        configs = resp.json()["data"]
        assert len(configs) == 2
        names = {c["register_name"] for c in configs}
        assert names == {"voltage", "current"}

    async def test_explicit_null_skips_profile(
        self, client: AsyncClient,
    ) -> None:
        """Passing profile_id=null explicitly skips profile apply."""
        template_id, _ = await _setup(client)
        resp = await client.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "No Profile Device",
            "slave_id": 2,
            "profile_id": None,
        })
        assert resp.status_code == 201
        device_id = resp.json()["data"]["id"]

        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert resp.json()["data"] == []

    async def test_specific_profile_id_applied(
        self, client: AsyncClient,
    ) -> None:
        """Passing a specific profile_id applies that profile."""
        template_id, profile_id = await _setup(client)

        # Create a second non-default profile
        resp = await client.post("/api/v1/simulation-profiles", json={
            "template_id": template_id,
            "name": "Custom",
            "configs": [
                {
                    "register_name": "voltage",
                    "data_mode": "static",
                    "mode_params": {"value": 230},
                },
            ],
        })
        custom_id = resp.json()["data"]["id"]

        resp = await client.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "Custom Profile Device",
            "slave_id": 3,
            "profile_id": custom_id,
        })
        assert resp.status_code == 201
        device_id = resp.json()["data"]["id"]

        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        configs = resp.json()["data"]
        assert len(configs) == 1
        assert configs[0]["register_name"] == "voltage"
        assert configs[0]["data_mode"] == "static"

    async def test_nonexistent_profile_id_returns_404(
        self, client: AsyncClient,
    ) -> None:
        """Passing a nonexistent profile_id returns 404."""
        template_id, _ = await _setup(client)
        resp = await client.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "Bad Profile Device",
            "slave_id": 4,
            "profile_id": str(uuid.uuid4()),
        })
        assert resp.status_code == 404

    async def test_no_default_profile_creates_device_without_configs(
        self, client: AsyncClient,
    ) -> None:
        """If no default profile exists and profile_id absent, device has no configs."""
        resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD | {"name": "No Default Meter"})
        template_id = resp.json()["data"]["id"]

        resp = await client.post("/api/v1/devices", json={
            "template_id": template_id,
            "name": "No Default Device",
            "slave_id": 5,
        })
        assert resp.status_code == 201
        device_id = resp.json()["data"]["id"]

        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert resp.json()["data"] == []


class TestBatchCreateWithProfile:
    async def test_batch_create_applies_default(
        self, client: AsyncClient,
    ) -> None:
        template_id, _ = await _setup(client)
        resp = await client.post("/api/v1/devices/batch", json={
            "template_id": template_id,
            "slave_id_start": 10,
            "slave_id_end": 12,
        })
        assert resp.status_code == 201
        devices = resp.json()["data"]
        assert len(devices) == 3

        # Check first device has configs
        device_id = devices[0]["id"]
        resp = await client.get(f"/api/v1/devices/{device_id}/simulation")
        assert len(resp.json()["data"]) == 2
