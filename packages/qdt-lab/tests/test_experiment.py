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
    FixedLevel,
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
from qdt_schemas.pulse import Capture, Measure, PulseSequence, Step, Symbol
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


def test_build_backends_closes_what_it_built_when_a_later_factory_fails():
    stand = StandConfig(
        stand_id="s",
        instruments=(
            InstrumentConfig(id="dac", backend="good", capabilities=("level_source",)),
            InstrumentConfig(id="scope", backend="bad", capabilities=("waveform_sense",)),
        ),
        channels=(ChannelMap(logical="g", instrument="dac", channel="ch00", quantity="voltage"),),
    )
    closed = []

    class Backend:
        def close(self):
            closed.append("dac")

    def bad(instrument, channels):
        raise OSError("could not connect")

    with pytest.raises(RuntimeError, match="instrument 'scope' \\(bad\\) could not be built"):
        build_backends(stand, {"good": lambda i, c: Backend(), "bad": bad})
    assert closed == ["dac"], "the backend built before the failure is closed"


# --- captured waveforms (ADR 0047) ------------------------------------------------------------------


def scope_stand() -> StandConfig:
    return StandConfig(
        stand_id="scope",
        instruments=(
            InstrumentConfig(id="dac", backend="simulated", capabilities=("level_source",)),
            InstrumentConfig(id="meter", backend="simulated", capabilities=("level_sense",)),
            InstrumentConfig(id="scope", backend="simulated", capabilities=("waveform_sense",)),
        ),
        channels=(
            ChannelMap(logical="V", instrument="dac", channel="ch00", quantity="voltage"),
            ChannelMap(logical="I", instrument="meter", channel="ch00", quantity="current"),
            ChannelMap(logical="scope1", instrument="scope", channel="1", quantity="voltage"),
            ChannelMap(logical="scope2", instrument="scope", channel="2", quantity="voltage"),
        ),
    )


def capture(name="trace", channel="scope1", records=1, num=200):
    from qdt_schemas.activity import CapturedWaveform

    return CapturedWaveform(
        name=name, channel=channel, start_s=-1e-3, stop_s=9e-3, num=num, records=records
    )


def test_a_capture_alone_is_one_record_on_its_time_axis():
    from qdt_lab.simulated import SimulatedWaveformSense, exponential_decay

    plan = compile_sweep(SweepDefinition(name="droop", captured=(capture(),)), scope_stand())
    assert [(d.name, d.size) for d in plan.dataset.dims] == [("time", 200)]
    (coord,) = plan.dataset.coords
    assert (coord.name, coord.unit, coord.start, coord.stop, coord.num) == (
        "time",
        "s",
        -1e-3,
        9e-3,
        200,
    )
    assert [(v.name, v.dims, v.unit) for v in plan.dataset.data_vars] == [("trace", ("time",), "V")]
    assert [(c.logical, c.role) for c in plan.channels] == [("scope1", "waveform_sense")]
    assert plan.dataset.attrs["records"] == 1
    scope = SimulatedWaveformSense(noise=0.0, response=exponential_decay(2e-3, 0.2))
    frames = list(Executor(plan, {"scope": scope}).run().frames())
    assert len(frames) == 1 and frames[0].chunk.final
    assert [(s.dim, s.start, s.stop) for s in frames[0].chunk.region] == [("time", 0, 200)]
    out = assemble(plan.dataset, frames)
    t = np.linspace(-1e-3, 9e-3, 200)
    np.testing.assert_allclose(out["trace"].values, np.where(t >= 0, 0.2 * np.exp(-t / 2e-3), 0.0))


