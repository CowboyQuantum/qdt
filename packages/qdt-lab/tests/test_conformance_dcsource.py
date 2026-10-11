"""DCSource conformance. Test names are the spec; drivers must pass these unchanged."""

from qdt_lab.protocols import DCSource


def test_backend_satisfies_protocol(dc_source):
    assert isinstance(dc_source, DCSource)


def test_set_voltage_then_read_returns_within_tolerance(dc_source):
    dc_source.set_voltage("ch00", 1.000)
    assert abs(dc_source.get_voltage("ch00") - 1.000) < 1e-3


def test_channels_are_independent(dc_source):
    dc_source.set_voltage("ch00", 0.5)
    dc_source.set_voltage("ch01", -0.5)
    assert abs(dc_source.get_voltage("ch00") - 0.5) < 1e-3
    assert abs(dc_source.get_voltage("ch01") + 0.5) < 1e-3
