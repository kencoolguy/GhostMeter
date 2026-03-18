"""Integration tests for anomaly injection and schedule API routes."""

import uuid

from httpx import AsyncClient


TEMPLATE_PAYLOAD = {
    "name": "Anomaly Test Meter",
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
        {
            "name": "current",
            "address": 2,
            "function_code": 4,
            "data_type": "float32",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "A",
            "sort_order": 1,
        },
    ],
}


async def _create_device(client: AsyncClient) -> tuple[str, str]:
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    tid = resp.json()["data"]["id"]
    resp = await client.post(
        "/api/v1/devices",
        json={"template_id": tid, "name": "Anomaly Dev", "slave_id": 20},
    )
    assert resp.status_code == 201
    did = resp.json()["data"]["id"]
    return tid, did


class TestRealTimeAnomaly:
    async def test_inject_and_get(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        resp = await client.post(
            f"/api/v1/devices/{did}/anomaly",
            json={
                "register_name": "voltage",
                "anomaly_type": "spike",
                "anomaly_params": {"multiplier": 3.0, "probability": 0.5},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["anomaly_type"] == "spike"

        resp = await client.get(f"/api/v1/devices/{did}/anomaly")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    async def test_remove_specific(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        await client.post(
            f"/api/v1/devices/{did}/anomaly",
            json={"register_name": "voltage", "anomaly_type": "data_loss", "anomaly_params": {}},
        )
        await client.post(
            f"/api/v1/devices/{did}/anomaly",
            json={"register_name": "current", "anomaly_type": "data_loss", "anomaly_params": {}},
        )
        resp = await client.delete(f"/api/v1/devices/{did}/anomaly/voltage")
        assert resp.status_code == 200

        resp = await client.get(f"/api/v1/devices/{did}/anomaly")
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["register_name"] == "current"

    async def test_clear_all(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        await client.post(
            f"/api/v1/devices/{did}/anomaly",
            json={"register_name": "voltage", "anomaly_type": "data_loss", "anomaly_params": {}},
        )
        resp = await client.delete(f"/api/v1/devices/{did}/anomaly")
        assert resp.status_code == 200

        resp = await client.get(f"/api/v1/devices/{did}/anomaly")
        assert resp.json()["data"] == []

    async def test_invalid_anomaly_type(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        resp = await client.post(
            f"/api/v1/devices/{did}/anomaly",
            json={"register_name": "voltage", "anomaly_type": "invalid", "anomaly_params": {}},
        )
        assert resp.status_code == 422

    async def test_spike_missing_params(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        resp = await client.post(
            f"/api/v1/devices/{did}/anomaly",
            json={"register_name": "voltage", "anomaly_type": "spike", "anomaly_params": {}},
        )
        assert resp.status_code == 422


class TestAnomalySchedules:
    async def test_set_and_get_schedules(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        payload = {
            "schedules": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "spike",
                    "anomaly_params": {"multiplier": 3.0, "probability": 0.5},
                    "trigger_after_seconds": 300,
                    "duration_seconds": 60,
                },
            ],
        }
        resp = await client.put(f"/api/v1/devices/{did}/anomaly/schedules", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["register_name"] == "voltage"

        resp = await client.get(f"/api/v1/devices/{did}/anomaly/schedules")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    async def test_replace_schedules(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        payload1 = {
            "schedules": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "data_loss",
                    "anomaly_params": {},
                    "trigger_after_seconds": 100,
                    "duration_seconds": 30,
                },
            ],
        }
        await client.put(f"/api/v1/devices/{did}/anomaly/schedules", json=payload1)

        payload2 = {
            "schedules": [
                {
                    "register_name": "current",
                    "anomaly_type": "flatline",
                    "anomaly_params": {"value": 0.0},
                    "trigger_after_seconds": 200,
                    "duration_seconds": 60,
                },
            ],
        }
        resp = await client.put(f"/api/v1/devices/{did}/anomaly/schedules", json=payload2)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["register_name"] == "current"

    async def test_overlapping_schedules_rejected(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        payload = {
            "schedules": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "data_loss",
                    "anomaly_params": {},
                    "trigger_after_seconds": 100,
                    "duration_seconds": 60,
                },
                {
                    "register_name": "voltage",
                    "anomaly_type": "spike",
                    "anomaly_params": {"multiplier": 2.0, "probability": 1.0},
                    "trigger_after_seconds": 130,
                    "duration_seconds": 60,
                },
            ],
        }
        resp = await client.put(f"/api/v1/devices/{did}/anomaly/schedules", json=payload)
        assert resp.status_code == 422

    async def test_invalid_register_name(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        payload = {
            "schedules": [
                {
                    "register_name": "nonexistent",
                    "anomaly_type": "data_loss",
                    "anomaly_params": {},
                    "trigger_after_seconds": 100,
                    "duration_seconds": 30,
                },
            ],
        }
        resp = await client.put(f"/api/v1/devices/{did}/anomaly/schedules", json=payload)
        assert resp.status_code == 422

    async def test_delete_schedules(self, client: AsyncClient) -> None:
        _, did = await _create_device(client)
        payload = {
            "schedules": [
                {
                    "register_name": "voltage",
                    "anomaly_type": "data_loss",
                    "anomaly_params": {},
                    "trigger_after_seconds": 100,
                    "duration_seconds": 30,
                },
            ],
        }
        await client.put(f"/api/v1/devices/{did}/anomaly/schedules", json=payload)

        resp = await client.delete(f"/api/v1/devices/{did}/anomaly/schedules")
        assert resp.status_code == 200

        resp = await client.get(f"/api/v1/devices/{did}/anomaly/schedules")
        assert resp.json()["data"] == []

    async def test_nonexistent_device(self, client: AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/devices/{fake_id}/anomaly/schedules")
        assert resp.status_code == 404
