"""Compiler + executor over simulated backends: dry-run count, order, shape; reproducibility; rejections.

The flat-index SimulatedSequencer makes stage results checkable exactly; the loopback
SimulatedLevelSense makes sensed values equal the applied level on the same vendor channel.
"""

import itertools
from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_lab.experiment import Executor, SimulatedEmitter, build_backends, compile_sweep
from qdt_lab.experiment.execute import expected_points
from qdt_lab.simulated import SimulatedLevelSense, SimulatedLevelSource, SimulatedSequencer
from qdt_lab.stream import Source, assemble
from qdt_schemas.activity import (
    ExecutionPlan,
    ParameterBinding,
    SensedLevel,
    SequencerParameter,
    SequencerProgram,
    SequencerResult,
    SequencerStage,
    SweepAxis,
    SweepDefinition,
    SymbolBinding,
)
from qdt_schemas.pulse import Measure, PulseSequence, Step, Symbol
from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig

T0 = datetime(2026, 10, 12, tzinfo=UTC)
EMITTERS = {"simulated": SimulatedEmitter()}


def stand() -> StandConfig:
    return StandConfig(
        stand_id="sim",
        instruments=(
            InstrumentConfig(id="dac", backend="simulated", capabilities=("level_source",)),
            InstrumentConfig(id="meter", backend="simulated", capabilities=("level_sense",)),
            InstrumentConfig(id="seq", backend="simulated", capabilities=("sequencer",)),
        ),
        channels=(
            ChannelMap(logical="gate_R", instrument="dac", channel="ch00", quantity="voltage"),
            ChannelMap(
                logical="gate_L_dc",
                instrument="dac",
                channel="ch01",
                quantity="voltage",
                settle_s=0.01,
            ),
            ChannelMap(logical="sensor_dc", instrument="meter", channel="ch00", quantity="current"),
            ChannelMap(logical="gate_L_p", instrument="seq", channel="ao1", quantity="voltage"),
            ChannelMap(logical="sensor", instrument="seq", channel="ai1", quantity="voltage"),
        ),
    )


class SpyLevelSource(SimulatedLevelSource):
    def __init__(self):
        super().__init__()
        self.calls: list[tuple[str, float]] = []

    def set(self, channel, value):
        self.calls.append((channel, value))
        super().set(channel, value)


def backends():
    dac = SpyLevelSource()
    return {"dac": dac, "meter": SimulatedLevelSense(follow=dac), "seq": SimulatedSequencer()}


def stepped_definition(repeats=1) -> SweepDefinition:
    return SweepDefinition(
        name="dc map",
        axes=(
            SweepAxis(name="gate_R", channel="gate_R", start=-0.5, stop=0.5, num=4),
            SweepAxis(name="gate_L_dc", channel="gate_L_dc", start=-1.0, stop=0.0, num=5),
        ),
        sensed=(SensedLevel(name="I_dc", channel="sensor_dc"),),
        repeats=repeats,
    )


def pixel() -> PulseSequence:
    return PulseSequence(
        name="pixel",
        body=(
            Step(channel="gate_L_p", level=Symbol(name="v_L", unit="V"), duration=100),
            Measure(channel="sensor", duration=1000, result="I_sens"),
        ),
    )


def staged_definition(shots=1, reduce=None, repeats=1) -> SweepDefinition:
    return SweepDefinition(
        name="stability",
        axes=(
            SweepAxis(name="gate_R", channel="gate_R", start=-0.5, stop=0.5, num=3),
            SweepAxis(name="gate_L", channel="gate_L_p", start=-1.0, stop=0.0, num=4),
        ),
        stage=SequencerStage(
            instrument="seq",
            axes=("gate_L",),
            sequence=pixel(),
            bindings=(SymbolBinding(symbol="v_L", axis="gate_L"),),
            shots=shots,
            reduce=reduce or {},
        ),
        repeats=repeats,
    )


# --- stepped sweep -------------------------------------------------------------------------------


