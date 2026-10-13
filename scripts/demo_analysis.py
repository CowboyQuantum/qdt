"""Record a simulated stability diagram into a registry, analyse it, and print how to view it.

    uv run python scripts/demo_analysis.py [--root ~/.qdt/registry]
    uv run python -m qdt_registry --root <root> serve <record_id>     # then Flight Deck (corepack pnpm dev)

The same steps as Tutorial 03, against a registry you keep, so Flight Deck can show the transitions.
"""

import argparse
import pathlib
from datetime import UTC, datetime

from qdt_analysis.transitions import detect_transitions
from qdt_lab.experiment import Executor, RunRecorder, SimulatedEmitter, compile_sweep
from qdt_registry import Registry
from qdt_schemas.identity import DeviceRecord
from qdt_sim.scenarios import DEVICE_ID, default_device, default_stand, stability

p = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
p.add_argument("--root", type=pathlib.Path, default=pathlib.Path.home() / ".qdt" / "registry")
p.add_argument("--size", type=int, default=128)
p.add_argument("--seed", type=int, default=1)
a = p.parse_args()

registry = Registry.from_env(a.root)
registry.register_device(
    DeviceRecord(
        device_id=DEVICE_ID,
        kind="double_dot",
        simulated=True,
        registered_at=datetime(2026, 10, 13, tzinfo=UTC),  # fixed: re-registering stays identical
    )
)
stand = default_stand()
plan = compile_sweep(
    stability(a.size, a.size, p1=(0.03, 0.18), p2=(0.03, 0.18), name="demo stability"),
    stand,
    {"simulated": SimulatedEmitter()},
)
recorder = RunRecorder(plan, stand, DEVICE_ID, campaign="demo")
for _ in recorder.wrap(Executor(plan, {DEVICE_ID: default_device(seed=a.seed)}).run()).frames():
    pass
record, path = recorder.finish(a.root / "outbox")
registry.ingest(record, path)
result = detect_transitions(record, registry.payload(record.record_id))
registry.add_result(result)
print(f"record {record.record_id}: {result.status}, {len(result.annotations)} transition segments")
for e in result.estimates:
    print(f"  {e.name:16} {e.value:10.4f} {e.unit}")
print(f"\nview: uv run python -m qdt_registry --root {a.root} serve {record.record_id}")
print("then: cd apps/flightdeck; corepack pnpm dev   (open the URL it prints)")
