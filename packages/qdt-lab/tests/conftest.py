"""Conformance parametrization: one fixture per capability, each listing its backends.

Every backend must pass the same tests unchanged. Each real driver is registered twice: on its SCPI
emulator (L0, CI) and on the instrument (`hardware` marker; the VISA address comes from an environment
variable and the test skips without it — addresses are never committed, rule 7):

    QDT_QDAC2_ADDRESS   QDAC-II          e.g. TCPIP::<host>::5025::SOCKET
    QDT_SMU_ADDRESS     Keithley 2400    e.g. TCPIP::<host>::5025::SOCKET or GPIB0::24::INSTR
    QDT_SCOPE_ADDRESS   InfiniiVision X  e.g. TCPIP::<host>::INSTR
    QDT_OPX_ADDRESS     OPX1000          QM host (cluster gateway)
"""

import os
import warnings
from typing import ClassVar

import pytest

from qdt_lab.drivers.keithley.k2400 import Keithley2400
from qdt_lab.drivers.keithley.k2400_emulator import emulated as k2400_emulated
from qdt_lab.drivers.keysight.infiniivision import InfiniiVisionX
from qdt_lab.drivers.keysight.infiniivision_emulator import emulated as infiniivision_emulated
from qdt_lab.drivers.qdevil.qdac2 import QDac2
from qdt_lab.drivers.qdevil.qdac2_emulator import emulated as qdac2_emulated
from qdt_lab.simulated import (
    SimulatedLevelSense,
    SimulatedLevelSource,
    SimulatedSequencer,
    SimulatedWaveformSense,
    SimulatedWaveformSource,
)
from qdt_schemas.activity import SequencerParameter, SequencerProgram, SequencerResult
from qdt_schemas.stand import ChannelMap, InstrumentConfig


@pytest.fixture
def wallclock_rate():
    """Check a measured rate against a design target. Strict by default; with QDT_WALLCLOCK_ADVISORY=1
    (CI's shared runners, ADR 0039) a rate below target only warns, and only one below half fails."""
    advisory = os.environ.get("QDT_WALLCLOCK_ADVISORY") == "1"

    def check(measured: float, target: float, what: str) -> None:
        if measured >= target:
            return
        floor = 0.5 * target if advisory else target
        assert measured >= floor, f"{what}: {measured:,.0f}/s is below {floor:,.0f}/s"
        warnings.warn(
            f"{what}: {measured:,.0f}/s is below the {target:,.0f}/s target (advisory)",
            stacklevel=2,
        )

    return check


def _address(var: str) -> str:
    address = os.environ.get(var)
    if not address:
        pytest.skip(f"set {var} to run against the instrument")
    return address


def _instrument(id: str, backend: str, capabilities: tuple[str, ...], var: str) -> InstrumentConfig:
    return InstrumentConfig(
        id=id, backend=backend, capabilities=capabilities, settings={"address": _address(var)}
    )


class _Renamed:
    """The suite's ch00/ch01 onto an instrument that numbers its channels from 1 (QDAC-II)."""

    _MAP: ClassVar[dict[str, str]] = {"ch00": "ch01", "ch01": "ch02"}

    def __init__(self, driver) -> None:
        self._d = driver

    def set(self, channel: str, value: float) -> None:
        self._d.set(self._MAP.get(channel, channel), value)

    def get(self, channel: str) -> float:
        return self._d.get(self._MAP.get(channel, channel))


def _qdac2_hardware():
    return _Renamed(
        QDac2.from_config(
            _instrument("dac0", "qdac2", ("level_source", "level_sense"), "QDT_QDAC2_ADDRESS"), ()
        )
    )


def _k2400_hardware(channels: tuple[ChannelMap, ...] = ()):
    return Keithley2400.from_config(
        _instrument("smu", "keithley2400", ("level_source", "level_sense"), "QDT_SMU_ADDRESS"),
        channels,
    )


# One SMU terminal is both source and sense: ch00 declared 'voltage' so sense reads the sourced level.
_SMU_LOOPBACK = (ChannelMap(logical="in", instrument="smu", channel="ch00", quantity="voltage"),)


def _smu_loopback(make):
    def factory(sense_channels: tuple[ChannelMap, ...] = ()):
        smu = make(sense_channels or _SMU_LOOPBACK)
        return smu, smu

    return factory


def _infiniivision_hardware():
    inst = _instrument("scope0", "infiniivision", ("waveform_sense",), "QDT_SCOPE_ADDRESS")
    ch = ChannelMap(logical="ch00", instrument="scope0", channel="1", quantity="voltage")
    return InfiniiVisionX.from_config(inst, (ch,))