def test_stepped_sweep_count_order_shape():
    plan = compile_sweep(stepped_definition(), stand(), EMITTERS, created_at=T0)
    b = backends()
    sleeps = []
    frames = list(Executor(plan, b, sleep=sleeps.append).run().frames())
    out = assemble(plan.dataset, frames)
    assert out["I_dc"].shape == (4, 5)
    assert expected_points(plan) == 20
    # row-major: outer gate_R changes 4 times, inner gate_L_dc 20 times
    expected = []
    for i, j in itertools.product(range(4), range(5)):
        if j == 0:
            expected.append(("ch00", -0.5 + i / 3))
        expected.append(("ch01", -1.0 + j / 4))
    assert [c[0] for c in b["dac"].calls] == [c[0] for c in expected]
    np.testing.assert_allclose([c[1] for c in b["dac"].calls], [c[1] for c in expected])
    # the loopback sense reads dac ch00 == the current gate_R value
    np.testing.assert_allclose(
        out["I_dc"].values, np.repeat(np.linspace(-0.5, 0.5, 4)[:, None], 5, 1)
    )
    assert len(frames) == 4 and all(len(f.chunk.region) == 2 for f in frames)
    assert frames[-1].chunk.final and not frames[0].chunk.final
    assert sleeps == [0.01] * 20, "settle honoured on every change of the channel that declares it"


def test_repeats_add_an_outer_dimension_and_are_never_averaged():
    plan = compile_sweep(stepped_definition(repeats=2), stand(), EMITTERS, created_at=T0)
    assert [d.name for d in plan.dataset.dims] == ["repeat", "gate_R", "gate_L_dc"]
    frames = list(Executor(plan, backends()).run().frames())
    assert len(frames) == 8
    assert {f.chunk.region[0].start for f in frames} == {0, 1}
    out = assemble(plan.dataset, frames)
    np.testing.assert_allclose(out["I_dc"].values[0], out["I_dc"].values[1])


def test_unbounded_repeats_stream_until_stopped():
    plan = compile_sweep(stepped_definition(repeats=None), stand(), EMITTERS, created_at=T0)
    assert plan.dataset.dims[0].size is None
    assert expected_points(plan) is None
    frames = list(itertools.islice(Executor(plan, backends()).run().frames(), 10))
    assert len(frames) == 10 and frames[-1].chunk.region[0].start == 2


# --- staged sweep --------------------------------------------------------------------------------


def test_staged_sweep_emits_program_and_fills_declared_dataset():
    plan = compile_sweep(staged_definition(), stand(), EMITTERS, created_at=T0)
    p = plan.stage_program
    assert p.backend == "simulated"
    assert [x.name for x in p.parameters] == ["n_gate_L", "v_L_start", "v_L_step", "shots"]
    assert p.results[0].dims == ("n_gate_L",) and p.results[0].unit == "V"
    assert [d.name for d in plan.dataset.dims] == ["gate_R", "gate_L"]
    assert plan.dataset.data_vars[0].dims == ("gate_R", "gate_L")
    assert {c.logical: c.role for c in plan.channels} == {
        "gate_R": "level_source",
        "gate_L_p": "sequencer",
        "sensor": "sequencer",
    }
    src = Executor(plan, backends()).run()
    assert isinstance(src, Source)
    frames = list(src.frames())
    out = assemble(plan.dataset, frames)
    np.testing.assert_array_equal(out["I_sens"].values, np.tile(np.arange(4.0), (3, 1)))
    assert len(frames) == 3, "one whole inner line per stepped point"
    assert frames[-1].chunk.final
    assert expected_points(plan) == 12


def test_stage_parameters_resolve_through_scale():
    plan = compile_sweep(staged_definition(), stand(), EMITTERS, created_at=T0)
    from qdt_lab.experiment.execute import resolve_parameters

    values = resolve_parameters(plan.stage_program, plan.stage_parameters, plan, {"gate_R": -0.5})
    assert values == {"n_gate_L": 4, "v_L_start": -1_000_000, "v_L_step": 333_333, "shots": 1}


def test_kept_shots_add_a_shot_dimension():
    plan = compile_sweep(staged_definition(shots=5), stand(), EMITTERS, created_at=T0)
    assert [d.name for d in plan.dataset.dims] == ["gate_R", "gate_L", "shot"]
    assert plan.dataset.data_vars[0].dims == ("gate_R", "gate_L", "shot")
    out = assemble(plan.dataset, Executor(plan, backends()).run().frames())
    assert out["I_sens"].shape == (3, 4, 5)
    assert expected_points(plan) == 60


def test_reduced_shots_leave_a_parameter_and_an_attr():
    plan = compile_sweep(
        staged_definition(shots=5, reduce={"I_sens": "mean"}), stand(), EMITTERS, created_at=T0
    )
    assert [d.name for d in plan.dataset.dims] == ["gate_R", "gate_L"]
    assert plan.dataset.attrs["shots"] == 5 and plan.dataset.attrs["I_sens.reduced"] == "shot:mean"
    out = assemble(plan.dataset, Executor(plan, backends()).run().frames())
    assert out["I_sens"].shape == (3, 4)