def test_captures_at_every_stepped_point_with_records_and_a_sensed_level():
    """Per stepped point: the level is set and settled, the level sensed, then each capture armed on
    its own (record, time) slab and re-keyed; `record` is a dimension only when records > 1."""
    from qdt_lab.experiment.execute import capture_slab
    from qdt_lab.simulated import SimulatedWaveformSense, low_pass_step

    definition = SweepDefinition(
        name="stepped droop",
        axes=(SweepAxis(name="V", channel="V", start=0.0, stop=1.0, num=3),),
        sensed=(SensedLevel(name="I", channel="I"),),
        captured=(capture(records=2), capture("ref", "scope2", records=2, num=50)),
    )
    plan = compile_sweep(definition, scope_stand())
    assert [(d.name, d.size) for d in plan.dataset.dims] == [
        ("V", 3),
        ("record", 2),
        ("trace_time", 200),
        ("ref_time", 50),
    ]
    dims = {v.name: v.dims for v in plan.dataset.data_vars}
    assert dims == {
        "I": ("V",),
        "trace": ("V", "record", "trace_time"),
        "ref": ("V", "record", "ref_time"),
    }
    slab = capture_slab(plan, definition.capture("ref"))
    assert [(d.name, d.size) for d in slab.dims] == [("record", 2), ("ref_time", 50)]
    assert slab.data_vars[0].dims == ("record", "ref_time") and slab.coords[0].dim == "ref_time"

    class SpyScope(SimulatedWaveformSense):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.armed: list[tuple[str, tuple[int | None, ...]]] = []

        def arm(self, channel, dataset, variable):
            self.armed.append((channel, tuple(d.size for d in dataset.dims)))
            return super().arm(channel, dataset, variable)

    dac, meter = SimulatedLevelSource(), SimulatedLevelSense()
    scope = SpyScope(noise=0.0, response=low_pass_step(3e-3, 1.0))
    frames = list(Executor(plan, {"dac": dac, "meter": meter, "scope": scope}).run().frames())
    assert scope.armed == [("1", (2, 200)), ("2", (2, 50))] * 3
    # per point: two records of each capture, in order; the sensed line is flushed once, at the last
    # point of the innermost stepped axis, before that point's captures
    kinds = [f.chunk.variables for f in frames]
    point = [("trace",), ("trace",), ("ref",), ("ref",)]
    assert kinds == point * 2 + [("I",)] + point
    assert frames[-1].chunk.final and not any(f.chunk.final for f in frames[:-1])
    assert [(s.dim, s.start, s.stop) for s in frames[1].chunk.region] == [
        ("V", 0, 1),
        ("record", 1, 2),
        ("trace_time", 0, 200),
    ]
    assert frames[1].arrays["trace"].shape == (1, 1, 200)
    out = assemble(plan.dataset, frames)
    assert out["trace"].shape == (3, 2, 200) and out["ref"].shape == (3, 2, 50)
    assert not np.isnan(out["trace"].values).any() and not np.isnan(out["ref"].values).any()
    t = np.linspace(-1e-3, 9e-3, 200)
    np.testing.assert_allclose(
        out["trace"].values[2, 1], np.where(t >= 0, 1 - np.exp(-np.clip(t, 0, None) / 3e-3), 0.0)
    )


def test_capture_needs_the_capability_and_the_protocol():
    bare = scope_stand().model_copy(
        update={
            "instruments": tuple(
                i.model_copy(update={"capabilities": ("level_source",)}) if i.id == "scope" else i
                for i in scope_stand().instruments
            )
        }
    )
    with pytest.raises(ValueError, match="lacks capability 'waveform_sense'"):
        compile_sweep(SweepDefinition(name="droop", captured=(capture(),)), bare)
    plan = compile_sweep(SweepDefinition(name="droop", captured=(capture(),)), scope_stand())
    with pytest.raises(TypeError, match="WaveformSense"):
        Executor(plan, {"scope": SimulatedLevelSource()})


# --- virtual gates (ADR 0049) ------------------------------------------------------------------------


