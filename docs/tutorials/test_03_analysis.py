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
from qdt_sim.scenarios import DEVICE_ID, default_device, default_stand, load_device, stability

registry = Registry(Path(tempfile.mkdtemp()) / "registry")
registry.register_device(
    DeviceRecord(
        device_id=DEVICE_ID, kind="double_dot", simulated=True, registered_at=datetime.now(UTC)
    )
)

# 1. A stability diagram, recorded as in Tutorial 02. The default window sits about the device's
#    programmed point, where both dots hold electrons and the honeycomb is periodic; 10 ms a pixel keeps
#    the simulated readout noise (Phantom's, ADR 0088) well below a transition's step.
stand = default_stand()
plan = compile_sweep(
    stability(64, 64, measure_ns=10_000_000), stand, {"simulated": SimulatedEmitter()}
)
recorder = RunRecorder(plan, stand, DEVICE_ID)
for _ in recorder.wrap(Executor(plan, {DEVICE_ID: default_device(seed=1)}).run()).frames():
    pass
registry.ingest(*recorder.finish(registry.root / "outbox"))

# 2. Analysis starts from a query, never from a file path.
[record] = registry.find(device_id=DEVICE_ID, definition_name=plan.definition.name)

# 3. A pure function: the record and its payload in, an Analysis out: the AnalysisResult, which knows
#    what data it read (record_id) and how (method: name, version, every parameter, content hash), and
#    the arrays the method produced as a Dataset of its own (here the detection map), not yet stored.
result, output = detect_transitions(record, registry.payload(record.record_id))
assert result.status == "ok" and result.record_id == record.record_id
assert output.dataset.source.kind == "analysis" and result.output is None

# 4. The numbers: electrons per volt on each dot from each plunger, and the cross-capacitance ratios
#    a virtual-gate matrix is built from. The simulated device knows the truth (in a test only; a
#    server never shows it). This ratio is dot 1's, whose lines the device's slow noise bends between
#    rows, so one noisy map gets it only to about 0.05 (ADR 0091).
truth = load_device().truth(("P1", "P2")).charge_lattice_e_per_v
ratio = result.estimate("cross_ratio_a").value
assert abs(ratio - truth[0][1] / truth[0][0]) < 0.06

# 5. Keep it. The registry writes the output payload to its store and fills `result.output`; results and
#    their outputs sync to the server with everything else. The output reads back as a Dataset, and
#    `python -m qdt_registry serve --output <result_id>` streams it to Flight Deck like a measurement.
result = registry.add_result(result, output)
assert registry.results(record_id=record.record_id) == [result]
assert result.output is not None
assert registry.output(result.result_id).dataset == output.dataset


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