def test_stepped_axis_symbol_becomes_a_per_run_parameter():
    d = staged_definition()
    seq = PulseSequence(
        name="pixel",
        body=(
            Step(channel="gate_L_p", level=Symbol(name="v_L", unit="V"), duration=100),
            Step(channel="gate_L_p", level=Symbol(name="v_R", unit="V"), duration=100),
            Measure(channel="sensor", duration=1000, result="I_sens"),
        ),
    )
    d = d.model_copy(
        update={
            "stage": d.stage.model_copy(
                update={
                    "sequence": seq,
                    "bindings": (
                        SymbolBinding(symbol="v_L", axis="gate_L"),
                        SymbolBinding(symbol="v_R", axis="gate_R"),
                    ),
                }
            )
        }
    )
    plan = compile_sweep(d, stand(), EMITTERS, created_at=T0)
    binding = next(b for b in plan.stage_parameters if b.parameter == "v_R")
    assert binding.source == "axis_value"
    out = assemble(plan.dataset, Executor(plan, backends()).run().frames())
    assert out["I_sens"].shape == (3, 4)


def test_program_escape_hatch_runs():
    program = SequencerProgram(
        backend="qua",
        body="# hand-written",
        parameters=(SequencerParameter(name="n", unit=""), SequencerParameter(name="k", unit="")),
        results=(SequencerResult(name="data", dims=("n",), dtype="int64", unit=""),),
    )
    d = SweepDefinition(
        name="raw",
        axes=(SweepAxis(name="g", channel="gate_L_p", start=0, stop=1, num=6),),
        stage=SequencerStage(
            instrument="seq",
            axes=("g",),
            program=program,
            parameters=(
                ParameterBinding(parameter="n", source="axis_num", axis="g"),
                ParameterBinding(parameter="k", source="const", value=3),
            ),
        ),
    )
    plan = compile_sweep(d, stand(), created_at=T0)
    out = assemble(plan.dataset, Executor(plan, backends()).run().frames())
    np.testing.assert_array_equal(out["data"].values, np.arange(6))


# --- reproducibility and round trips ------------------------------------------------------------


def test_compile_is_reproducible_up_to_identity():
    a = compile_sweep(staged_definition(), stand(), EMITTERS, plan_id="p", created_at=T0)
    b = compile_sweep(staged_definition(), stand(), EMITTERS, plan_id="p", created_at=T0)
    assert a == b
    assert ExecutionPlan.model_validate_json(a.model_dump_json()) == a


# --- rejections ----------------------------------------------------------------------------------


def test_compile_rejects_missing_capability():
    d = stepped_definition().model_copy(
        update={"sensed": (SensedLevel(name="I_dc", channel="gate_L_p"),)}
    )
    with pytest.raises(ValueError, match="lacks capability"):
        compile_sweep(d, stand(), EMITTERS)


def test_compile_rejects_stage_channel_on_another_instrument():
    d = staged_definition()
    d = d.model_copy(
        update={
            "axes": (
                d.axes[0],
                SweepAxis(name="gate_L", channel="gate_L_dc", start=-1.0, stop=0.0, num=4),
            )
        }
    )
    with pytest.raises(ValueError, match="not a channel of"):
        compile_sweep(d, stand(), EMITTERS)


def test_compile_rejects_missing_emitter():
    with pytest.raises(ValueError, match="no emitter"):
        compile_sweep(staged_definition(), stand())


def test_executor_rejects_backend_without_the_protocol():
    plan = compile_sweep(stepped_definition(), stand(), EMITTERS)
    b = backends()
    b["meter"] = object()
    with pytest.raises(TypeError, match="LevelSense"):
        Executor(plan, b)


def test_build_backends_hands_each_factory_its_instrument_and_channels():
    stand = StandConfig(
        stand_id="s",
        instruments=(
            InstrumentConfig(id="dac", backend="simulated", capabilities=("level_source",)),
            InstrumentConfig(id="dmm", backend="simulated", capabilities=("level_sense",)),
        ),
        channels=(
            ChannelMap(logical="g", instrument="dac", channel="ch00", quantity="voltage"),
            ChannelMap(
                logical="i", instrument="dmm", channel="ch00", quantity="current", integration_s=0.1
            ),
        ),
    )
    seen = {}

    def factory(instrument, channels):
        seen[instrument.id] = channels
        return instrument.id

    assert build_backends(stand, {"simulated": factory}) == {"dac": "dac", "dmm": "dmm"}
    assert [c.logical for c in seen["dmm"]] == ["i"] and seen["dmm"][0].integration_s == 0.1
    with pytest.raises(ValueError, match="no backend factory"):
        build_backends(stand, {})