LEVEL_SOURCE_BACKENDS = [
    pytest.param(SimulatedLevelSource, id="simulated"),
    pytest.param(lambda: _Renamed(qdac2_emulated()), id="qdac2-emulated"),
    pytest.param(lambda: k2400_emulated("2400"), id="k2400-emulated"),
    pytest.param(lambda: k2400_emulated("2450"), id="k2450-emulated"),
    pytest.param(_qdac2_hardware, id="qdac2", marks=pytest.mark.hardware),
    pytest.param(_k2400_hardware, id="k2400", marks=pytest.mark.hardware),
]


@pytest.fixture
def closing():
    """Backends built during a test; each is closed at teardown, last first. Real instruments need
    it: a Keithley 2450 accepts one raw-socket connection at a time and resets any second one, so a
    backend left open by one test breaks the next."""
    made: list[object] = []
    yield made
    seen: set[int] = set()
    for backend in reversed(made):
        if id(backend) in seen:
            continue
        seen.add(id(backend))
        close = getattr(backend, "close", None)
        if close is not None:
            close()


@pytest.fixture(params=LEVEL_SOURCE_BACKENDS)
def level_source(request, closing):
    backend = request.param()
    closing.append(backend)
    return backend


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
LEVEL_LOOPBACK_BACKENDS = [
    pytest.param(_simulated_loopback, id="simulated"),
    pytest.param(_smu_loopback(lambda ch: k2400_emulated("2400", ch)), id="k2400-emulated"),
    pytest.param(_smu_loopback(lambda ch: k2400_emulated("2450", ch)), id="k2450-emulated"),
    pytest.param(_smu_loopback(_k2400_hardware), id="k2400", marks=pytest.mark.hardware),
]


@pytest.fixture(params=LEVEL_LOOPBACK_BACKENDS)
def level_loopback_factory(request, closing):
    def factory(*args, **kwargs):
        pair = request.param(*args, **kwargs)
        closing.extend(pair)
        return pair

    return factory


@pytest.fixture
def level_loopback(level_loopback_factory):
    return level_loopback_factory()


def _opx_waveform_hardware(kind: str):
    """The OPX1000 as a WaveformSource (ch00 → ao1) or WaveformSense (ch00 → ai1), through the stand's
    logical-name resolution; the suite checks shapes and the declared grid, so no loopback is needed."""

    def make():
        from qdt_lab.drivers.qm.opx1000 import Opx1000

        inst = _instrument("opx", "qua", ("waveform_source", "waveform_sense"), "QDT_OPX_ADDRESS")
        inst = inst.model_copy(
            update={
                "settings": {
                    **inst.settings,
                    "fem": int(os.environ.get("QDT_OPX_FEM", "1")),
                    "output_mode": "direct",
                }
            }
        )
        port = "ao1" if kind == "source" else "ai1"
        return Opx1000.from_config(
            inst, (ChannelMap(logical="ch00", instrument="opx", channel=port, quantity="voltage"),)
        )

    return make


WAVEFORM_SOURCE_BACKENDS = [
    pytest.param(SimulatedWaveformSource, id="simulated"),
    pytest.param(_opx_waveform_hardware("source"), id="opx1000", marks=pytest.mark.hardware),
]


@pytest.fixture(params=WAVEFORM_SOURCE_BACKENDS)
def waveform_source(request, closing):
    backend = request.param()
    closing.append(backend)
    return backend


WAVEFORM_SENSE_BACKENDS = [
    pytest.param(lambda: SimulatedWaveformSense(seed=1), id="simulated"),
    pytest.param(infiniivision_emulated, id="infiniivision-emulated"),
    pytest.param(_infiniivision_hardware, id="infiniivision", marks=pytest.mark.hardware),
    pytest.param(_opx_waveform_hardware("sense"), id="opx1000", marks=pytest.mark.hardware),
]


@pytest.fixture(params=WAVEFORM_SENSE_BACKENDS)
def waveform_sense(request, closing):
    backend = request.param()
    closing.append(backend)
    return backend


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


def _opx_hardware():
    from qdt_lab.drivers.qm.opx1000 import Opx1000

    inst = _instrument("opx", "qua", ("sequencer",), "QDT_OPX_ADDRESS")
    program = FLAT_INDEX_PROGRAM.model_copy(update={"body": '{"kind": "flat_index"}'})
    return Opx1000.from_config(inst, ()), program


SEQUENCER_BACKENDS = [
    pytest.param(lambda: (SimulatedSequencer(), FLAT_INDEX_PROGRAM), id="simulated"),
    pytest.param(_opx_hardware, id="opx1000", marks=pytest.mark.hardware),
]


@pytest.fixture(params=SEQUENCER_BACKENDS)
def sequencer_and_program(request, closing):
    sequencer, program = request.param()
    closing.append(sequencer)
    return sequencer, program
