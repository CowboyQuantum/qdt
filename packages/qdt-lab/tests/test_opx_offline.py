"""OPX1000 driver without a server (L0): the QM config and the QUA programs it builds pass qm-qua's own
validation, and the host-side shaping (integration → volts, per-shot difference, reduction) is exact.
The conformance suite runs the driver on the instrument under `-m hardware` (QDT_OPX_ADDRESS)."""

import json

import numpy as np
import pytest

qm = pytest.importorskip("qm")

from qdt_lab.drivers.qm import opx1000
from qdt_lab.drivers.qm.opx1000 import Opx1000, _RunSource
from qdt_lab.experiment import QuaEmitter
from qdt_schemas.activity import (
    SequencerParameter,
    SequencerProgram,
    SequencerResult,
    SequencerStage,
    SweepAxis,
    SymbolBinding,
)
from qdt_schemas.pulse import Affine, Difference, Measure, PulseSequence, Step, Symbol, Wait
from qdt_schemas.stand import ChannelMap

CHANNELS = (
    ChannelMap(logical="P2_pulse", instrument="opx", channel="ao1", quantity="voltage"),
    ChannelMap(logical="sensor", instrument="opx", channel="ai1", quantity="voltage"),
)


class _FakeQM:
    def __init__(self, config):
        self.config = config

    def compile(self, program):
        return "compiled"


class _FakeQMM:
    def open_qm(self, config, close_other_machines=True):
        return _FakeQM(config)


def chopped_program(logical: bool = False) -> SequencerProgram:
    """The emitted stage; with `logical`, written in the stand's logical names and keyed by them, as
    `compile_sweep` hands it to the driver (the driver maps them to its ports)."""
    ao, ai = ("P2_pulse", "sensor") if logical else ("ao1", "ai1")
    v, t = Symbol(name="v_P2", unit="V"), Symbol(name="t_hold", unit="ns")
    seq = PulseSequence(
        name="chop",
        body=(
            Step(channel=ao, level=v, duration=t),
            Measure(channel=ai, duration=1000, result="I_on"),
            Step(channel=ao, level=Affine(symbol=v, offset=0.002), duration=200),
            Wait(duration=100),
            Measure(channel=ai, duration=1000, result="I_off"),
            Difference(result="dI", a="I_on", b="I_off"),
        ),
    )
    stage = SequencerStage(
        instrument="opx",
        axes=("P2",),
        sequence=seq,
        bindings=(
            SymbolBinding(symbol="v_P2", axis="P2"),
            SymbolBinding(symbol="t_hold", value=500),
        ),
        shots=3,
        reduce={"I_on": "mean", "I_off": "mean", "dI": "mean"},
    )
    axes = {"P2": SweepAxis(name="P2", channel=ao, start=0.0, stop=0.1, num=11)}
    keyed = {(c.logical if logical else c.channel): c for c in CHANNELS}
    program, _ = QuaEmitter().emit(stage, axes, keyed)
    return program


@pytest.fixture(scope="module", autouse=True)
def _offline():
    qm.QuantumMachinesManager.set_capabilities_offline()


def test_an_emitted_stage_compiles_to_a_valid_qua_program_and_config():
    opx = Opx1000(_FakeQMM(), CHANNELS)
    compiled = opx.compile(chopped_program())
    config = opx._qm.config
    assert sorted(config["elements"]) == ["el_ai1", "el_ao1", "el_ao1_wave"]
    assert config["elements"]["el_ao1"]["sticky"]["analog"] is True
    script = qm.generate_qua_script(compiled.plan["qua"], config)  # validates program + config
    for needle in (
        "declare_input_stream",
        "measure('readout_1000'",
        "ramp_to_zero",
        "amplitude_scale",
    ):
        assert needle in script


def test_the_conformance_program_compiles_and_shapes_its_flat_index():
    flat = SequencerProgram(
        backend="qua",
        body=json.dumps({"kind": "flat_index"}),
        parameters=(
            SequencerParameter(name="n_lines", unit=""),
            SequencerParameter(name="n_points", unit=""),
        ),
        results=(
            SequencerResult(name="data", dims=("n_lines", "n_points"), dtype="int64", unit=""),
        ),
    )
    opx = Opx1000(_FakeQMM(), ())
    compiled = opx.compile(flat)
    qm.generate_qua_script(compiled.plan["qua"], opx._qm.config)
    out = _RunSource(opx, compiled, {"n_lines": 3, "n_points": 4}, None).results(
        {"data": np.arange(12)}
    )
    np.testing.assert_array_equal(out["data"], np.arange(12).reshape(3, 4))


def test_per_shot_values_become_volts_differences_and_means():
    opx = Opx1000(_FakeQMM(), CHANNELS)
    compiled = opx.compile(chopped_program())
    params = {p.name: 0 for p in compiled.program.parameters} | {"n_P2": 11, "shots": 3}
    on, off = np.linspace(0, 1, 33), np.linspace(0, 1, 33) * 0.5
    raw = lambda volts: volts * 1000 / opx1000.INTEGRATION_TO_VOLTS
    out = _RunSource(opx, compiled, params, None).results({"I_on": raw(on), "I_off": raw(off)})
    np.testing.assert_allclose(out["I_on"], on.reshape(11, 3).mean(-1))
    np.testing.assert_allclose(out["dI"], (on - off).reshape(11, 3).mean(-1))


