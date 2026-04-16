"""Tests for monitor_service snapshot aggregation."""
from httpx import AsyncClient

from app.services.monitor_service import monitor_service
from tests.test_devices import create_device, create_template


async def test_snapshot_includes_stopped_devices(client: AsyncClient) -> None:
    """Stopped devices must appear in monitor snapshot (not filtered out)."""
    tpl = await create_template(client)
    device = await create_device(client, tpl["id"], name="Stopped-Meter", slave_id=11)
    # Newly created devices default to status='stopped'

    snapshot = await monitor_service.get_snapshot()

    device_ids = [d["device_id"] for d in snapshot["devices"]]
    assert device["id"] in device_ids, "Stopped device should appear in snapshot"

    found = next(d for d in snapshot["devices"] if d["device_id"] == device["id"])
    assert found["status"] == "stopped"
