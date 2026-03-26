"""Tests for batch device start/stop/delete operations."""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

TEMPLATE_PAYLOAD = {
    "name": "Batch-Test-Meter",
    "protocol": "modbus_tcp",
    "description": "Template for batch ops test",
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


async def _create_template(client: AsyncClient) -> dict:
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    return resp.json()["data"]


async def _create_device(
    client: AsyncClient, template_id: str, slave_id: int,
) -> dict:
    resp = await client.post("/api/v1/devices", json={
        "name": f"batch-dev-{slave_id}",
        "template_id": template_id,
        "slave_id": slave_id,
        "port": 502,
    })
    assert resp.status_code == 201
    return resp.json()["data"]


async def _setup_devices(client: AsyncClient, count: int = 3) -> list[dict]:
    """Create template and N devices, return device list."""
    template = await _create_template(client)
    devices = []
    for i in range(1, count + 1):
        d = await _create_device(client, template["id"], i)
        devices.append(d)
    return devices


class TestBatchStart:
    async def test_batch_start_selected(self, client: AsyncClient):
        """Start specific devices by IDs."""
        devices = await _setup_devices(client, 3)
        ids = [devices[0]["id"], devices[1]["id"]]

        resp = await client.post("/api/v1/devices/batch/start", json={
            "device_ids": ids,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success_count"] == 2
        assert data["skipped_count"] == 0

    async def test_batch_start_all(self, client: AsyncClient):
        """Empty device_ids starts all stopped devices."""
        devices = await _setup_devices(client, 3)

        resp = await client.post("/api/v1/devices/batch/start", json={
            "device_ids": [],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success_count"] == 3

    async def test_batch_start_skips_running(self, client: AsyncClient):
        """Already-running devices are skipped."""
        devices = await _setup_devices(client, 2)

        # Start first device individually
        await client.post(f"/api/v1/devices/{devices[0]['id']}/start")

        # Batch start both
        resp = await client.post("/api/v1/devices/batch/start", json={
            "device_ids": [d["id"] for d in devices],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success_count"] == 1
        assert data["skipped_count"] == 1


class TestBatchStop:
    async def test_batch_stop_selected(self, client: AsyncClient):
        """Stop specific running devices."""
        devices = await _setup_devices(client, 3)

        # Start all first
        await client.post("/api/v1/devices/batch/start", json={"device_ids": []})

        # Stop first two
        resp = await client.post("/api/v1/devices/batch/stop", json={
            "device_ids": [devices[0]["id"], devices[1]["id"]],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success_count"] == 2

    async def test_batch_stop_all(self, client: AsyncClient):
        """Empty device_ids stops all running devices."""
        devices = await _setup_devices(client, 3)

        # Start all
        await client.post("/api/v1/devices/batch/start", json={"device_ids": []})

        # Stop all
        resp = await client.post("/api/v1/devices/batch/stop", json={
            "device_ids": [],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success_count"] == 3

    async def test_batch_stop_skips_stopped(self, client: AsyncClient):
        """Already-stopped devices are skipped."""
        devices = await _setup_devices(client, 2)

        # Start only first
        await client.post(f"/api/v1/devices/{devices[0]['id']}/start")

        # Batch stop both
        resp = await client.post("/api/v1/devices/batch/stop", json={
            "device_ids": [d["id"] for d in devices],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success_count"] == 1
        assert data["skipped_count"] == 1


class TestBatchDelete:
    async def test_batch_delete_stopped(self, client: AsyncClient):
        """Delete stopped devices."""
        devices = await _setup_devices(client, 3)
        ids = [d["id"] for d in devices]

        resp = await client.post("/api/v1/devices/batch/delete", json={
            "device_ids": ids,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success_count"] == 3

        # Verify all gone
        resp = await client.get("/api/v1/devices")
        assert len(resp.json()["data"]) == 0

    async def test_batch_delete_skips_running(self, client: AsyncClient):
        """Running devices are skipped during batch delete."""
        devices = await _setup_devices(client, 2)

        # Start first device
        await client.post(f"/api/v1/devices/{devices[0]['id']}/start")

        # Try to delete both
        resp = await client.post("/api/v1/devices/batch/delete", json={
            "device_ids": [d["id"] for d in devices],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success_count"] == 1
        assert data["skipped_count"] == 1

    async def test_batch_delete_requires_ids(self, client: AsyncClient):
        """Empty device_ids is rejected for batch delete."""
        resp = await client.post("/api/v1/devices/batch/delete", json={
            "device_ids": [],
        })
        assert resp.status_code == 422