def test_refuses_what_the_lf_fem_cannot_run():
    opx = Opx1000(_FakeQMM(), CHANNELS)
    with pytest.raises(ValueError, match="backend 'qua'"):
        opx.compile(chopped_program().model_copy(update={"backend": "simulated"}))
    with pytest.raises(ValueError, match="ao1..8"):
        Opx1000(
            _FakeQMM(),
            (ChannelMap(logical="x", instrument="opx", channel="ao9", quantity="voltage"),),
        )
    with pytest.raises(ValueError, match="carries volts"):
        Opx1000(
            _FakeQMM(),
            (ChannelMap(logical="x", instrument="opx", channel="ai1", quantity="current"),),
        )
    with pytest.raises(ValueError, match="multiple of 4"):
        opx1000._cycles_ns(1001, "measure")


def test_a_stage_in_logical_channel_names_compiles_onto_the_declared_ports():
    """Bench, 2026-10-14: the compiler names channels as the stand does ('P2_pulse'), the driver knows
    ports ('ao1'); a real run failed with "OPX channel 'P2_pulse' is not 'ao<p>'" until this mapping."""
    opx = Opx1000(_FakeQMM(), CHANNELS)
    compiled = opx.compile(chopped_program(logical=True))
    assert sorted(opx._qm.config["elements"]) == ["el_ai1", "el_ao1", "el_ao1_wave"]
    script = qm.generate_qua_script(compiled.plan["qua"], opx._qm.config)
    assert "el_ao1" in script and "P2_pulse" not in script


def test_the_waveform_element_is_not_sticky_and_the_stage_element_is():
    """A looped waveform on a sticky element accumulates its last sample every repetition (bench,
    2026-10-14: a sine railed within a second); `play` uses a non-sticky twin, stages keep sticky."""
    opx = Opx1000(_FakeQMM(), CHANNELS)
    opx.compile(chopped_program())
    elements = opx._qm.config["elements"]
    assert elements["el_ao1"]["sticky"]["analog"] is True
    assert "sticky" not in elements["el_ao1_wave"]
    assert elements["el_ao1_wave"]["singleInput"] == elements["el_ao1"]["singleInput"]


# --- marker lines: the scope's trigger and the DAC's list advance (ADR 0063, 0064) -------------------

LINED = (
    *CHANNELS,
    ChannelMap(logical="scope_trigger", instrument="opx", channel="do1", quantity="voltage"),
    ChannelMap(logical="dac_trigger", instrument="opx", channel="do2", quantity="voltage"),
)


def paced_program(lines: bool = True, triggered: bool = True) -> SequencerProgram:
    """A stepped axis the OPX advances on do2, a shot of a step and a scope capture triggered on do1."""
    from qdt_lab.experiment import TriggeredStep
    from qdt_schemas.pulse import Capture

    seq = PulseSequence(
        name="step response",
        body=(
            Step(channel="P2_pulse", level=0.1, duration=2000),
            Capture(channel="scope1", duration=10_000, num=200, result="trace"),
        ),
    )
    stage = SequencerStage(instrument="opx", sequence=seq, shots=2)
    axes = {
        "V": SweepAxis(name="V", channel="P1", start=0.0, stop=1.0, num=5, stepping="triggered")
    }
    keyed = {c.logical: c for c in LINED}
    program, _ = QuaEmitter().emit(
        stage,
        axes,
        keyed,
        triggered=TriggeredStep(axis="V", lines=("dac_trigger",), settle_ns=50_000)
        if triggered
        else None,
        lines={"scope1": "scope_trigger"} if lines else {},
    )
    return program


def test_marker_lines_are_digital_outputs_with_their_own_elements_and_the_program_plays_them():
    opx = Opx1000(_FakeQMM(), LINED)
    compiled = opx.compile(paced_program())
    config = opx._qm.config
    assert config["controllers"]["con1"]["fems"][1]["digital_outputs"] == {1: {}, 2: {}}
    assert config["elements"]["trig_do1"]["digitalInputs"]["marker"]["port"] == ("con1", 1, 1)
    assert config["pulses"]["marker"] == {
        "operation": "control",
        "length": opx1000.MARKER_NS,
        "digital_marker": "ON",
    }
    assert "el_scope1" not in config["elements"]  # the scope is not an OPX element
    script = qm.generate_qua_script(compiled.plan["qua"], config)  # validates program + config
    assert script.count("play('marker', 'trig_do2')") == 1  # at the top of the triggered loop
    assert script.count("play('marker', 'trig_do1')") == 1  # at the capture
    assert "wait(2500," in script  # the capture window, 10 µs in clock cycles
    assert "wait(12500," in script  # the settle, 50 µs
    assert [p.name for p in compiled.program.parameters][:1] == ["n_V"]


def test_a_capture_without_a_line_compiles_and_the_shot_still_waits_out_the_window():
    """The interim of ADR 0063: the scope triggers itself; the shot's timeline is unchanged."""
    opx = Opx1000(_FakeQMM(), CHANNELS)
    compiled = opx.compile(paced_program(lines=False, triggered=False))
    script = qm.generate_qua_script(compiled.plan["qua"], opx._qm.config)
    assert "marker" not in script and "wait(2500," in script


def test_a_line_must_be_a_digital_output():
    bad = (
        *CHANNELS,
        ChannelMap(logical="scope_trigger", instrument="opx", channel="ao2", quantity="voltage"),
    )
    program = paced_program(lines=True, triggered=False)
    with pytest.raises(ValueError, match="is an ao, not an do"):
        Opx1000(_FakeQMM(), bad).compile(program)
