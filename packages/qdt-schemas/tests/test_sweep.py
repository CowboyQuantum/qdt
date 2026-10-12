import pytest
from pydantic import ValidationError

from qdt_schemas.activity import (
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


def pixel() -> PulseSequence:
    return PulseSequence(
        name="pixel",
        body=(
            Step(channel="gate_L_p", level=Symbol(name="v_L", unit="V"), duration=100),
            Step(channel="gate_R_p", level=Symbol(name="v_R", unit="V"), duration=100),
            Measure(channel="sensor", duration=1000, result="I_sens"),
        ),
    )


def stability(repeats: int | None = 1, shots: int = 1) -> SweepDefinition:
    return SweepDefinition(
        name="stability",
        axes=(
            SweepAxis(name="gate_R", channel="gate_R", start=-0.5, stop=0.5, num=3),
            SweepAxis(name="gate_L", channel="gate_L_p", start=-1.0, stop=0.0, num=4),
        ),
        stage=SequencerStage(
            instrument="seq0",
            axes=("gate_L",),
            sequence=pixel(),
            bindings=(
                SymbolBinding(symbol="v_L", axis="gate_L"),
                SymbolBinding(symbol="v_R", axis="gate_R"),
            ),
            shots=shots,
        ),
        repeats=repeats,
    )


def test_round_trip_and_helpers():
    d = stability()
    assert SweepDefinition.model_validate_json(d.model_dump_json()) == d
    assert [a.name for a in d.stepped_axes()] == ["gate_R"]
    assert [a.name for a in d.stage_axes()] == ["gate_L"]
    assert d.axis("gate_L").step == pytest.approx(1 / 3)
    assert d.stage.results() == ("I_sens",)
    assert d.stage.reduction("I_sens") == "keep"


def test_stepped_only_with_sensed():
    d = SweepDefinition(
        name="dc",
        axes=(SweepAxis(name="g", channel="gate", start=0, stop=1, num=5),),
        sensed=(SensedLevel(name="I", channel="meter"),),
    )
    assert d.stepped_axes() == d.axes


def test_stage_axes_must_be_innermost_in_order():
    d = stability()
    with pytest.raises(ValidationError, match="innermost"):
        SweepDefinition(
            name="x",
            axes=tuple(reversed(d.axes)),
            stage=d.stage,
        )


def test_every_symbol_must_be_bound():
    with pytest.raises(ValidationError, match="unbound"):
        SequencerStage(
            instrument="seq0",
            axes=("gate_L",),
            sequence=pixel(),
            bindings=(SymbolBinding(symbol="v_L", axis="gate_L"),),
        )


def test_binding_needs_axis_or_value():
    with pytest.raises(ValidationError, match="exactly one"):
        SymbolBinding(symbol="v")


def test_channel_in_two_roles_rejected():
    with pytest.raises(ValidationError, match="not both"):
        SweepDefinition(
            name="x",
            axes=(SweepAxis(name="g", channel="gate", start=0, stop=1, num=2),),
            sensed=(SensedLevel(name="I", channel="gate"),),
        )


def test_reserved_names_rejected():
    with pytest.raises(ValidationError, match="reserved"):
        SweepDefinition(
            name="x",
            axes=(SweepAxis(name="repeat", channel="gate", start=0, stop=1, num=2),),
            sensed=(SensedLevel(name="I", channel="meter"),),
        )


def test_sensed_needs_something_to_lay_over():
    with pytest.raises(ValidationError, match="stepped axis"):
        SweepDefinition(name="x", sensed=(SensedLevel(name="I", channel="meter"),))
    SweepDefinition(name="ok", sensed=(SensedLevel(name="I", channel="meter"),), repeats=None)


def test_program_escape_hatch_binds_every_parameter():
    program = SequencerProgram(
        backend="qua",
        body="#",
        parameters=(SequencerParameter(name="n", unit=""), SequencerParameter(name="k", unit="")),
        results=(SequencerResult(name="d", dims=("n",), dtype="int64", unit=""),),
    )
    with pytest.raises(ValidationError, match="every program parameter"):
        SequencerStage(
            instrument="seq0",
            axes=("g",),
            program=program,
            parameters=(ParameterBinding(parameter="n", source="axis_num", axis="g"),),
        )
    stage = SequencerStage(
        instrument="seq0",
        axes=("g",),
        program=program,
        parameters=(
            ParameterBinding(parameter="n", source="axis_num", axis="g"),
            ParameterBinding(parameter="k", source="const", value=7),
        ),
    )
    d = SweepDefinition(
        name="x", axes=(SweepAxis(name="g", channel="c", start=0, stop=1, num=4),), stage=stage
    )
    assert d.stage.results() == ("d",)


def test_parameter_binding_shape():
    with pytest.raises(ValidationError, match="needs value"):
        ParameterBinding(parameter="p", source="const", axis="g")
    with pytest.raises(ValidationError, match="needs axis"):
        ParameterBinding(parameter="p", source="axis_num", value=3)
