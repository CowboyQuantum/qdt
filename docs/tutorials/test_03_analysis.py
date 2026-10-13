"""Tutorial 03 — analysis as a consumer: query a run, find its charge transitions, store the result,
and replay the run with the transitions drawn on it.

Every tutorial in this folder is also a test. Read it top to bottom.
"""

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from qdt_analysis.transitions import detect_transitions
from qdt_lab.experiment import Executor, RunRecorder, SimulatedEmitter, compile_sweep
from qdt_lab.stream import PayloadSource, StreamServer, collect
from qdt_registry import Registry
from qdt_schemas.identity import DeviceRecord
from qdt_sim.scenarios import DEVICE_ID, default_device, default_model, default_stand, stability

registry = Registry(Path(tempfile.mkdtemp()) / "registry")
registry.register_device(
    DeviceRecord(
        device_id=DEVICE_ID, kind="double_dot", simulated=True, registered_at=datetime.now(UTC)
    )
)

# 1. A stability diagram, recorded as in Tutorial 02. The window keeps both dots occupied, where the
#    honeycomb is periodic.
stand = default_stand()
plan = compile_sweep(
    stability(96, 96, p1=(0.03, 0.18), p2=(0.03, 0.18)), stand, {"simulated": SimulatedEmitter()}
)
recorder = RunRecorder(plan, stand, DEVICE_ID)
for _ in recorder.wrap(Executor(plan, {DEVICE_ID: default_device(seed=1)}).run()).frames():
    pass
registry.ingest(*recorder.finish(registry.root / "outbox"))

# 2. Analysis starts from a query, never from a file path.
[record] = registry.find(device_id=DEVICE_ID, definition_name=plan.definition.name)

# 3. A pure function: the record and its payload in, an AnalysisResult out. It knows what data it read
#    (record_id) and how (method: name, version, every parameter, content hash).
result = detect_transitions(record, registry.payload(record.record_id))
assert result.status == "ok" and result.record_id == record.record_id

# 4. The numbers: electrons per volt on each dot from each plunger, and the cross-capacitance ratios
#    a virtual-gate matrix is built from. The simulated device knows the truth.
truth = default_model().charge_lattice("P1", "P2")
ratio = result.estimate("cross_ratio_a").value
assert abs(ratio - truth[0, 1] / truth[0, 0]) < 0.02

# 5. Keep it. Results sync to the server with everything else.
registry.add_result(result)
assert registry.results(record_id=record.record_id) == [result]


# 6. Replay the run with the overlays: `python -m qdt_registry serve <record_id>` does this for Flight Deck,
#    which draws the detected transition segments on the map.
async def replay():
    overlays = [a for r in registry.results(record_id=record.record_id) for a in r.annotations]
    source = PayloadSource(
        registry.payload(record.record_id), record.record_id, annotations=overlays
    )
    async with StreamServer() as server:
        await server.feed(source)
        return await collect(server.url)


received = asyncio.run(replay())[plan.dataset.dataset_id]
assert {a.annotation_id for a in received.annotations} == {
    a.annotation_id for a in result.annotations
}
