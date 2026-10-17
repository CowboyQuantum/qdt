import json
import pathlib

import pytest
from pydantic import ValidationError

from qdt_schemas.activity import (
    CapturedWaveform,
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
from qdt_schemas.pulse import Capture, Difference, Measure, PulseSequence, Step, Symbol


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


def test_operating_point_levels_hold_untouched_channels():
    """ADR 0038: fixed DC levels for the whole sweep; never a swept or sensed channel, one per channel."""
    from qdt_schemas.activity import FixedLevel

    base = stability()
    held = base.model_copy(update={"levels": (FixedLevel(channel="gate_R_dc", value=0.05),)})
    d = SweepDefinition.model_validate(held.model_dump())
    assert d.levels == (FixedLevel(channel="gate_R_dc", value=0.05),)
    assert SweepDefinition.model_validate_json(d.model_dump_json()) == d
    # without levels nothing new is serialized, so existing definitions keep their content hash
    assert "levels" not in base.model_dump() and "levels" in d.model_dump()
    axis = base.axes[0].channel
    for levels, match in [
        ((FixedLevel(channel=axis, value=0.0),), "swept, sensed or captured"),
        ((FixedLevel(channel="g", value=0.0), FixedLevel(channel="g", value=0.1)), "one level"),
    ]:
        with pytest.raises(ValidationError, match=match):
            SweepDefinition.model_validate(
                base.model_dump() | {"levels": [lv.model_dump() for lv in levels]}
            )


def test_captured_waveforms_are_an_additive_activity():
    """ADR 0047: a `WaveformSense` record per stepped point; the field is absent from the serialized
    form when empty, so existing definitions keep their content hash."""
    from qdt_schemas.activity import CapturedWaveform

    base = stability()
    assert "captured" not in base.model_dump()
    cap = CapturedWaveform(name="trace", channel="scope1", start_s=-1e-3, stop_s=9e-3, num=1000)
    assert cap.records == 1
    alone = SweepDefinition(name="droop", captured=(cap,))  # no axis, no stage, no sensed level
    assert "captured" in alone.model_dump() and alone.stepped_axes() == ()
    assert alone.capture("trace") == cap and alone.capture_time_dim("trace") == "time"
    two = SweepDefinition(
        name="two",
        captured=(
            cap,
            CapturedWaveform(name="ref", channel="scope2", start_s=0.0, stop_s=1e-3, num=100),
        ),
    )
    assert (
        two.capture_time_dim("trace") == "trace_time" and two.capture_time_dim("ref") == "ref_time"
    )
    with_axis = SweepDefinition(
        name="stepped droop",
        axes=(SweepAxis(name="gate_R", channel="gate_R", start=-0.5, stop=0.5, num=3),),
        captured=(cap.model_copy(update={"records": 4}),),
    )
    assert with_axis.captured[0].records == 4

    with pytest.raises(ValidationError, match="stop_s > start_s"):
        CapturedWaveform(name="t", channel="scope1", start_s=1.0, stop_s=1.0, num=10)
    with pytest.raises(ValidationError, match="num"):
        CapturedWaveform(name="t", channel="scope1", start_s=0.0, stop_s=1.0, num=1)
    for captured, match in [
        ((cap, cap.model_copy(update={"name": "again"})), "captured once"),
        ((cap, cap.model_copy(update={"name": "ref", "records": 2})), "same number of records"),
        ((cap.model_copy(update={"name": "time"}),), "reserved"),
        ((cap.model_copy(update={"name": "gate_R"}),), "distinct from axis names"),
        ((cap.model_copy(update={"channel": "gate_R"}),), "neither stepped nor sensed"),
    ]:
        with pytest.raises(ValidationError, match=match):
            SweepDefinition(
                name="bad",
                axes=(SweepAxis(name="gate_R", channel="gate_R", start=-0.5, stop=0.5, num=3),),
                captured=captured,
            )
    with pytest.raises(ValidationError, match="_time"):
        SweepDefinition(
            name="bad",
            axes=(SweepAxis(name="trace_time", channel="gate_R", start=-0.5, stop=0.5, num=3),),
            captured=(cap,),
        )
    with pytest.raises(ValidationError, match="senses something, captures something"):
        SweepDefinition(
            name="bad", axes=(SweepAxis(name="g", channel="gate_R", start=0, stop=1, num=3),)
        )


def test_a_stepped_axis_may_couple_other_channels_as_a_virtual_gate():
    """ADR 0049: `couplings` move LevelSource channels with the axis; absent from the serialized form
    when empty, so existing definitions keep their hash; never on a stage axis."""
    base = stability()
    assert "couplings" not in base.model_dump()["axes"][0]
    virtual = SweepDefinition.model_validate(
        base.model_dump()
        | {
            "axes": [
                base.axes[0].model_dump() | {"couplings": {"gate_L_dc": -0.2}},
                base.axes[1].model_dump(),
            ]
        }
    )
    assert virtual.axes[0].couplings == {"gate_L_dc": -0.2}
    assert virtual.coupled_channels() == ("gate_L_dc",)
    assert "couplings" in virtual.model_dump()["axes"][0]
    held = virtual.model_copy(update={"levels": (FixedLevel(channel="gate_L_dc", value=0.05),)})
    assert SweepDefinition.model_validate(held.model_dump()).levels[0].channel == "gate_L_dc"
    for axes, match in [
        (
            [base.axes[0], base.axes[1].model_copy(update={"couplings": {"gate_L_dc": 1.0}})],
            "stage axis",
        ),
        (
            [base.axes[0].model_copy(update={"couplings": {"gate_L_p": 1.0}}), base.axes[1]],
            "another axis",
        ),
        (
            [base.axes[0].model_copy(update={"couplings": {"gate_R": 1.0}}), base.axes[1]],
            "another axis",
        ),
    ]:
        with pytest.raises(ValidationError, match=match):
            SweepDefinition.model_validate(
                base.model_dump() | {"axes": [a.model_dump() for a in axes]}
            )
    with pytest.raises(ValidationError, match="sensed or captured"):
        SweepDefinition(
            name="dc",
            axes=(
                SweepAxis(
                    name="g", channel="gate_R", start=0, stop=1, num=3, couplings={"sensor": 0.1}
                ),
            ),
            sensed=(SensedLevel(name="I", channel="sensor"),),
        )


# --- the shot is the timeline: a capture is an op of the sequence (ADR 0060) -------------------------


def _shot_capture(**kw) -> PulseSequence:
    ops = (
        Step(channel="P2_pulse", level=0.1, duration=2000),
        Capture(channel="scope1", duration=10_000, num=200, result="trace"),
    )
    return PulseSequence(name="step response", body=ops, **kw)


def test_a_capture_is_a_readout_op_of_the_shot():
    seq = _shot_capture()
    assert seq.results() == ("trace",) and seq.captures()[0].channel == "scope1"
    assert seq.result_channel("trace") == "scope1" and "scope1" in seq.channels()
    assert seq.captures()[0].duration_s == pytest.approx(1e-5)
    with pytest.raises(ValidationError, match="result names must be unique"):
        PulseSequence(
            name="x",
            body=(
                Measure(channel="sensor", duration=100, result="trace"),
                Capture(channel="scope1", duration=100, num=2, result="trace"),
            ),
        )
    with pytest.raises(ValidationError, match="captured once per shot"):
        PulseSequence(
            name="x",
            body=(
                Capture(channel="scope1", duration=100, num=2, result="a"),
                Capture(channel="scope1", duration=100, num=2, result="b"),
            ),
        )
    with pytest.raises(ValidationError, match="needs 'trace' measured"):  # not a measure
        PulseSequence(
            name="x",
            body=(
                Capture(channel="scope1", duration=100, num=2, result="trace"),
                Measure(channel="sensor", duration=100, result="i"),
                Difference(result="d", a="trace", b="i"),
            ),
        )
    with pytest.raises(ValidationError):  # the window is fixed: no Symbol, no zero
        Capture(channel="scope1", duration=0, num=2, result="t")


def test_a_shot_capture_keeps_every_shot_and_needs_a_stage_without_stage_axes():
    stage = SequencerStage(instrument="dot", sequence=_shot_capture(), shots=3)
    assert stage.captures()[0].result == "trace" and stage.results() == ("trace",)
    with pytest.raises(ValidationError, match="keeps every shot"):
        SequencerStage(
            instrument="dot", sequence=_shot_capture(), shots=3, reduce={"trace": "mean"}
        )
    d = SweepDefinition(
        name="step response",
        axes=(SweepAxis(name="P1", channel="P1", start=0.0, stop=0.1, num=4),),
        stage=stage,
    )
    assert d.capture_time_dim("trace") == "time" and d.capture_grids() == {
        "trace": (0.0, 1e-5, 200)
    }
    with pytest.raises(ValidationError, match="without stage axes"):
        SweepDefinition(
            name="x",
            axes=(SweepAxis(name="P2", channel="P2_pulse", start=0.0, stop=0.1, num=4),),
            stage=SequencerStage(
                instrument="dot",
                axes=("P2",),
                sequence=PulseSequence(
                    name="s",
                    body=(
                        Step(channel="P2_pulse", level=Symbol(name="v", unit="V"), duration=100),
                        Capture(channel="scope1", duration=100, num=2, result="trace"),
                    ),
                ),
                bindings=(SymbolBinding(symbol="v", axis="P2"),),
            ),
        )
    with pytest.raises(ValidationError, match="in the shot or per point, not both"):
        SweepDefinition(
            name="x",
            stage=stage,
            captured=(
                CapturedWaveform(name="mon", channel="scope1", start_s=0.0, stop_s=1e-3, num=10),
            ),
        )
    # two grids: each variable gets its own time axis
    two = SweepDefinition(
        name="x",
        stage=stage,
        captured=(
            CapturedWaveform(name="mon", channel="scope2", start_s=0.0, stop_s=1e-3, num=10),
        ),
    )
    assert (
        two.capture_time_dim("trace") == "trace_time" and two.capture_time_dim("mon") == "mon_time"
    )


# --- pacing: the definition prefers, the plan decides (ADR 0064, 0066) --------------------------------

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _triggered(**axis_kw) -> SweepDefinition:
    axes = (
        SweepAxis(name="gate_R", channel="gate_R", start=-0.5, stop=0.5, num=3),
        SweepAxis(name="gate_L", channel="gate_L_p", start=-1.0, stop=0.0, num=4),
    )
    return SweepDefinition(
        name="stability",
        axes=(axes[0].model_copy(update=axis_kw), axes[1]),
        stage=SequencerStage(
            instrument="seq0",
            axes=("gate_L",),
            sequence=pixel(),
            bindings=(
                SymbolBinding(symbol="v_L", axis="gate_L"),
                SymbolBinding(symbol="v_R", axis="gate_R"),
            ),
        ),
    )


def test_stepping_is_a_preference_whose_default_auto_is_not_serialized():
    d = stability()
    assert all(a.stepping == "auto" for a in d.axes)
    assert (
        "stepping" not in d.model_dump()["axes"][0]
    )  # existing definitions keep their content hash
    for preference in ("software", "triggered"):
        forced = _triggered(stepping=preference)
        assert forced.model_dump()["axes"][0]["stepping"] == preference
        assert SweepDefinition.model_validate_json(forced.model_dump_json()) == forced
    assert [a.name for a in _triggered(stepping="triggered").stepped_axes()] == ["gate_R"]


def test_a_forced_trigger_needs_the_sequencer_in_the_loop_and_nothing_per_point():
    base = _triggered(stepping="triggered")
    with pytest.raises(ValidationError, match="innermost stepped axis"):
        SweepDefinition.model_validate(
            base.model_dump()
            | {
                "axes": [
                    base.axes[0].model_dump(),
                    SweepAxis(name="gate_M", channel="gate_M", start=0, stop=1, num=2).model_dump(),
                    base.axes[1].model_dump(),
                ],
            }
        )
    with pytest.raises(ValidationError, match="at most one axis is triggered"):
        SweepDefinition.model_validate(
            base.model_dump()
            | {
                "axes": [
                    SweepAxis(
                        name="gate_M",
                        channel="gate_M",
                        start=0,
                        stop=1,
                        num=2,
                        stepping="triggered",
                    ).model_dump(),
                    *[a.model_dump() for a in base.axes],
                ],
            }
        )
    for preference in ("software", "triggered"):
        with pytest.raises(ValidationError, match="is swept by the sequencer; stepping"):
            SweepDefinition.model_validate(
                base.model_dump()
                | {
                    "axes": [
                        base.axes[0].model_dump() | {"stepping": "auto"},
                        base.axes[1].model_dump() | {"stepping": preference},
                    ]
                }
            )
    with pytest.raises(ValidationError, match="needs a stage with a sequence"):
        SweepDefinition(
            name="dc",
            axes=(SweepAxis(name="g", channel="g", start=0, stop=1, num=2, stepping="triggered"),),
            sensed=(SensedLevel(name="I", channel="sensor"),),
        )
    with pytest.raises(ValidationError, match="nothing is sensed or captured per point"):
        SweepDefinition.model_validate(
            base.model_dump() | {"sensed": [{"name": "I_dc", "channel": "sensor_dc"}]}
        )
    # 'auto' asks nothing of the definition: the compiler falls back to the executor where it must
    SweepDefinition.model_validate(
        _triggered().model_dump() | {"sensed": [{"name": "I_dc", "channel": "sensor_dc"}]}
    )


def _plan(pacing=None):
    from qdt_schemas.activity import ExecutionPlan

    raw = json.loads((FIXTURES / "ExecutionPlan" / "v2.json").read_text())
    if pacing is not None:
        raw["pacing"] = pacing
    return ExecutionPlan.model_validate(raw)


def test_a_plan_records_how_each_axis_advances():
    """ADR 0066: P1 (a DC line) and P2 (a pulse line in the stage) in the committed v2 plan."""
    legacy = _plan()
    assert legacy.pacing == () and "pacing" not in legacy.model_dump()  # its content hash keeps
    assert [legacy.pacing_of(a).pacing for a in ("P1", "P2")] == ["software", "sequencer"]
    assert legacy.triggered_axis() is None
    assert [a.name for a in legacy.program_axes()] == ["P2"]
    assert [a.name for a in legacy.software_axes()] == ["P1"]

    paced = _plan(
        [
            {"axis": "P1", "pacing": "triggered", "lines": ["dac_trigger"]},
            {"axis": "P2", "pacing": "sequencer"},
        ]
    )
    assert paced.pacing_of("P1").lines == ("dac_trigger",)
    assert paced.triggered_axis().name == "P1"
    assert [a.name for a in paced.program_axes()] == ["P1", "P2"]
    assert paced.software_axes() == ()
    with pytest.raises(KeyError):
        paced.pacing_of("P3")


@pytest.mark.parametrize(
    ("pacing", "match"),
    [
        ([{"axis": "P1", "pacing": "software"}], "every axis once, in order"),
        (
            [{"axis": "P2", "pacing": "sequencer"}, {"axis": "P1", "pacing": "software"}],
            "every axis once, in order",
        ),
        (
            [{"axis": "P1", "pacing": "sequencer"}, {"axis": "P2", "pacing": "sequencer"}],
            "exactly the stage axes",
        ),
        (
            [
                {"axis": "P1", "pacing": "software", "lines": ["dac_trigger"]},
                {"axis": "P2", "pacing": "sequencer"},
            ],
            "only a triggered axis has marker lines",
        ),
    ],
)
def test_a_plans_pacing_is_consistent_with_its_definition(pacing, match):
    with pytest.raises(ValidationError, match=match):
        _plan(pacing)
