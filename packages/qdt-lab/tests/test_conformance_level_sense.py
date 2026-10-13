"""LevelSense conformance, on a (LevelSource, LevelSense) loopback pair. Test names are the spec."""

import time

from qdt_lab.protocols import LevelSense, LevelSource
from qdt_schemas.stand import ChannelMap


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


def test_sense_honours_declared_integration_time(level_loopback_factory):
    aperture = 0.02
    source, sense = level_loopback_factory(
        (
            ChannelMap(
                logical="in",
                instrument="sense",
                channel="ch00",
                quantity="voltage",
                integration_s=aperture,
            ),
        )
    )
    source.set("ch00", 0.125)
    t0 = time.perf_counter()
    value = sense.sense("ch00")
    assert time.perf_counter() - t0 >= aperture
    assert abs(value - 0.125) < 1e-3
