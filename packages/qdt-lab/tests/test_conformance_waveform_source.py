"""WaveformSource conformance. Test names are the spec; drivers must pass these unchanged."""

import numpy as np
import pytest

from qdt_lab.protocols import WaveformSource


def test_backend_satisfies_protocol(waveform_source):
    assert isinstance(waveform_source, WaveformSource)


def test_play_then_stop_does_not_raise(waveform_source):
    waveform_source.play("ch00", np.sin(np.linspace(0, 2 * np.pi, 1000)), 1e9)
    waveform_source.stop("ch00")
    waveform_source.stop("ch00")  # idempotent


def test_play_rejects_non_1d_waveform(waveform_source):
    with pytest.raises(ValueError):
        waveform_source.play("ch00", np.zeros((2, 10)), 1e9)


def test_play_rejects_non_positive_sample_rate(waveform_source):
    with pytest.raises(ValueError):
        waveform_source.play("ch00", np.zeros(10), 0.0)
