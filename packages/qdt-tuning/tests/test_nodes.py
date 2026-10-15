"""A node is data the server can run: its method is in the catalogue with exactly these defaults, its
rule is in RULES, and its experiment compiles on both the simulator's stand and a bench-shaped one."""

from qdt_lab.experiment import SimulatedEmitter, compile_sweep
from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig
from qdt_server.catalogue import METHODS
from qdt_sim.scenarios import DEVICE_ID, default_stand
from qdt_tuning import RULES, charge_lattice, stability_diagram
from qdt_tuning.nodes import TRANSITIONS_DEFAULTS, TRANSITIONS_METHOD


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
