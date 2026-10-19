"""Compiler + executor over simulated backends: dry-run count, order, shape; reproducibility; rejections.

The flat-index SimulatedSequencer makes stage results checkable exactly; the loopback
SimulatedLevelSense makes sensed values equal the applied level on the same vendor channel.
"""

import itertools
import json
import threading
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

    plan = compile_sweep(
        step_response(shots=3), pulsed_scope_stand(), {"simulated": SimulatedEmitter()}
    )
    assert [(d.name, d.size) for d in plan.dataset.dims] == [("shot", 3), ("time", 200)]
    (coord,) = plan.dataset.coords
    assert (coord.dim, coord.start, coord.stop, coord.num, coord.unit) == (
        "time",
        0.0,
        8e-3,
        200,
        "s",
    )
    assert [(v.name, v.dims, v.unit) for v in plan.dataset.data_vars] == [
        ("trace", ("shot", "time"), "V")
    ]
    assert {(c.logical, c.role) for c in plan.channels} == {
        ("rf", "sequencer"),
        ("scope1", "waveform_sense"),
    }
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
    frames = list(Executor(plan, {"seq": SimulatedSequencer(), "scope": scope}).run().frames())
    assert scope.armed == [("1", (3, 200))]
    assert [f.chunk.variables for f in frames] == [("trace",)] * 3
    assert [(s.dim, s.start, s.stop) for s in frames[1].chunk.region] == [
        ("shot", 1, 2),
        ("time", 0, 200),
    ]
    assert frames[-1].chunk.final and not any(f.chunk.final for f in frames[:-1])
    out = assemble(plan.dataset, frames)
    t = np.linspace(0.0, 8e-3, 200)
    np.testing.assert_allclose(out["trace"].values[2], 0.2 * np.exp(-t / 2e-3))


def test_a_shot_capture_at_every_stepped_point_with_one_shot_has_no_shot_dimension():
    from qdt_lab.simulated import SimulatedWaveformSense, low_pass_step

    plan = compile_sweep(
        step_response(axis=True), pulsed_scope_stand(), {"simulated": SimulatedEmitter()}
    )
    assert [(d.name, d.size) for d in plan.dataset.dims] == [("V", 3), ("time", 200)]
    assert plan.dataset.data_vars[0].dims == ("V", "time")
    dac, scope = (
        SimulatedLevelSource(),
        SimulatedWaveformSense(noise=0.0, response=low_pass_step(3e-3, 1.0)),
    )
    frames = list(
        Executor(plan, {"dac": dac, "seq": SimulatedSequencer(), "scope": scope}).run().frames()
    )
    assert [(s.dim, s.start, s.stop) for s in frames[2].chunk.region] == [
        ("V", 2, 3),
        ("time", 0, 200),
    ]
    assert dac.get("ch00") == 1.0  # the axis was stepped before each shot
    out = assemble(plan.dataset, frames)
    assert out["trace"].shape == (3, 200) and not np.isnan(out["trace"].values).any()


