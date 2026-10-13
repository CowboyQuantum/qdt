"""Tutorial 03 — analyse a run: query the registry, detect charge transitions, keep the result, see it.

Every tutorial in this folder is also a test. Read it top to bottom.
"""

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from qdt_analysis import charge_transitions, recovery
from qdt_analysis.transitions import axis_values
from qdt_lab.experiment import Executor, RunRecorder, SimulatedEmitter, compile_sweep
from qdt_lab.stream import PayloadSource, StreamServer, collect
from qdt_registry import Registry
from qdt_schemas.identity import DeviceRecord
from qdt_schemas.modeling import ScenarioRef
from qdt_sim.scenarios import DEVICE_ID, resolve

workdir = Path(tempfile.mkdtemp())

# 1. A measurement, with its scenario on record. A `ScenarioRef` names a qdt_sim scenario, a seed and
#    its parameters (ADR 0029): enough to regenerate the sweep, the seeded device, and therefore the
#    truth behind the data. `resolve` turns it back into the sweep and the device.
scenario = ScenarioRef(
    kind="simulation",
    name="stability",
    seed=3,
    parameters={
        "n_outer": 64,
        "n_inner": 64,
        "p1_start": -0.02,
        "p1_stop": 0.06,
        "p2_start": -0.02,
        "p2_stop": 0.06,
    },
)
sweep = resolve(scenario)
plan = compile_sweep(sweep.definition, sweep.stand, {"simulated": SimulatedEmitter()})

registry = Registry(workdir / "registry")
registry.register_device(
    DeviceRecord(
        device_id=DEVICE_ID, kind="double_dot", simulated=True, registered_at=datetime.now(UTC)
    )
)
recorder = RunRecorder(plan, sweep.stand, DEVICE_ID, campaign="tutorial-03")
for _ in recorder.wrap(Executor(plan, {DEVICE_ID: sweep.device}).run()).frames():
    pass
record, payload_file = recorder.finish(workdir / "outbox")
registry.ingest(record, payload_file)

# 2. Analysis runs from a query. qdt-analysis is pure (rule 5): it is handed the Dataset and its
#    arrays and returns an `AnalysisResult`; it never sees the registry. The result carries both
#    provenance legs: the measurement (Dataset, variable, record) and the scenario.
(found,) = registry.find(device_id=DEVICE_ID, campaign="tutorial-03")
payload = registry.payload(found.record_id)
result = charge_transitions(payload.dataset, payload.arrays, scenario, record_id=found.record_id)
assert result.summary["n_lines"] > 0
assert result.measurement.record_id == found.record_id
assert result.scenario == scenario

# 3. Keep it. The registry checks that the result names this record, that the Dataset is the record's,
#    and that every annotation fits the recorded coordinates (ADR 0030). Analyses sync like records.
registry.record_analysis(result)
assert registry.analyses(found.record_id) == [result]

# 4. See it. `python -m qdt_registry serve <record_id>` streams the payload and the record's analysis
#    annotations to Flight Deck, which draws them over the map in data coordinates. Here the reference
#    client receives the same stream.
overlays = [a for r in registry.analyses(found.record_id) for a in r.annotations]


async def replay():
    async with StreamServer() as server:
        await server.feed(PayloadSource(payload, found.record_id, annotations=overlays))
        return await collect(server.url)


received = asyncio.run(replay())[plan.dataset.dataset_id]
assert received.dataset.source.registry_ref == found.record_id
assert tuple(received.annotations) == result.annotations

# 5. Injection–recovery: the scenario knows the truth. Regenerate it from the result's own ScenarioRef
#    (the model's transition map on the recorded grid) and score the detected lines against it.
again = resolve(result.scenario)
_, p1 = axis_values(payload.dataset, payload.arrays, "P1")
_, p2 = axis_values(payload.dataset, payload.arrays, "P2")
grid = np.stack([*np.meshgrid(p1, p2, indexing="ij"), np.zeros((p1.size, p2.size))], axis=-1)
truth = np.isin(again.device.model.transition_map(grid), (1, 2))
scores = recovery(result, payload.dataset, payload.arrays, truth, tolerance=2.0)
assert scores.precision > 0.8 and scores.recall > 0.8, scores
