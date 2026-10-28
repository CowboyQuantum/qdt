"""The sequencer interpreter (`SimulatedInstrument`, ADR 0087) on a linear physics, through the real
path: compile_sweep + SimulatedEmitter + Executor. The physics defines every value, so the oracle is
arithmetic: what each reading should be, and how far the clock should have run."""

import numpy as np
import pytest

from qdt_lab.experiment import Executor, SimulatedEmitter, compile_sweep
from qdt_lab.protocols import LevelSense, LevelSource, Sequencer, TriggeredLevelSource
from qdt_lab.simulated import LinearPhysics, SimulatedInstrument
from qdt_lab.stream import assemble
from qdt_schemas.activity import SequencerStage, SweepAxis, SweepDefinition
from qdt_schemas.pulse import Capture, Difference, Measure, PulseSequence, Step
from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig

ROLES = {"a": "a", "a_pulse": "a", "b": "b", "out": "out"}
OVERHEAD = 10e-6


def stand() -> StandConfig:
    quantity = {"a": "voltage", "a_pulse": "voltage", "b": "voltage", "out": "current"}
    return StandConfig(
        stand_id="stub-stand",
        instruments=(
            InstrumentConfig(
                id="sim",
                backend="simulated",
                capabilities=("level_source", "level_sense", "sequencer", "triggered_level_source"),
            ),
        ),
        channels=tuple(
            ChannelMap(logical=ch, instrument="sim", channel=ch, quantity=q)
            for ch, q in quantity.items()
        ),
    )


def instrument(**kwargs) -> SimulatedInstrument:
    s = stand()
    physics = LinearPhysics({"a": 1.0, "b": 2.0}, defaults={"b": 0.25})
    return SimulatedInstrument.from_config(
        s.instrument("sim"), s.instrument_channels("sim"), physics, ROLES, **kwargs
    )


def run(definition: SweepDefinition, inst: SimulatedInstrument):
    plan = compile_sweep(definition, stand(), {"simulated": SimulatedEmitter()})
    return plan, assemble(plan.dataset, Executor(plan, {"sim": inst}).run().frames())


def test_the_instrument_satisfies_the_four_protocols():
    inst = instrument()
    for protocol in (LevelSource, LevelSense, Sequencer, TriggeredLevelSource):
        assert isinstance(inst, protocol)


def test_levels_add_per_input_and_an_input_starts_at_its_default():
    inst = instrument()
    assert inst.get("b") == 0.25  # the first channel of an input starts at the physics' default
    inst.set("a", 0.5)
    assert inst.levels({"a_pulse": 0.125}) == {"a": 0.625, "b": 0.25}
    assert inst.sense("out") == pytest.approx(0.5 + 2 * 0.25)
    assert inst.clock_s == pytest.approx(1e-3 + OVERHEAD)  # default aperture plus the shot overhead
    with pytest.raises(ValueError, match="sense the out"):
        inst.sense("a")
    with pytest.raises(ValueError, match="unknown channel"):
        inst.set("c", 0.0)


def test_from_config_refuses_another_backend_and_a_contradicting_quantity():
    s = stand()
    physics = LinearPhysics({"a": 1.0, "b": 2.0})
    with pytest.raises(ValueError, match="backend 'simulated'"):
        SimulatedInstrument.from_config(
            s.instrument("sim").model_copy(update={"backend": "qua"}), (), physics, ROLES
        )
    wrong = tuple(
        c.model_copy(update={"quantity": "voltage"}) if c.channel == "out" else c
        for c in s.instrument_channels("sim")
    )
    with pytest.raises(ValueError, match="'out' \\(out\\) is current"):
        SimulatedInstrument.from_config(s.instrument("sim"), wrong, physics, ROLES)


def test_an_emitted_shot_gives_the_values_the_physics_defines_and_runs_the_clock_it_says():
    """A triggered DC axis on `a`; per shot: a pulse step, a measure, a second step, a measure, their
    difference, and a record on the instrument's own output."""
    levels = np.linspace(-0.1, 0.2, 4)
    definition = SweepDefinition(
        name="stub shot",
        axes=(SweepAxis(name="a", channel="a", start=-0.1, stop=0.2, num=4),),
        stage=SequencerStage(
            instrument="sim",
            sequence=PulseSequence(
                name="two levels and a record",
                body=(
                    Step(channel="a_pulse", level=0.05, duration=200),
                    Measure(channel="out", duration=1000, result="high"),
                    Step(channel="a_pulse", level=-0.05, duration=300),
                    Measure(channel="out", duration=1000, result="low"),
                    Difference(result="delta", a="high", b="low"),
                    Capture(channel="out", duration=2000, num=8, result="trace"),
                ),
            ),
            shots=3,
            reduce={"high": "mean", "low": "mean", "delta": "mean"},
        ),
    )
    inst = instrument()
    plan, out = run(definition, inst)
    assert plan.pacing_of("a").pacing == "triggered"  # the instrument triggers itself (ADR 0066)
    np.testing.assert_allclose(out["high"].values, levels + 0.05 + 0.5)
    np.testing.assert_allclose(out["low"].values, levels - 0.05 + 0.5)
    np.testing.assert_allclose(out["delta"].values, 0.1)
    assert out["trace"].shape == (4, 3, 8)  # a record keeps every shot (ADR 0060)
    np.testing.assert_allclose(
        out["trace"].values, np.broadcast_to((levels - 0.05 + 0.5)[:, None, None], (4, 3, 8))
    )
    per_shot = (200 + 1000 + 300 + 1000 + 2000) * 1e-9 + 2 * OVERHEAD
    assert inst.clock_s == pytest.approx(4 * 3 * per_shot, rel=1e-12)


def test_a_list_loaded_on_a_channel_follows_the_triggered_axis_and_wraps():
    inst = instrument()
    inst.load("b", (0.0, 1.0))
    inst.advance("b")
    inst.advance("b")
    assert inst.get("b") == 1.0
    inst.advance("b")
    assert inst.get("b") == 0.0  # past the end the list starts again
    inst.release("b")
    with pytest.raises(ValueError, match="no list loaded"):
        inst.advance("b")
