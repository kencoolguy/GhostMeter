"""Unit tests for the in-memory write tracker."""

from uuid import uuid4

from app.simulation.write_tracker import WriteTracker


def test_record_and_get_events_newest_first():
    t = WriteTracker()
    dev = uuid4()
    t.record(dev, operation="Write Register", address=10, values=["111"], register_name="setpoint")
    t.record(dev, operation="Write Registers", address=20, values=["1", "2"], register_name=None)

    events = t.get_events(dev)
    assert [e.address for e in events] == [20, 10]  # newest first
    assert events[1].register_name == "setpoint"
    assert events[0].values == ["1", "2"]
    assert events[0].operation == "Write Registers"


def test_unread_increments_and_mark_read_resets():
    t = WriteTracker()
    dev = uuid4()
    assert t.get_unread_count(dev) == 0
    t.record(dev, operation="Write Register", address=1, values=["1"], register_name=None)
    t.record(dev, operation="Write Register", address=2, values=["2"], register_name=None)
    assert t.get_unread_count(dev) == 2
    t.mark_read(dev)
    assert t.get_unread_count(dev) == 0
    # buffer retained after mark_read
    assert len(t.get_events(dev)) == 2


def test_ring_buffer_caps_at_max():
    t = WriteTracker()
    dev = uuid4()
    for i in range(60):
        t.record(dev, operation="Write Register", address=i, values=[str(i)], register_name=None)
    events = t.get_events(dev)
    assert len(events) == 50  # MAX_EVENTS_PER_DEVICE
    assert events[0].address == 59  # newest kept
    assert events[-1].address == 10  # oldest 10 dropped


def test_latest_returns_most_recent_or_none():
    t = WriteTracker()
    dev = uuid4()
    assert t.latest(dev) is None
    t.record(dev, operation="Write Register", address=7, values=["7"], register_name="x")
    assert t.latest(dev).address == 7


def test_clear_removes_device_state():
    t = WriteTracker()
    dev = uuid4()
    t.record(dev, operation="Write Register", address=1, values=["1"], register_name=None)
    t.clear(dev)
    assert t.get_events(dev) == []
    assert t.get_unread_count(dev) == 0
    assert t.latest(dev) is None


def test_values_are_copied_not_aliased():
    t = WriteTracker()
    dev = uuid4()
    src = ["1", "2"]
    t.record(dev, operation="Write Registers", address=0, values=src, register_name=None)
    src.append("3")
    assert t.get_events(dev)[0].values == ["1", "2"]
