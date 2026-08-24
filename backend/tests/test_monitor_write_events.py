"""The monitor snapshot must carry per-device write-event summaries."""

from uuid import uuid4

from app.services.monitor_service import MonitorService
from app.simulation import write_tracker


def test_build_write_events_payload_with_events():
    svc = MonitorService()
    dev = uuid4()
    write_tracker.clear_all()
    write_tracker.record(
        dev, operation="Write Register", address=4, values=["1234"], register_name="sp"
    )

    payload = svc.build_write_events_payload(dev)

    assert payload["unread"] == 1
    assert payload["latest"]["operation"] == "Write Register"
    assert payload["latest"]["address"] == 4
    assert payload["latest"]["values"] == ["1234"]
    assert payload["latest"]["register_name"] == "sp"
    assert isinstance(payload["latest"]["timestamp"], str)


def test_build_write_events_payload_empty():
    svc = MonitorService()
    dev = uuid4()
    write_tracker.clear_all()
    payload = svc.build_write_events_payload(dev)
    assert payload == {"unread": 0, "latest": None}
