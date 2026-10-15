"""WaveformSource conformance. Test names are the spec; drivers must pass these unchanged."""

import numpy as np
import pytest

from qdt_lab.protocols import WaveformSource


def test_backend_satisfies_protocol(waveform_source):
    assert isinstance(waveform_source, WaveformSource)


def test_play_then_stop_does_not_raise(waveform_source):
    # 0.1 V: inside every backend's output range (the OPX LF-FEM direct mode is ±0.5 V)
    waveform_source.play("ch00", 0.1 * np.sin(np.linspace(0, 2 * np.pi, 1000)), 1e9)
    waveform_source.stop("ch00")
    waveform_source.stop("ch00")  # idempotent


def test_play_rejects_non_1d_waveform(waveform_source):
    with pytest.raises(ValueError):
        waveform_source.play("ch00", np.zeros((2, 10)), 1e9)


def test_play_rejects_non_positive_sample_rate(waveform_source):
    with pytest.raises(ValueError):
        waveform_source.play("ch00", np.zeros(10), 0.0)


def test_a_second_play_on_a_channel_replaces_the_first(waveform_source):
    """`play` loops until `stop`; a new waveform on a playing channel takes over without an error and
    without a stop in between (the bench's pulse trains are swapped this way, BENCH.md L2)."""
    waveform_source.play("ch00", np.full(1000, 0.1), 1e9)
    waveform_source.play("ch00", np.linspace(0.0, 0.2, 1000), 1e9)
    waveform_source.stop("ch00")
