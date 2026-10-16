"""Regenerate the committed `SimResult` fixtures in packages/qdt-server/tests/fixtures/ (ADR 0048).

Run only when a node, its method, its rule or the simulator changes:
`uv run python scripts/make_tuning_fixtures.py`. `test_tuning.py` reproduces each fixture's decided
quantities within tolerance and checks them against the model's truth. A fixture is the last node of
its tune-up (`SCENARIOS` lists the nodes in order; earlier nodes feed later ones, ADR 0049).
"""

import pathlib
import sys
import tempfile
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "packages/qdt-server/tests"))
from test_tuning import FIXTURES, SCENARIOS, run_scenario

from qdt_schemas.modeling import SimResult

if __name__ == "__main__":
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, (scenario, builders) in SCENARIOS.items():
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:  # Windows: sqlite may still be open
            outcomes, result, truth = run_scenario(scenario, builders, pathlib.Path(tmp))
        outcome = outcomes[-1]  # the tune-up's last node is the fixture's
        fixture = SimResult(
            scenario=scenario,
            node_id=outcome.node_id,
            outcome=outcome,
            estimates=result.estimates if result is not None else (),
            truth=truth,
            created_at=datetime.now(UTC),
        )
        path = FIXTURES / f"{name}.json"
        path.write_text(fixture.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}: {outcome.status}; {outcome.message}")