def test_a_shot_capture_on_the_sequencers_own_input_is_refused_for_now():
    stand = pulsed_scope_stand().model_copy(
        update={
            "instruments": (
                InstrumentConfig(id="dac", backend="simulated", capabilities=("level_source",)),
                InstrumentConfig(
                    id="seq", backend="simulated", capabilities=("sequencer", "waveform_sense")
                ),
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


# --- the sequencer paces the scan: a triggered stepped axis (ADR 0064) ------------------------------


class TriggeringSequencer(SimulatedSequencer):
    """The L0 model of the OPX's marker line: before a run it advances every list on the DAC once per
    point of the triggered axis (num markers), as the program's outer loop does on hardware."""

    def __init__(self, dac: SimulatedLevelSource, num: int) -> None:
        super().__init__()
        self._dac, self._num = dac, num
        self.markers = 0
        self.levels_seen: list[tuple[float, ...]] = []

    def run(self, compiled, parameters, dataset):
        for _ in range(self._num):
            for ch in self._dac.armed():
                self._dac.advance(ch)
            self.markers += 1
            self.levels_seen.append(tuple(self._dac.get(ch) for ch in sorted(self._dac.armed())))
        return super().run(compiled, parameters, dataset)


def paced_stand(trigger_from: bool = True) -> StandConfig:
    dac_settings = {"trigger_from": "dac_trigger"} if trigger_from else {}
    return StandConfig(
        stand_id="paced",
        instruments=(
            InstrumentConfig(
                id="dac",
                backend="simulated",
                capabilities=("level_source", "triggered_level_source"),
                settings=dac_settings,
            ),
            InstrumentConfig(id="seq", backend="simulated", capabilities=("sequencer",)),
            InstrumentConfig(id="scope", backend="simulated", capabilities=("waveform_sense",)),
        ),
        channels=(
            ChannelMap(
                logical="V", instrument="dac", channel="ch00", quantity="voltage", settle_s=0.01
            ),
            ChannelMap(logical="W", instrument="dac", channel="ch01", quantity="voltage"),
            ChannelMap(logical="B", instrument="dac", channel="ch02", quantity="voltage"),
            ChannelMap(logical="rf", instrument="seq", channel="ao1", quantity="voltage"),
            ChannelMap(logical="dac_trigger", instrument="seq", channel="do2", quantity="voltage"),
            ChannelMap(logical="sensor", instrument="seq", channel="ai1", quantity="voltage"),
            ChannelMap(logical="scope1", instrument="scope", channel="1", quantity="voltage"),
        ),
    )


def paced_definition(
    shots=1, outer=False, capture=False, couple=False, stepping="triggered"
) -> SweepDefinition:
    body = [Step(channel="rf", level=Symbol(name="v", unit="V"), duration=200)]
    body.append(
        Capture(channel="scope1", duration=8_000_000, num=50, result="trace")
        if capture
        else Measure(channel="sensor", duration=1000, result="I")
    )
    axes = [
        SweepAxis(
            name="V",
            channel="V",
            start=0.0,
            stop=1.0,
            num=3,
            stepping=stepping,
            couplings={"W": -0.5} if couple else {},
        )
    ]
    if outer:
        axes.insert(0, SweepAxis(name="B", channel="B", start=0.0, stop=0.1, num=2))
    return SweepDefinition(
        name="paced",
        axes=tuple(axes),
        levels=(FixedLevel(channel="W", value=0.2),) if couple else (),
        stage=SequencerStage(
            instrument="seq",
            sequence=PulseSequence(name="px", body=tuple(body)),
            bindings=(SymbolBinding(symbol="v", axis="V"),),
            shots=shots,
        ),
    )


def test_a_triggered_axis_is_loaded_as_a_list_and_swept_inside_the_program():
    """The DAC is loaded once per program run and advanced by the sequencer's marker; the executor
    never `set`s it. The symbol bound to the axis travels as start/step, like a stage axis's."""
    plan = compile_sweep(paced_definition(outer=True), paced_stand(), EMITTERS)
    assert {(c.logical, c.role) for c in plan.channels} == {
        ("B", "level_source"),
        ("V", "triggered_level_source"),
        ("dac_trigger", "sequencer"),
        ("rf", "sequencer"),
        ("sensor", "sequencer"),
    }
    assert [p.name for p in plan.stage_program.parameters] == ["n_V", "v_start", "v_step", "shots"]
    assert plan.stage_program.results[0].dims == ("n_V",)
    body = json.loads(plan.stage_program.body)
    assert body["triggered"] == {"axis": "V", "lines": ["dac_trigger"], "settle_ns": 10_000_000}
    assert [d.name for d in plan.dataset.dims] == ["B", "V"]
    assert plan.dataset.data_vars[0].dims == ("B", "V")
    dac = SimulatedLevelSource()
    seq = TriggeringSequencer(dac, 3)
    frames = list(Executor(plan, {"dac": dac, "seq": seq}, sleep=lambda s: None).run().frames())
    assert seq.markers == 6  # 3 points, twice (once per outer point)
    assert seq.levels_seen == [(0.0,), (0.5,), (1.0,)] * 2
    assert dac.armed() == ()  # released when the plan ended; the last point holds
    assert dac.get("ch00") == 1.0 and dac.get("ch02") == 0.1
    assert [(s.dim, s.start, s.stop) for s in frames[1].chunk.region] == [("B", 1, 2), ("V", 0, 3)]
    out = assemble(plan.dataset, frames)
    assert out["I"].shape == (2, 3) and not np.isnan(out["I"].values).any()


def test_a_triggered_axis_moves_its_coupled_companions_as_lists_too():
    plan = compile_sweep(paced_definition(couple=True), paced_stand(), EMITTERS)
    assert {c.logical: c.role for c in plan.channels}["W"] == "triggered_level_source"
    dac = SimulatedLevelSource()
    seq = TriggeringSequencer(dac, 3)
    list(Executor(plan, {"dac": dac, "seq": seq}, sleep=lambda s: None).run().frames())
    # W from its held 0.2 V by -0.5 V/V of V: 0.2, -0.05, -0.3
    np.testing.assert_allclose(seq.levels_seen, [(0.0, 0.2), (0.5, -0.05), (1.0, -0.3)], atol=1e-12)


def test_a_shot_capture_over_a_triggered_axis_is_armed_for_points_times_shots():
    from qdt_lab.experiment.execute import shot_capture_slab
    from qdt_lab.simulated import SimulatedWaveformSense, exponential_decay

    plan = compile_sweep(paced_definition(shots=2, capture=True), paced_stand(), EMITTERS)
    assert [(d.name, d.size) for d in plan.dataset.dims] == [("V", 3), ("shot", 2), ("time", 50)]
    slab = shot_capture_slab(plan, plan.definition.stage.captures()[0])
    assert [(d.name, d.size) for d in slab.dims] == [("record", 6), ("time", 50)]
    assert "lines" not in json.loads(plan.stage_program.body)  # the scope triggers itself (0063)
    dac = SimulatedLevelSource()
    scope = SimulatedWaveformSense(noise=0.0, response=exponential_decay(2e-3, 0.2))
    frames = list(
        Executor(
            plan,
            {"dac": dac, "seq": TriggeringSequencer(dac, 3), "scope": scope},
            sleep=lambda s: None,
        )
        .run()
        .frames()
    )
    assert [(s.dim, s.start, s.stop) for s in frames[3].chunk.region] == [
        ("V", 1, 2),
        ("shot", 1, 2),
        ("time", 0, 50),
    ]
    out = assemble(plan.dataset, frames)
    assert out["trace"].shape == (3, 2, 50) and not np.isnan(out["trace"].values).any()


def test_a_scope_with_a_trigger_line_gets_its_marker_in_the_program():
    stand = paced_stand().model_copy(
        update={
            "instruments": tuple(
                i.model_copy(update={"settings": {"trigger_from": "scope_trigger"}})
                if i.id == "scope"
                else i
                for i in paced_stand().instruments
            ),
            "channels": (
                *paced_stand().channels,
                ChannelMap(
                    logical="scope_trigger", instrument="seq", channel="do1", quantity="voltage"
                ),
            ),
        }
    )
    plan = compile_sweep(paced_definition(capture=True), stand, EMITTERS)
    assert json.loads(plan.stage_program.body)["lines"] == {"scope1": "scope_trigger"}
    assert {c.logical: c.role for c in plan.channels}["scope_trigger"] == "sequencer"


def test_a_forced_trigger_needs_the_capability_and_a_trigger_line_from_the_sequencer():
    """ADR 0066: 'triggered' is required, so a stand that cannot honour it is a compile error."""
    with pytest.raises(ValueError, match="'V' is set to 'triggered', but .* cannot step a list"):
        compile_sweep(paced_definition(), pulsed_scope_stand_with_v(), EMITTERS)
    with pytest.raises(ValueError, match="has no settings\\['trigger_from'\\]"):
        compile_sweep(paced_definition(), paced_stand(trigger_from=False), EMITTERS)
    wrong = paced_stand().model_copy(
        update={
            "instruments": tuple(
                i.model_copy(update={"settings": {"trigger_from": "scope1"}})
                if i.id == "dac"
                else i
                for i in paced_stand().instruments
            )
        }
    )
    with pytest.raises(ValueError, match="not a channel of the sequencer"):
        compile_sweep(paced_definition(), wrong, EMITTERS)


def pulsed_scope_stand_with_v() -> StandConfig:
    base = paced_stand()
    return base.model_copy(
        update={
            "instruments": tuple(
                i.model_copy(update={"capabilities": ("level_source",)}) if i.id == "dac" else i
                for i in base.instruments
            )
        }
    )


def test_a_shot_capture_is_drained_while_the_shots_play():
    """A real scope acquires only while its frames are read (`:DIGitize`), so the executor reads
    them on a thread from before the sequencer starts; a backend that raises there raises here."""
    from qdt_lab.simulated import SimulatedWaveformSense

    class Blocking(SimulatedWaveformSense):
        """Yields only after the sequencer has run: a scope waiting for its trigger."""

        def __init__(self, **kw):
            super().__init__(**kw)
            self.started = threading.Event()
            self.sequencer_ran = threading.Event()

        def arm(self, channel, dataset, variable):
            inner = super().arm(channel, dataset, variable)
            outer = self

            class Source:
                dataset = inner.dataset

                def frames(self):
                    outer.started.set()
                    assert outer.sequencer_ran.wait(2.0), "the scope was never triggered"
                    yield from inner.frames()

            return Source()

    class Firing(SimulatedSequencer):
        def __init__(self, scope):
            super().__init__()
            self._scope = scope

        def run(self, compiled, parameters, dataset):
            assert self._scope.started.wait(2.0), "the scope was not armed before the shots"
            self._scope.sequencer_ran.set()
            return super().run(compiled, parameters, dataset)

    plan = compile_sweep(step_response(shots=2), pulsed_scope_stand(), EMITTERS)
    scope = Blocking(noise=0.0)
    frames = list(
        Executor(plan, {"seq": Firing(scope), "scope": scope}, sleep=lambda s: None).run().frames()
    )
    assert len(frames) == 2

    class Broken(SimulatedWaveformSense):
        def arm(self, channel, dataset, variable):
            class Source:
                def frames(self):
                    raise RuntimeError("the scope timed out waiting for its trigger")
                    yield

            return Source()

    with pytest.raises(RuntimeError, match="timed out"):
        list(
            Executor(plan, {"seq": SimulatedSequencer(), "scope": Broken()}, sleep=lambda s: None)
            .run()
            .frames()
        )


# --- pacing is the plan's: 'auto' lets the stand decide (ADR 0066) ------------------------------------


def test_auto_pacing_triggers_the_innermost_dc_axis_on_a_stand_that_wires_it():
    """The definition says nothing about pacing; the stand's wiring decides; the plan and the Dataset
    record what was decided, so every record says how it was taken."""
    plan = compile_sweep(paced_definition(outer=True, stepping="auto"), paced_stand(), EMITTERS)
    assert "stepping" not in plan.definition.model_dump()["axes"][1]
    assert [(p.axis, p.pacing, p.lines) for p in plan.pacing] == [
        ("B", "software", ()),
        ("V", "triggered", ("dac_trigger",)),
    ]
    assert (plan.dataset.attrs["B.pacing"], plan.dataset.attrs["V.pacing"]) == (
        "software",
        "triggered",
    )
    roles = {c.logical: c.role for c in plan.channels}
    assert (roles["B"], roles["V"], roles["dac_trigger"]) == (
        "level_source",
        "triggered_level_source",
        "sequencer",
    )
    dac = SimulatedLevelSource()
    seq = TriggeringSequencer(dac, 3)
    list(Executor(plan, {"dac": dac, "seq": seq}, sleep=lambda s: None).run().frames())
    assert seq.markers == 6 and seq.levels_seen == [(0.0,), (0.5,), (1.0,)] * 2


def test_auto_pacing_steps_in_software_where_a_trigger_cannot_run():
    def pacing(definition, stand_config):
        plan = compile_sweep(definition, stand_config, EMITTERS)
        return {p.axis: p.pacing for p in plan.pacing}, plan

    # no wiring, no capability, or a preference for software: the executor sets every point
    # three shots kept: stepped from the host, the stage needs an axis of its own (the shots)
    for definition, stand_config in (
        (paced_definition(shots=3, stepping="auto"), paced_stand(trigger_from=False)),
        (paced_definition(shots=3, stepping="auto"), pulsed_scope_stand_with_v()),
        (paced_definition(shots=3, stepping="software"), paced_stand()),
    ):
        modes, plan = pacing(definition, stand_config)
        assert modes == {"V": "software"}
        assert {c.logical: c.role for c in plan.channels}["V"] == "level_source"
        assert "triggered" not in json.loads(plan.stage_program.body)
        assert plan.stage_program.parameters[0].name == "v"  # the axis value, set per point
        dac = SpyLevelSource()
        list(
            Executor(plan, {"dac": dac, "seq": SimulatedSequencer()}, sleep=lambda s: None)
            .run()
            .frames()
        )
        assert [v for ch, v in dac.calls if ch == "ch00"] == [0.0, 0.5, 1.0]
    # one shot per point compiles both ways since ADR 0068: host-stepped over the one-point axis
    assert (
        compile_sweep(paced_definition(stepping="auto"), paced_stand(trigger_from=False), EMITTERS)
        .pacing_of("V")
        .pacing
        == "software"
    )
    assert (
        compile_sweep(paced_definition(stepping="auto"), paced_stand(), EMITTERS)
        .pacing_of("V")
        .pacing
        == "triggered"
    )
    # something sensed per point, or no sequenced stage: the same
    assert pacing(stepped_definition(), stand())[0] == {
        "gate_R": "software",
        "gate_L_dc": "software",
    }
    assert pacing(staged_definition(), stand())[0] == {"gate_R": "software", "gate_L": "sequencer"}


def test_a_stand_whose_trigger_line_is_not_the_sequencers_is_an_error_even_on_auto():
    """A wrong `trigger_from` is a stand file error; falling back would hide it."""
    wrong = paced_stand().model_copy(
        update={
            "instruments": tuple(
                i.model_copy(update={"settings": {"trigger_from": "scope1"}})
                if i.id == "dac"
                else i
                for i in paced_stand().instruments
            )
        }
    )
    with pytest.raises(ValueError, match="not a channel of the sequencer"):
        compile_sweep(paced_definition(stepping="auto"), wrong, EMITTERS)


def test_resolve_pacing_is_pure_and_matches_the_plan():
    from qdt_lab.experiment import resolve_pacing

    definition = paced_definition(outer=True, stepping="auto")
    assert (
        resolve_pacing(definition, paced_stand())
        == compile_sweep(definition, paced_stand(), EMITTERS).pacing
    )


# --- a stage with no axis of its own records once per stepped point (ADR 0068) -----------------------


def test_a_stage_with_no_axis_records_one_value_per_host_stepped_point():
    """The program records its one value per run over the one-point axis `once`; the executor strips it
    and lays the value at the point it stepped to. Nothing on the stream carries `once`."""
    from qdt_lab.experiment import ONCE
    from qdt_lab.experiment.execute import stage_slab

    plan = compile_sweep(paced_definition(stepping="software"), paced_stand(), EMITTERS)
    assert plan.pacing_of("V").pacing == "software"
    assert [r.dims for r in plan.stage_program.results] == [(f"n_{ONCE}",)]
    assert f"n_{ONCE}" in {p.name for p in plan.stage_program.parameters}
    assert [(d.name, d.size) for d in plan.dataset.dims] == [("V", 3)]
    assert plan.dataset.data_vars[0].dims == ("V",)
    slab = stage_slab(plan)
    assert [(d.name, d.size) for d in slab.dims] == [(ONCE, 1)] and slab.data_vars[0].dims == (
        ONCE,
    )
    dac = SpyLevelSource()
    frames = list(
        Executor(plan, {"dac": dac, "seq": SimulatedSequencer()}, sleep=lambda s: None)
        .run()
        .frames()
    )
    assert [v for ch, v in dac.calls if ch == "ch00"] == [0.0, 0.5, 1.0]
    assert [[(s.dim, s.start, s.stop) for s in f.chunk.region] for f in frames] == [
        [("V", i, i + 1)] for i in range(3)
    ]
    assert all(ONCE not in (s.dim for s in f.chunk.region) for f in frames)
    out = assemble(plan.dataset, frames)
    assert out["I"].shape == (3,) and not np.isnan(out["I"].values).any()


def test_shots_averaged_or_kept_need_no_one_point_axis_unless_a_result_has_none():
    from qdt_lab.experiment import ONCE

    averaged = paced_definition(shots=3, stepping="software").model_copy(
        update={
            "stage": paced_definition(shots=3, stepping="software").stage.model_copy(
                update={"reduce": {"I": "mean"}}
            )
        }
    )
    plan = compile_sweep(averaged, paced_stand(), EMITTERS)
    assert [r.dims for r in plan.stage_program.results] == [(f"n_{ONCE}",)]
    assert plan.dataset.data_vars[0].dims == (
        "V",
    )  # averaged on the sequencer, one value per point
    kept = compile_sweep(paced_definition(shots=3, stepping="software"), paced_stand(), EMITTERS)
    assert [r.dims for r in kept.stage_program.results] == [("shots",)]  # the shots are its axis
    assert f"n_{ONCE}" not in {p.name for p in kept.stage_program.parameters}


def test_one_number_with_no_axis_anywhere_is_refused_and_a_repeat_gives_it_one():
    single = SweepDefinition(
        name="one number",
        stage=SequencerStage(
            instrument="seq",
            sequence=PulseSequence(
                name="px", body=(Measure(channel="sensor", duration=1000, result="I"),)
            ),
        ),
    )
    with pytest.raises(ValueError, match="'I' would be one number with no axis"):
        compile_sweep(single, paced_stand(), EMITTERS)
    plan = compile_sweep(single.model_copy(update={"repeats": 4}), paced_stand(), EMITTERS)
    assert plan.dataset.data_vars[0].dims == ("repeat",)
    frames = list(Executor(plan, {"seq": SimulatedSequencer()}).run().frames())
    assert [[(s.dim, s.start, s.stop) for s in f.chunk.region] for f in frames] == [
        [("repeat", k, k + 1)] for k in range(4)
    ]


def test_a_sequencers_input_is_read_in_the_shot_and_never_sensed_per_point():
    """ADR 0067 on a bench-shaped stand: a sequencer's voltage input is a sensor through its own
    `measure` (a 'V' variable over the stepped axes, the shots averaged); sensed per point it would need
    a LevelSense the sequencer has not, and the compiler says so."""
    seq = PulseSequence(
        name="read the input", body=(Measure(channel="sensor", duration=1000, result="V_sensor"),)
    )
    axes = (SweepAxis(name="V", channel="gate_R", start=0.0, stop=0.1, num=3),)
    in_shot = SweepDefinition(
        name="dc read in the shot",
        axes=axes,
        stage=SequencerStage(instrument="seq", sequence=seq, shots=4, reduce={"V_sensor": "mean"}),
    )
    plan = compile_sweep(in_shot, stand(), EMITTERS)
    assert [(v.name, v.dims, v.unit) for v in plan.dataset.data_vars] == [("V_sensor", ("V",), "V")]
    assert {(c.logical, c.role) for c in plan.channels} == {
        ("gate_R", "level_source"),
        ("sensor", "sequencer"),
    }
    per_point = SweepDefinition(
        name="dc sensed per point",
        axes=axes,
        sensed=(SensedLevel(name="V_sensor", channel="sensor"),),
    )
    with pytest.raises(ValueError, match=r"instrument 'seq' \('sensor'\) lacks capability 'level_sense'"):
        compile_sweep(per_point, stand(), EMITTERS)
