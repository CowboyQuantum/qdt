"""Record a simulated stability diagram (or the sensor's Coulomb diamonds) into a registry, analyse it,
and print how to view it.

    uv run python scripts/demo_analysis.py [--root ~/.qdt/registry] [--diamonds]
    uv run python -m qdt_registry --root <root> serve <record_id>     # then Flight Deck (corepack pnpm dev)

The same steps as Tutorial 03, against a registry you keep, so Flight Deck can show the transitions, or
with `--diamonds` the diamond edges, degeneracy points and diamonds of the sensor (ADR 0030), on the
simulator's default Phantom device (ADR 0088).
"""

import argparse
import pathlib
from datetime import UTC, datetime

from qdt_analysis.diamonds import detect_diamonds
from qdt_analysis.transitions import detect_transitions
from qdt_lab.experiment import Executor, RunRecorder, SimulatedEmitter, compile_sweep
from qdt_registry import Registry
from qdt_schemas.identity import DeviceRecord
from qdt_sim.scenarios import (
    DEVICE_ID,
    default_device,
    default_stand,
    diamonds,
    stability,
)

p = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
p.add_argument("--root", type=pathlib.Path, default=pathlib.Path.home() / ".qdt" / "registry")
p.add_argument("--size", type=int, default=64)
p.add_argument("--seed", type=int, default=1)
p.add_argument("--diamonds", action="store_true", help="the sensor's Coulomb diamonds instead")
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
if a.diamonds:
    definition = diamonds(a.size, a.size, name="demo diamonds")
    device = default_device(seed=a.seed, sample_charge=False)
    method = detect_diamonds
else:
    definition = stability(a.size, a.size, measure_ns=10_000_000, name="demo stability")
    device = default_device(seed=a.seed)
    method = detect_transitions
plan = compile_sweep(definition, stand, {"simulated": SimulatedEmitter()})
recorder = RunRecorder(plan, stand, DEVICE_ID, campaign="demo")
for _ in recorder.wrap(Executor(plan, {DEVICE_ID: device}).run()).frames():
    pass
record, path = recorder.finish(a.root / "outbox")
registry.ingest(record, path)
result = registry.add_result(*method(record, registry.payload(record.record_id)))
print(f"record {record.record_id}: {result.status}, {len(result.annotations)} overlays")
for e in result.estimates:
    print(f"  {e.name:16} {e.value:10.4f} {e.unit}")
print(f"\nview: uv run python -m qdt_registry --root {a.root} serve {record.record_id}")
print(f"  or the detection map: uv run python -m qdt_registry --root {a.root} serve --output {result.result_id}")
print("then: cd apps/flightdeck; corepack pnpm dev   (open the URL it prints)")
