"""Tests for monitor_service snapshot aggregation."""
import pytest
from httpx import AsyncClient

from app.services.monitor_service import monitor_service


async def _make_template(client: AsyncClient) -> dict:
    payload = {
        "name": "T-Stopped-Test",
        "protocol": "modbus_tcp",
        "registers": [
            {
                "name": "voltage", "address": 0, "function_code": 4,
                "data_type": "float32", "byte_order": "big_endian",
                "scale_factor": 1.0, "unit": "V", "description": "",
                "sort_order": 0,
            },
        ],
    }
    r = await client.post("/api/v1/templates", json=payload)
    assert r.status_code == 201
    return r.json()["data"]


async def _make_device(client: AsyncClient, template_id: str, name: str, slave_id: int) -> dict:
    r = await client.post(
        "/api/v1/devices",
        json={"template_id": template_id, "name": name, "slave_id": slave_id, "port": 5020},
    )
    assert r.status_code == 201
    return r.json()["data"]


@pytest.mark.asyncio
async def test_snapshot_includes_stopped_devices(client: AsyncClient) -> None:
    """Stopped devices must appear in monitor snapshot (not filtered out)."""
    tpl = await _make_template(client)
    device = await _make_device(client, tpl["id"], "Stopped-Meter", 11)
    # Newly created devices default to status='stopped'

    snapshot = await monitor_service.get_snapshot()

    device_ids = [d["device_id"] for d in snapshot["devices"]]
    assert device["id"] in device_ids, "Stopped device should appear in snapshot"

    found = next(d for d in snapshot["devices"] if d["device_id"] == device["id"])
    assert found["status"] == "stopped"
