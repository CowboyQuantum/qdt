"""Regenerate the committed qdt-sim scenario fixture in packages/qdt-sim/tests/fixtures/.

Run only when the dot model, the noise models or `stability_fixture()` change:
`uv run python scripts/make_sim_fixtures.py`. The test reproduces it within rtol=1e-9.
"""

import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "packages/qdt-sim/tests"))
from test_scenario import FIXTURE, run_fixture

if __name__ == "__main__":
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    x = run_fixture()
    np.save(FIXTURE, x)
    print(f"wrote {FIXTURE} shape={x.shape} mean={x.mean():.3e} A std={x.std():.3e} A")
