"""Tutorial 01 — an experiment as data: declare a stability diagram, compile it, run it, assemble it.

Every tutorial in this folder is also a test. Read it top to bottom.
"""

import numpy as np

from qdt_lab.experiment import Executor, SimulatedEmitter, compile_sweep
from qdt_lab.simulated import SimulatedLevelSource, SimulatedSequencer
from qdt_lab.stream import assemble
from qdt_schemas.activity import SequencerStage, SweepAxis, SweepDefinition, SymbolBinding
from qdt_schemas.pulse import Measure, PulseSequence, Step, Symbol
from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig

# 1. The stand: instruments with capabilities, and logical channels experiments name (ADR 0016).
stand = StandConfig(
    stand_id="tutorial",
    instruments=(
        InstrumentConfig(id="dac", backend="simulated", capabilities=("level_source",)),
        InstrumentConfig(id="seq", backend="simulated", capabilities=("sequencer",)),
    ),
    channels=(
        ChannelMap(logical="gate_R", instrument="dac", channel="ch00", quantity="voltage"),
        ChannelMap(logical="gate_L", instrument="seq", channel="ao1", quantity="voltage"),
        ChannelMap(logical="sensor", instrument="seq", channel="ai1", quantity="voltage"),
    ),
)

# 2. The per-shot pulse sequence, backend-neutral (ADR 0018). `v_L` is a Symbol the sweep binds.
pixel = PulseSequence(
    name="read the sensor at a gate level",
    body=(
        Step(channel="gate_L", level=Symbol(name="v_L", unit="V"), duration=200),
        Measure(channel="sensor", duration=1000, result="I_sens"),
    ),
)

# 3. The experiment: outer gate stepped by the DAC, inner gate swept by the sequencer, 1 shot (ADR 0019).
stability = SweepDefinition(
    name="stability diagram",
    axes=(
        SweepAxis(name="gate_R", channel="gate_R", start=-0.5, stop=0.5, num=8),
        SweepAxis(name="gate_L", channel="gate_L", start=-1.0, stop=0.0, num=16),
    ),
    stage=SequencerStage(
        instrument="seq",
        axes=("gate_L",),
        sequence=pixel,
        bindings=(SymbolBinding(symbol="v_L", axis="gate_L"),),
    ),
)

# 4. Compile: channels resolved, the sequence emitted for the stand's sequencer backend, the Dataset declared.
plan = compile_sweep(stability, stand, {"simulated": SimulatedEmitter()})
assert [d.name for d in plan.dataset.dims] == ["gate_R", "gate_L"]
assert plan.stage_program.backend == "simulated"

# 5. Run against backends. The executor returns a stream Source; a server would feed it to Flight Deck.
source = Executor(plan, {"dac": SimulatedLevelSource(), "seq": SimulatedSequencer()}).run()
result = assemble(plan.dataset, source.frames())

# The generic simulated sequencer fills results with the flat loop index (Probe 01's oracle);
# qdt-sim's SimulatedDevice puts dot physics behind the same interface.
assert result["I_sens"].shape == (8, 16)
np.testing.assert_array_equal(result["I_sens"].values[3], np.arange(16.0))
np.testing.assert_allclose(result["gate_L"].values, np.linspace(-1.0, 0.0, 16))