def test_a_coupled_channel_moves_with_its_axis_from_its_held_level():
    """`couplings` on a stepped axis: the companion is set with the axis to origin + c · value, the
    origin its held level (ADR 0038) or 0; it resolves as level_source; settle is the longest."""
    definition = SweepDefinition(
        name="virtual",
        axes=(
            SweepAxis(
                name="R",
                channel="gate_R",
                start=0.0,
                stop=0.2,
                num=3,
                couplings={"gate_L_dc": -0.5},
            ),
        ),
        sensed=(SensedLevel(name="I", channel="sensor_dc"),),
        levels=(FixedLevel(channel="gate_L_dc", value=0.1),),
    )
    plan = compile_sweep(definition, stand())
    assert {c.logical: c.role for c in plan.channels} == {
        "gate_R": "level_source",
        "gate_L_dc": "level_source",
        "sensor_dc": "level_sense",
    }
    assert [d.name for d in plan.dataset.dims] == ["R"]  # the companion is not a coordinate
    dac = SpyLevelSource()
    slept: list[float] = []
    list(
        Executor(plan, {"dac": dac, "meter": SimulatedLevelSense()}, sleep=slept.append)
        .run()
        .frames()
    )
    sets = [(ch, round(v, 6)) for ch, v in dac.calls]
    assert sets[0] == ("ch01", 0.1)  # the operating point first
    # at R = 0 the companion's target, 0.1 − 0.5 · 0.0, is the level already applied: no redundant set
    assert sets[1:] == [
        ("ch00", 0.0),
        ("ch00", 0.1),
        ("ch01", 0.05),
        ("ch00", 0.2),
        ("ch01", 0.0),
    ]
    assert slept and max(slept) == 0.01  # gate_L_dc's settle_s wins at every point


def test_a_coupled_channel_needs_the_capability():
    bare = stand().model_copy(
        update={
            "instruments": tuple(
                i.model_copy(update={"capabilities": ("level_sense",)}) if i.id == "dac" else i
                for i in stand().instruments
            )
        }
    )
    definition = SweepDefinition(
        name="virtual",
        axes=(
            SweepAxis(
                name="R",
                channel="gate_R",
                start=0.0,
                stop=0.2,
                num=3,
                couplings={"gate_L_dc": -0.5},
            ),
        ),
        sensed=(SensedLevel(name="I", channel="sensor_dc"),),
    )
    with pytest.raises(ValueError, match="lacks capability 'level_source'"):
        compile_sweep(definition, bare)


# --- the shot is the timeline: captures inside the shot (ADR 0060) ----------------------------------


def pulsed_scope_stand() -> StandConfig:
    """A sequencer with a pulse line and a scope on its own instrument: L2-3's shape."""
    return StandConfig(
        stand_id="pulsed-scope",
        instruments=(
            InstrumentConfig(id="dac", backend="simulated", capabilities=("level_source",)),
            InstrumentConfig(id="seq", backend="simulated", capabilities=("sequencer",)),
            InstrumentConfig(id="scope", backend="simulated", capabilities=("waveform_sense",)),
        ),
        channels=(
            ChannelMap(logical="V", instrument="dac", channel="ch00", quantity="voltage"),
            ChannelMap(logical="rf", instrument="seq", channel="ao1", quantity="voltage"),
            ChannelMap(logical="scope1", instrument="scope", channel="1", quantity="voltage"),
        ),
    )


def step_response(shots=1, axis=False) -> SweepDefinition:
    seq = PulseSequence(
        name="step response",
        body=(
            Step(channel="rf", level=0.1, duration=2000),
            Capture(channel="scope1", duration=8_000_000, num=200, result="trace"),
        ),
    )
    return SweepDefinition(
        name="step response",
        axes=(SweepAxis(name="V", channel="V", start=0.0, stop=1.0, num=3),) if axis else (),
        stage=SequencerStage(instrument="seq", sequence=seq, shots=shots),
    )


