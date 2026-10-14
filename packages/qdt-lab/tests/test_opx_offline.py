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


def chopped_program() -> SequencerProgram:
    v, t = Symbol(name="v_P2", unit="V"), Symbol(name="t_hold", unit="ns")
    seq = PulseSequence(
        name="chop",
        body=(
            Step(channel="ao1", level=v, duration=t),
            Measure(channel="ai1", duration=1000, result="I_on"),
            Step(channel="ao1", level=Affine(symbol=v, offset=0.002), duration=200),
            Wait(duration=100),
            Measure(channel="ai1", duration=1000, result="I_off"),
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
    axes = {"P2": SweepAxis(name="P2", channel="ao1", start=0.0, stop=0.1, num=11)}
    program, _ = QuaEmitter().emit(stage, axes, {c.channel: c for c in CHANNELS})
    return program


@pytest.fixture(scope="module", autouse=True)
def _offline():
    qm.QuantumMachinesManager.set_capabilities_offline()


def test_an_emitted_stage_compiles_to_a_valid_qua_program_and_config():
    opx = Opx1000(_FakeQMM(), CHANNELS)
    compiled = opx.compile(chopped_program())
    config = opx._qm.config
    assert sorted(config["elements"]) == ["el_ai1", "el_ao1"]
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
