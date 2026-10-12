"""LevelSource conformance. Test names are the spec; drivers must pass these unchanged."""

from qdt_lab.protocols import LevelSource


def test_backend_satisfies_protocol(level_source):
    assert isinstance(level_source, LevelSource)


def test_set_level_then_get_returns_within_tolerance(level_source):
    level_source.set("ch00", 1.000)
    assert abs(level_source.get("ch00") - 1.000) < 1e-3


def test_channels_are_independent(level_source):
    level_source.set("ch00", 0.5)
    level_source.set("ch01", -0.5)
    assert abs(level_source.get("ch00") - 0.5) < 1e-3
    assert abs(level_source.get("ch01") + 0.5) < 1e-3
