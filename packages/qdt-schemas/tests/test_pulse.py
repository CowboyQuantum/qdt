import pytest
from pydantic import ValidationError

from qdt_schemas.pulse import (
    Affine,
    Call,
    Difference,
    Drive,
    Measure,
    PulseSequence,
    Ramp,
    Segment,
    Step,
    Symbol,
    Wait,
)


def readout_sequence() -> PulseSequence:
    """Initialise, pulse the swept gates, read out: the per-pixel shot of a pulsed stability map."""
    return PulseSequence(
        name="pulsed stability pixel",
        segments=(
            Segment(name="init", ops=(Step(channel="gate_L", level=0.0, duration=200),)),
            Segment(
                name="read_out",
                ops=(
                    Wait(duration=Symbol(name="t_settle", unit="ns")),
                    Measure(channel="sensor", duration=1000, result="I_sens"),
                ),
            ),
        ),
        body=(
            Call(segment="init"),
            Ramp(channel="gate_L", start=0.0, stop=Symbol(name="v_L", unit="V"), duration=100),
            Step(channel="gate_R", level=Symbol(name="v_R", unit="V"), duration=400),
            Drive(channel="esr", frequency=Symbol(name="f", unit="Hz"), amplitude=0.1, duration=50),
            Call(segment="read_out"),
        ),
    )


def test_round_trip():
    s = readout_sequence()
    assert PulseSequence.model_validate_json(s.model_dump_json()) == s


def test_expand_inlines_calls_in_order():
    ops = readout_sequence().expand()
    assert [op.op for op in ops] == ["step", "ramp", "step", "drive", "wait", "measure"]


def test_symbols_results_channels():
    s = readout_sequence()
    assert s.symbols() == {"v_L": "V", "v_R": "V", "f": "Hz", "t_settle": "ns"}
    assert s.results() == ("I_sens",)
    assert s.channels() == ("gate_L", "gate_R", "esr", "sensor")


def test_unknown_segment_rejected():
    with pytest.raises(ValidationError, match="unknown segment"):
        PulseSequence(name="x", body=(Call(segment="nope"),))


def test_recursive_segment_rejected():
    with pytest.raises(ValidationError, match="calls itself"):
        PulseSequence(
            name="x",
            segments=(Segment(name="a", ops=(Call(segment="a"),)),),
            body=(Call(segment="a"),),
        )


def test_symbol_unit_must_be_consistent():
    with pytest.raises(ValidationError, match="units"):
        PulseSequence(
            name="x",
            body=(
                Step(channel="g", level=Symbol(name="v", unit="V"), duration=10),
                Step(channel="g", level=Symbol(name="v", unit="mV"), duration=10),
            ),
        )


def test_duration_symbol_must_be_ns():
    with pytest.raises(ValidationError, match="'ns'"):
        PulseSequence(name="x", body=(Wait(duration=Symbol(name="t", unit="s")),))


def test_result_names_unique_per_shot():
    with pytest.raises(ValidationError, match="unique"):
        PulseSequence(
            name="x",
            body=(
                Measure(channel="s", duration=10, result="r"),
                Measure(channel="s", duration=10, result="r"),
            ),
        )


def chopped(**diff) -> PulseSequence:
    v = Symbol(name="v", unit="V")
    return PulseSequence(
        name="chopped",
        body=(
            Step(channel="g", level=v, duration=100),
            Measure(channel="sensor", duration=1000, result="I_on"),
            Step(channel="g", level=Affine(symbol=v, scale=1.0, offset=0.002), duration=100),
            Measure(channel="sensor", duration=1000, result="I_off"),
            Difference(**({"result": "dI", "a": "I_on", "b": "I_off"} | diff)),
        ),
    )


def test_affine_follows_its_symbol_and_counts_as_using_it():
    s = chopped()
    assert s.symbols() == {"v": "V"}
    assert PulseSequence.model_validate_json(s.model_dump_json()) == s
    assert Affine(symbol=Symbol(name="v", unit="V"), scale=-2.0, offset=0.1).of(0.05) == 0.0
    with pytest.raises(ValidationError, match="units"):
        PulseSequence(
            name="x",
            body=(
                Step(channel="g", level=Symbol(name="v", unit="V"), duration=1),
                Drive(
                    channel="e",
                    frequency=Affine(symbol=Symbol(name="v", unit="Hz")),
                    amplitude=0.1,
                    duration=1,
                ),
            ),
        )


def test_difference_is_a_result_of_two_earlier_measures():
    s = chopped()
    assert s.results() == ("I_on", "I_off", "dI")
    assert s.result_channel("dI") == "sensor"
    assert [op.op for op in s.expand()][-1] == "difference"
    with pytest.raises(ValidationError, match="measured earlier"):
        chopped(b="I_later")
    with pytest.raises(ValidationError, match="from itself"):
        chopped(b="I_on")
    with pytest.raises(ValidationError, match="unique"):
        chopped(result="I_on")
    with pytest.raises(ValidationError, match="measured earlier"):  # time order: measure after it
        PulseSequence(
            name="x",
            body=(
                Measure(channel="sensor", duration=1, result="a"),
                Difference(result="d", a="a", b="b"),
                Measure(channel="sensor", duration=1, result="b"),
            ),
        )
