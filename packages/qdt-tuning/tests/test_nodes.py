"""A node is data the server can run: its method is in the catalogue with exactly these defaults, its
rule is in RULES, and its experiment compiles on both the simulator's stand and a bench-shaped one."""

from qdt_lab.experiment import SimulatedEmitter, compile_sweep
from qdt_schemas.activity import FixedLevel
from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig
from qdt_server.catalogue import METHODS
from qdt_sim.scenarios import DEVICE_ID, default_stand
from qdt_tuning import RULES, charge_lattice, coulomb_diamonds, stability_diagram
from qdt_tuning.nodes import (
    DIAMONDS_DEFAULTS,
    DIAMONDS_METHOD,
    TRANSITIONS_DEFAULTS,
    TRANSITIONS_METHOD,
    sensor_operating_point,
)


def test_the_nodes_method_is_the_catalogues_with_its_defaults():
    spec, _ = METHODS[TRANSITIONS_METHOD]
    assert spec.resolve({}) == TRANSITIONS_DEFAULTS
    node = charge_lattice(instrument=DEVICE_ID)
    assert node.method.name == TRANSITIONS_METHOD and node.method.version == spec.version
    assert node.method.parameters == TRANSITIONS_DEFAULTS
    assert node.decision.name in RULES and node.decision.version == RULES[node.decision.name][0]
    assert node.decision.parameters["max_cross_ratio"] == 0.6


def test_the_experiment_compiles_on_the_simulators_stand_and_on_a_bench_shaped_one():
    node = charge_lattice(instrument=DEVICE_ID, n=16)
    plan = compile_sweep(node.definition, default_stand(), {"simulated": SimulatedEmitter()})
    assert [d.name for d in plan.dataset.dims] == ["P1", "P2"]
    assert plan.dataset.data_vars[0].name == "I_sensor"
    bench = StandConfig(
        stand_id="bench-shaped",
        instruments=(
            InstrumentConfig(id="dac0", backend="simulated", capabilities=("level_source",)),
            InstrumentConfig(id="opx", backend="simulated", capabilities=("sequencer",)),
        ),
        channels=(
            ChannelMap(logical="P1", instrument="dac0", channel="ch01", quantity="voltage"),
            ChannelMap(logical="P2_pulse", instrument="opx", channel="ao1", quantity="voltage"),
            ChannelMap(logical="sensor", instrument="opx", channel="ai1", quantity="voltage"),
        ),
    )
    definition = stability_diagram(
        instrument="opx", p1=(0.0, 0.1), p2=(0.0, 0.1), n_outer=8, n_inner=8
    )
    plan = compile_sweep(definition, bench, {"simulated": SimulatedEmitter()})
    assert {c.logical: c.instrument for c in plan.channels} == {
        "P1": "dac0",
        "P2_pulse": "opx",
        "sensor": "opx",
    }


def test_the_sensor_node_uses_the_diamonds_method_with_its_defaults_and_feeds_the_charge_lattice():
    """ADR 0052: the diamonds method's defaults are the catalogue's; with a sensor gate the charge-lattice
    node holds it from the sensor node's `sg_operating_v` through `levels`."""
    spec, _ = METHODS[DIAMONDS_METHOD]
    assert spec.resolve({}) == DIAMONDS_DEFAULTS
    sensor = sensor_operating_point()
    assert sensor.node_id == "sensor-operating-point" and sensor.depends_on == ()
    assert sensor.method.name == DIAMONDS_METHOD and sensor.method.parameters == DIAMONDS_DEFAULTS
    assert sensor.decision.name in RULES and sensor.decision.parameters["flank_offset_v"] == 0.02
    assert [a.channel for a in sensor.definition.axes] == ["SG", "bias"]
    assert sensor.definition.sensed[0].channel == "sensor"
    plan = compile_sweep(sensor.definition, default_stand(), {"simulated": SimulatedEmitter()})
    assert [d.name for d in plan.dataset.dims] == ["SG", "V_sd"]
    held = charge_lattice(instrument=DEVICE_ID, sensor_gate="SG")
    assert held.depends_on == ("sensor-wing",)
    assert held.definition.levels == (FixedLevel(channel="SG", value=0.0),)
    assert [(b.node_id, b.output, b.target) for b in held.inputs] == [
        ("sensor-wing", "sg_operating_v", "levels.0.value")
    ]
    alone = charge_lattice(instrument=DEVICE_ID)
    assert alone.depends_on == () and alone.inputs == () and alone.definition.levels == ()
    assert coulomb_diamonds(sensor_gate="SG2", bias="b", sensor="s").axes[0].channel == "SG2"


def test_the_wing_node_uses_the_sensor_peak_method_holds_the_gate_and_compiles():
    """ADR 0062: a short sensor-gate sweep at a held bias, the peak method with the catalogue's defaults,
    the window bound to the diamonds' peak (or the held level), the gate held at the wing on acceptance."""
    from qdt_tuning.nodes import SENSOR_PEAK_DEFAULTS, SENSOR_PEAK_METHOD, sensor_wing

    spec, _ = METHODS[SENSOR_PEAK_METHOD]
    assert spec.resolve({}) == SENSOR_PEAK_DEFAULTS
    node = sensor_wing()
    assert node.node_id == "sensor-wing" and node.depends_on == ("sensor-operating-point",)
    assert node.method.parameters == SENSOR_PEAK_DEFAULTS and node.decision.name in RULES
    assert [a.channel for a in node.definition.axes] == ["SG"]
    assert node.definition.levels == (FixedLevel(channel="bias", value=10e-6),)
    assert {(b.target, b.offset, b.held) for b in node.inputs} == {("axes.0.start", -0.05, "SG"), ("axes.0.stop", 0.05, "SG")}
    assert node.holds == {"SG": "sg_operating_v"}
    plan = compile_sweep(node.definition, default_stand(), {"simulated": SimulatedEmitter()})
    assert [d.name for d in plan.dataset.dims] == ["SG"] and plan.dataset.data_vars[0].dims == ("SG",)
