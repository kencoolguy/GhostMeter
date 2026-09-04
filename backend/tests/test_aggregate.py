"""Unit tests for the aggregate data-mode helpers (issue #95)."""

import uuid
from types import SimpleNamespace

import pytest

from app.simulation.aggregate import (
    DeviceDirectory,
    find_cycle,
    format_cycle,
    resolve_sources,
)


def _directory(*names: str) -> tuple[DeviceDirectory, dict[str, uuid.UUID]]:
    directory = DeviceDirectory()
    ids: dict[str, uuid.UUID] = {}
    for name in names:
        device_id = uuid.uuid4()
        ids.setdefault(name, device_id)
        directory.by_id[device_id] = SimpleNamespace(id=device_id, name=name)
        directory.by_name.setdefault(name, []).append(device_id)
    return directory, ids


class TestDeviceDirectoryResolve:
    def test_resolves_by_name(self):
        directory, ids = _directory("PM-01", "PM-02")
        assert directory.resolve("PM-01") == ids["PM-01"]

    def test_resolves_by_uuid_string(self):
        directory, ids = _directory("PM-01")
        assert directory.resolve(str(ids["PM-01"])) == ids["PM-01"]

    def test_unknown_name_raises(self):
        directory, _ = _directory("PM-01")
        with pytest.raises(ValueError, match="does not match any device"):
            directory.resolve("PM-99")

    def test_unknown_uuid_raises(self):
        directory, _ = _directory("PM-01")
        with pytest.raises(ValueError, match="does not match any device"):
            directory.resolve(str(uuid.uuid4()))

    def test_ambiguous_name_raises(self):
        directory, _ = _directory("PM", "PM")
        with pytest.raises(ValueError, match="ambiguous"):
            directory.resolve("PM")

    def test_resolve_sources_strict_reraises(self):
        directory, _ = _directory("PM-01")
        with pytest.raises(ValueError):
            resolve_sources(directory, ["PM-01", "nope"], strict=True)

    def test_resolve_sources_lenient_drops_unknown(self):
        directory, ids = _directory("PM-01")
        assert resolve_sources(directory, ["PM-01", "nope"], strict=False) == [ids["PM-01"]]


class TestFindCycle:
    def test_no_cycle(self):
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        deps = {a: {b, c}, b: {c}}
        assert find_cycle(deps, a) is None

    def test_self_reference(self):
        a = uuid.uuid4()
        assert find_cycle({a: {a}}, a) == [a, a]

    def test_two_node_cycle(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        cycle = find_cycle({a: {b}, b: {a}}, a)
        assert cycle == [a, b, a]

    def test_cycle_reachable_but_not_through_start(self):
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        cycle = find_cycle({a: {b}, b: {c}, c: {b}}, a)
        assert cycle == [b, c, b]

    def test_diamond_is_not_a_cycle(self):
        a, b, c, d = (uuid.uuid4() for _ in range(4))
        assert find_cycle({a: {b, c}, b: {d}, c: {d}}, a) is None

    def test_format_cycle_uses_names(self):
        directory, ids = _directory("MVCB", "PM-01")
        text = format_cycle([ids["MVCB"], ids["PM-01"], ids["MVCB"]], directory)
        assert text == "MVCB → PM-01 → MVCB"
