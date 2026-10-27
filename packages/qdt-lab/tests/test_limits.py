"""The compiler refuses a sweep beyond the stand state's limits (ADR 0075, 0085): every level a sweep
programs is counted, and a refusal names each channel and its limit. Nothing is clamped."""

from datetime import UTC, datetime

import pytest

from qdt_lab.experiment import LimitError, SimulatedEmitter, compile_sweep, driven_extents
from qdt_schemas.activity import (
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
from qdt_schemas.operations import ChannelLimit, StandState
from qdt_schemas.pulse import Affine, Drive, Measure, PulseSequence, Ramp, Step, Symbol
from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig

EMITTERS = {"simulated": SimulatedEmitter()}
T0 = datetime(2026, 10, 27, tzinfo=UTC)


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
            ChannelMap(logical="gate_L_dc", instrument="dac", channel="ch01", quantity="voltage"),
            ChannelMap(logical="sensor_dc", instrument="meter", channel="ch00", quantity="current"),
            ChannelMap(logical="gate_L_p", instrument="seq", channel="ao1", quantity="voltage"),
            ChannelMap(logical="drive", instrument="seq", channel="ao2", quantity="voltage"),
            ChannelMap(logical="sensor", instrument="seq", channel="ai1", quantity="voltage"),
        ),
    )


def state(*limits: tuple[str, float, float]) -> StandState:
    return StandState(
        stand_id="sim",
        version=3,
        limits=tuple(ChannelLimit(channel=c, min_v=lo, max_v=hi) for c, lo, hi in limits),
        set_by="local",
        set_at=T0,
        reason="test limits",
    )


def virtual_sweep() -> SweepDefinition:
    """gate_R from −0.2 to 0.4, moving gate_L_dc by −0.5 V/V from its held 0.1 (ADR 0049)."""
    return SweepDefinition(
        name="virtual",
        axes=(
            SweepAxis(
                name="R",
                channel="gate_R",
                start=-0.2,
                stop=0.4,
                num=4,
                couplings={"gate_L_dc": -0.5},
            ),
        ),
        sensed=(SensedLevel(name="I", channel="sensor_dc"),),
        levels=(FixedLevel(channel="gate_L_dc", value=0.1),),
    )


def pulsed_sweep() -> SweepDefinition:
    """A stage axis bound to a step level through an Affine, a ramp and a drive with constants."""
    v = Symbol(name="v", unit="V")
    a = Symbol(name="a", unit="V")
    return SweepDefinition(
        name="pulsed",
        axes=(
            SweepAxis(name="R", channel="gate_R", start=0.0, stop=0.1, num=2),
            SweepAxis(name="L", channel="gate_L_p", start=-0.3, stop=0.2, num=3),
        ),
        stage=SequencerStage(
            instrument="seq",
            axes=("L",),
            sequence=PulseSequence(
                name="pixel",
                body=(
                    Step(
                        channel="gate_L_p",
                        level=Affine(symbol=v, scale=2.0, offset=0.05),
                        duration=100,
                    ),
                    Ramp(channel="gate_L_p", start=0.0, stop=-0.1, duration=100),
                    Drive(channel="drive", frequency=1e6, amplitude=a, duration=100),
                    Measure(channel="sensor", duration=1000, result="I"),
                ),
            ),
            bindings=(SymbolBinding(symbol="v", axis="L"), SymbolBinding(symbol="a", value=-0.02)),
        ),
    )


def test_every_level_a_sweep_programs_is_counted_with_its_extremes():
    assert driven_extents(virtual_sweep()) == {
        "gate_L_dc": pytest.approx(
            (-0.1, 0.2)
        ),  # 0.1 − 0.5 · 0.4 to 0.1 − 0.5 · (−0.2), and the held 0.1
        "gate_R": (-0.2, 0.4),
    }
    ext = driven_extents(pulsed_sweep())
    assert ext["gate_R"] == (0.0, 0.1)
    assert ext["gate_L_p"] == pytest.approx(
        (-0.55, 0.45)
    )  # 2 · (−0.3) + 0.05 to 2 · 0.2 + 0.05; the ramp inside
    assert ext["drive"] == (-0.02, 0.02)  # a tone swings either way by its amplitude
    assert "sensor" not in ext  # measured, not driven


def test_a_sweep_within_its_limits_compiles_and_one_beyond_is_refused_naming_each_channel():
    within = state(("gate_R", -0.2, 0.4), ("gate_L_dc", -0.1, 0.2))
    plan = compile_sweep(virtual_sweep(), stand(), EMITTERS, stand_state=within)
    assert plan.definition == virtual_sweep()  # nothing clamped, nothing rewritten
    tight = state(("gate_R", -0.2, 0.3), ("gate_L_dc", 0.0, 0.2))
    with pytest.raises(LimitError) as refused:
        compile_sweep(virtual_sweep(), stand(), EMITTERS, stand_state=tight)
    message = str(refused.value)
    assert "version 3" in message
    assert "gate_R would reach -0.2 to 0.4, beyond its limit [-0.2, 0.3]" in message
    assert "gate_L_dc would reach -0.1 to 0.2, beyond its limit [0, 0.2]" in message
    assert isinstance(
        refused.value, ValueError
    )  # every caller that maps ValueError to a 400 refuses it


def test_pulse_levels_count_against_the_pulse_channels_limit():
    compile_sweep(pulsed_sweep(), stand(), EMITTERS, stand_state=state(("gate_L_p", -0.6, 0.5)))
    with pytest.raises(LimitError, match="gate_L_p would reach -0.55 to 0.45"):
        compile_sweep(pulsed_sweep(), stand(), EMITTERS, stand_state=state(("gate_L_p", -0.5, 0.5)))
    with pytest.raises(LimitError, match="drive would reach -0.02 to 0.02"):
        compile_sweep(pulsed_sweep(), stand(), EMITTERS, stand_state=state(("drive", 0.0, 1.0)))


def test_without_a_stand_state_or_without_a_limit_on_the_channel_nothing_is_refused():
    compile_sweep(virtual_sweep(), stand(), EMITTERS)
    compile_sweep(virtual_sweep(), stand(), EMITTERS, stand_state=state(("gate_L_p", 0.0, 0.0)))


def test_a_hand_written_program_on_a_sequencer_with_a_limited_channel_is_refused():
    program = SequencerProgram(
        backend="qua",
        body="# hand-written",
        parameters=(SequencerParameter(name="n", unit=""),),
        results=(SequencerResult(name="data", dims=("n",), dtype="int64", unit=""),),
    )
    d = SweepDefinition(
        name="raw",
        axes=(SweepAxis(name="g", channel="gate_L_p", start=0, stop=1, num=6),),
        stage=SequencerStage(
            instrument="seq",
            axes=("g",),
            program=program,
            parameters=(ParameterBinding(parameter="n", source="axis_num", axis="g"),),
        ),
    )
    compile_sweep(d, stand(), stand_state=state(("gate_R", -1.0, 1.0)))  # a limit elsewhere only
    with pytest.raises(LimitError, match="hand-written program on 'seq'"):
        compile_sweep(d, stand(), stand_state=state(("drive", -1.0, 1.0)))
