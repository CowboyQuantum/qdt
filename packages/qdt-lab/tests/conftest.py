"""Conformance parametrization: one fixture per capability, each listing its backends.

Register real backends here under the `hardware` marker as drivers land (see CLAUDE.md). Every
backend must pass the same tests unchanged.
"""

import pytest

from qdt_lab.simulated import (
    SimulatedLevelSense,
    SimulatedLevelSource,
    SimulatedSequencer,
    SimulatedWaveformSense,
    SimulatedWaveformSource,
)
from qdt_schemas.activity import SequencerParameter, SequencerProgram, SequencerResult
from qdt_schemas.stand import ChannelMap, InstrumentConfig

LEVEL_SOURCE_BACKENDS = [pytest.param(SimulatedLevelSource, id="simulated")]


@pytest.fixture(params=LEVEL_SOURCE_BACKENDS)
def level_source(request):
    return request.param()


def _simulated_loopback(sense_channels: tuple[ChannelMap, ...] = ()):
    source = SimulatedLevelSource.from_config(
        InstrumentConfig(id="src", backend="simulated", capabilities=("level_source",)), ()
    )
    sense = SimulatedLevelSense.from_config(
        InstrumentConfig(id="sense", backend="simulated", capabilities=("level_sense",)),
        sense_channels,
        follow=source,
    )
    return source, sense


# A (LevelSource, LevelSense) pair wired so the sense terminal reads what the source applies: the bench
# loopback of BENCH.md. Each entry builds the pair given the sense instrument's ChannelMaps, through the
# backends' factories (ADR 0021). Real pairs register here with their loopback tolerance.
LEVEL_LOOPBACK_BACKENDS = [pytest.param(_simulated_loopback, id="simulated")]


@pytest.fixture(params=LEVEL_LOOPBACK_BACKENDS)
def level_loopback_factory(request):
    return request.param


@pytest.fixture
def level_loopback(level_loopback_factory):
    return level_loopback_factory()


WAVEFORM_SOURCE_BACKENDS = [pytest.param(SimulatedWaveformSource, id="simulated")]


@pytest.fixture(params=WAVEFORM_SOURCE_BACKENDS)
def waveform_source(request):
    return request.param()


WAVEFORM_SENSE_BACKENDS = [pytest.param(lambda: SimulatedWaveformSense(seed=1), id="simulated")]


@pytest.fixture(params=WAVEFORM_SENSE_BACKENDS)
def waveform_sense(request):
    return request.param()


# The conformance program: a 2-D loop whose result is the flat loop index, as Probe 01 ran on the OPX
# (bench/probes/probe01/opx_probe.py). A real sequencer registers with its own body for that program.
FLAT_INDEX_PROGRAM = SequencerProgram(
    backend="qua",
    body="# conformance program: data[i, j] = i * n_points + j; see bench/probes/probe01/opx_probe.py",
    parameters=(
        SequencerParameter(name="n_lines", unit=""),
        SequencerParameter(name="n_points", unit=""),
        SequencerParameter(name="step", unit="V", scale=1e-6),
    ),
    results=(SequencerResult(name="data", dims=("n_lines", "n_points"), dtype="int64", unit=""),),
)

SEQUENCER_BACKENDS = [
    pytest.param(lambda: (SimulatedSequencer(), FLAT_INDEX_PROGRAM), id="simulated"),
]


@pytest.fixture(params=SEQUENCER_BACKENDS)
def sequencer_and_program(request):
    return request.param()
