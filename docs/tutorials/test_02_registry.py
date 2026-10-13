"""Tutorial 02 — keep a run: record a sweep, store it in the registry, find it again, replay it.

Every tutorial in this folder is also a test. Read it top to bottom.
"""

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from qdt_lab.experiment import Executor, RunRecorder, SimulatedEmitter, compile_sweep
from qdt_lab.stream import PayloadSource, StreamServer, assemble, collect
from qdt_registry import Registry
from qdt_schemas.identity import DeviceRecord
from qdt_sim.scenarios import DEVICE_ID, default_device, default_stand, stability

workdir = Path(tempfile.mkdtemp())

# 1. A registry client: a local cache and payload store. It works with no server at all (ADR 0024);
#    `Registry.from_env` would also pick up QDT_REGISTRY_DSN / QDT_PAYLOAD_STORE for `sync()`.
registry = Registry(workdir / "registry")

# 2. Measurements are recorded against a registered device.
registry.register_device(
    DeviceRecord(
        device_id=DEVICE_ID,
        kind="double_dot",
        simulated=True,
        registered_at=datetime.now(UTC),
    )
)

# 3. Run a sweep as in Tutorial 01, with a RunRecorder around the stream. Whatever consumes the stream
#    (a StreamServer for Flight Deck, or a plain loop as here) also records it.
stand = default_stand()
plan = compile_sweep(stability(8, 12), stand, {"simulated": SimulatedEmitter()})
recorder = RunRecorder(plan, stand, DEVICE_ID, campaign="tutorial")
for _ in recorder.wrap(Executor(plan, {DEVICE_ID: default_device(seed=3)}).run()).frames():
    pass
record, payload_file = recorder.finish(workdir / "outbox")

# 4. Ingest: the registry checks the payload file against the record, then keeps both.
registry.ingest(record, payload_file)

# 5. The Step 3 question: which runs used this device, this stand, this experiment?
found = registry.find(
    device_id=DEVICE_ID,
    stand_sha256=stand.content_sha256(),
    definition_sha256=plan.definition.content_sha256(),
)
assert [r.record_id for r in found] == [record.record_id]


# 6. Replay it. `python -m qdt_registry serve <record_id>` does this for Flight Deck; here the reference
#    client receives it, and the Dataset says it came from the registry.
async def replay():
    async with StreamServer() as server:
        await server.feed(PayloadSource(registry.payload(record.record_id), record.record_id))
        return await collect(server.url)


received = asyncio.run(replay())[plan.dataset.dataset_id]
assert received.dataset.source.kind == "registry"
assert received.dataset.source.registry_ref == record.record_id
replayed = assemble(received.dataset, received.frames)["I_sensor"].values
np.testing.assert_array_equal(replayed, registry.payload(record.record_id).arrays["I_sensor"])
