"""Write the migration fixtures in packages/qdt-schemas/tests/fixtures/<Type>/v<n>.json.

Run after adding a persisted type or bumping a `schema_version`: `uv run python scripts/make_schema_fixtures.py`.
It writes only fixtures that do not exist yet. Old-version fixtures are history and are never rewritten;
the migration test loads every one of them through `migrations.load`.
"""

import json
import pathlib
from datetime import UTC, datetime

from qdt_lab.experiment import SimulatedEmitter, compile_sweep
from qdt_schemas.data import Annotation
from qdt_schemas.envelope import MeasurementRecord, PayloadRef
from qdt_schemas.identity import DeviceRecord
from qdt_schemas.migrations import PERSISTED, current_version
from qdt_sim.scenarios import DEVICE_ID, default_stand, stability

ROOT = pathlib.Path(__file__).resolve().parents[1] / "packages/qdt-schemas/tests/fixtures"
T0 = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def examples() -> dict[str, object]:
    stand = default_stand()
    definition = stability(4, 5, shots=2, reduce="mean", name="fixture stability 4x5")
    plan = compile_sweep(
        definition, stand, {"simulated": SimulatedEmitter()}, plan_id="0" * 31 + "1", created_at=T0
    )
    return {
        "StandConfig": stand,
        "SweepDefinition": definition,
        "ExecutionPlan": plan,
        "Dataset": plan.dataset,
        "Annotation": Annotation(
            annotation_id="a1",
            dataset_id=plan.dataset.dataset_id,
            kind="line",
            coords=("P1", "P2"),
            points=((0.0, 0.0), (0.05, 0.05)),
            label="transition",
        ),
        "DeviceRecord": DeviceRecord(
            device_id=DEVICE_ID, kind="double_dot", simulated=True, registered_at=T0
        ),
        "MeasurementRecord": MeasurementRecord(
            record_id="0" * 31 + "1",
            device_id=DEVICE_ID,
            stand_id=stand.stand_id,
            stand_sha256=stand.content_sha256(),
            definition_name=definition.name,
            definition_sha256=definition.content_sha256(),
            plan_id=plan.plan_id,
            source=plan.dataset.source,
            started_at=T0,
            finished_at=T0,
            outcome="completed",
            payload=PayloadRef(
                type="qdt-hdf5-v1",
                path="2026/10/" + "0" * 31 + "1.h5",
                sha256="0" * 64,
                size_bytes=0,
            ),
        ),
    }


if __name__ == "__main__":
    objects = examples()
    assert set(objects) == set(PERSISTED), "every persisted type needs an example"
    for name, obj in objects.items():
        path = ROOT / name / f"v{current_version(name)}.json"
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(obj.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        path.write_bytes(text.encode())  # LF on every platform
        print(f"wrote {path.relative_to(ROOT.parents[3])}")
