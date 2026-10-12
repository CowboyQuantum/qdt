"""LevelSense conformance, on a (LevelSource, LevelSense) loopback pair. Test names are the spec."""

from qdt_lab.protocols import LevelSense, LevelSource


def test_backends_satisfy_protocols(level_loopback):
    source, sense = level_loopback
    assert isinstance(source, LevelSource)
    assert isinstance(sense, LevelSense)


def test_sense_follows_source_within_tolerance(level_loopback):
    source, sense = level_loopback
    source.set("ch00", 0.250)
    assert abs(sense.sense("ch00") - 0.250) < 1e-3


def test_channels_are_independent(level_loopback):
    source, sense = level_loopback
    source.set("ch00", 0.5)
    source.set("ch01", -0.5)
    assert abs(sense.sense("ch00") - 0.5) < 1e-3
    assert abs(sense.sense("ch01") + 0.5) < 1e-3