def test_a_shot_capture_is_one_record_per_shot_on_a_time_axis_from_the_capture():
    """ADR 0060: the stimulus is a step on the sequencer's line; the readout is a scope window opened
    in the shot. The scope is armed for one record per shot before the shots run; each record is
    re-keyed to its shot; time starts at the capture, not at a front-panel trigger."""
    from qdt_lab.experiment.execute import shot_capture_slab
    from qdt_lab.simulated import SimulatedWaveformSense, exponential_decay

    plan = compile_sweep(step_response(shots=3), pulsed_scope_stand(), {"simulated": SimulatedEmitter()})
    assert [(d.name, d.size) for d in plan.dataset.dims] == [("shot", 3), ("time", 200)]
    (coord,) = plan.dataset.coords
    assert (coord.dim, coord.start, coord.stop, coord.num, coord.unit) == ("time", 0.0, 8e-3, 200, "s")
    assert [(v.name, v.dims, v.unit) for v in plan.dataset.data_vars] == [("trace", ("shot", "time"), "V")]
    assert {(c.logical, c.role) for c in plan.channels} == {("rf", "sequencer"), ("scope1", "waveform_sense")}
    assert plan.stage_program.results == ()  # the sequencer fills nothing: the scope does
    slab = shot_capture_slab(plan, plan.definition.stage.captures()[0])
    assert [(d.name, d.size) for d in slab.dims] == [("record", 3), ("time", 200)]

    class SpyScope(SimulatedWaveformSense):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.armed: list[tuple[str, tuple[int | None, ...]]] = []

        def arm(self, channel, dataset, variable):
            self.armed.append((channel, tuple(d.size for d in dataset.dims)))
            return super().arm(channel, dataset, variable)

    scope = SpyScope(noise=0.0, response=exponential_decay(2e-3, 0.2))
    frames = list(
        Executor(plan, {"seq": SimulatedSequencer(), "scope": scope}).run().frames()
    )
    assert scope.armed == [("1", (3, 200))]
    assert [f.chunk.variables for f in frames] == [("trace",)] * 3
    assert [(s.dim, s.start, s.stop) for s in frames[1].chunk.region] == [("shot", 1, 2), ("time", 0, 200)]
    assert frames[-1].chunk.final and not any(f.chunk.final for f in frames[:-1])
    out = assemble(plan.dataset, frames)
    t = np.linspace(0.0, 8e-3, 200)
    np.testing.assert_allclose(out["trace"].values[2], 0.2 * np.exp(-t / 2e-3))


def test_a_shot_capture_at_every_stepped_point_with_one_shot_has_no_shot_dimension():
    from qdt_lab.simulated import SimulatedWaveformSense, low_pass_step

    plan = compile_sweep(step_response(axis=True), pulsed_scope_stand(), {"simulated": SimulatedEmitter()})
    assert [(d.name, d.size) for d in plan.dataset.dims] == [("V", 3), ("time", 200)]
    assert plan.dataset.data_vars[0].dims == ("V", "time")
    dac, scope = SimulatedLevelSource(), SimulatedWaveformSense(noise=0.0, response=low_pass_step(3e-3, 1.0))
    frames = list(Executor(plan, {"dac": dac, "seq": SimulatedSequencer(), "scope": scope}).run().frames())
    assert [(s.dim, s.start, s.stop) for s in frames[2].chunk.region] == [("V", 2, 3), ("time", 0, 200)]
    assert dac.get("ch00") == 1.0  # the axis was stepped before each shot
    out = assemble(plan.dataset, frames)
    assert out["trace"].shape == (3, 200) and not np.isnan(out["trace"].values).any()


def test_a_shot_capture_on_the_sequencers_own_input_is_refused_for_now():
    stand = pulsed_scope_stand().model_copy(
        update={
            "instruments": (
                InstrumentConfig(id="dac", backend="simulated", capabilities=("level_source",)),
                InstrumentConfig(id="seq", backend="simulated", capabilities=("sequencer", "waveform_sense")),
            ),
            "channels": (
                ChannelMap(logical="V", instrument="dac", channel="ch00", quantity="voltage"),
                ChannelMap(logical="rf", instrument="seq", channel="ao1", quantity="voltage"),
                ChannelMap(logical="scope1", instrument="seq", channel="ai1", quantity="voltage"),
            ),
        }
    )
    with pytest.raises(ValueError, match="sequencer's own input"):
        compile_sweep(step_response(), stand, {"simulated": SimulatedEmitter()})
