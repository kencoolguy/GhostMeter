"""API tests for the write-events endpoints."""

import uuid

from httpx import AsyncClient

from app.simulation import write_tracker

TEMPLATE_PAYLOAD = {
    "name": "Write Test Meter",
    "protocol": "modbus_tcp",
    "registers": [
        {
            "name": "power_setpoint",
            "address": 4,
            "function_code": 3,
            "data_type": "uint16",
            "byte_order": "big_endian",
            "scale_factor": 1.0,
            "unit": "W",
            "description": "Setpoint",
            "sort_order": 0,
        },
    ],
}


async def _create_device(client: AsyncClient) -> str:
    """Create a template + device, return the device id (string UUID)."""
    resp = await client.post("/api/v1/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    template_id = resp.json()["data"]["id"]
    resp = await client.post(
        "/api/v1/devices",
        json={"template_id": template_id, "name": "Write Device", "slave_id": 11},
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


async def test_list_returns_events_newest_first_without_resetting_unread(
    client: AsyncClient,
):
    device_id = await _create_device(client)
    dev = uuid.UUID(device_id)  # write_tracker keys on UUID, as the endpoint does
    write_tracker.clear_all()
    write_tracker.record(
        dev, operation="Write Register", address=1, values=["10"], register_name="a"
    )
    write_tracker.record(
        dev, operation="Write Registers", address=2, values=["20", "30"], register_name=None
    )

    resp = await client.get(f"/api/v1/devices/{device_id}/write-events")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert [e["address"] for e in data] == [2, 1]  # newest first
    assert data[0]["values"] == ["20", "30"]
    # GET is pure: unread unchanged
    assert write_tracker.get_unread_count(dev) == 2


async def test_ack_resets_unread(client: AsyncClient):
    device_id = await _create_device(client)
    dev = uuid.UUID(device_id)
    write_tracker.clear_all()
    write_tracker.record(
        dev, operation="Write Register", address=1, values=["10"], register_name=None
    )
    assert write_tracker.get_unread_count(dev) == 1

    resp = await client.post(f"/api/v1/devices/{device_id}/write-events/ack")
    assert resp.status_code == 200
    assert resp.json()["data"]["unread"] == 0
    assert write_tracker.get_unread_count(dev) == 0


async def test_list_unknown_device_404(client: AsyncClient):
    resp = await client.get(f"/api/v1/devices/{uuid.uuid4()}/write-events")
    assert resp.status_code == 404
