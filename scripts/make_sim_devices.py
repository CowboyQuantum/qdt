"""Compile the simulator's device files in packages/qdt-sim/src/qdt_sim/devices/ from their recipes
(ADR 0087, 0088): the one writer of those files.

Run only when a recipe changes or qdt moves its Phantom pin: `uv run python scripts/make_sim_devices.py`.
It compiles each recipe in `qdt_sim/recipes.json` with the pinned Phantom, writes `<name>.json` (Phantom's
canonical text) and prints its SHA-256: paste the new hashes into `qdt_sim.scenarios.DEVICES`, then
regenerate the simulator fixtures (`make_sim_fixtures.py`, `make_tuning_fixtures.py`).
`--check` (check_all) writes nothing and fails when a recipe no longer compiles to its committed file
or a file's hash is not the one `DEVICES` pins. "Compiles to" is `same`: Phantom is bit for bit on one
platform and within 1e-9 relative across platforms (its CONTRACT.md), so floats compare within that and
everything else exactly (#154).
"""

import hashlib
import json
import math
import pathlib
import sys

from phantom.api import CompileParams, __version__, compile_device, two_dot_layout

from qdt_sim.scenarios import DEVICES

FOLDER = pathlib.Path(__file__).resolve().parents[1] / "packages/qdt-sim/src/qdt_sim/devices"


REL, ABS = 1e-9, 1e-15
"""Phantom's cross-platform bound, and a floor for a value that is zero on one platform (the smallest
computed number in a device file is about 2.5e-7)."""


def same(a, b) -> bool:
    """Two parsed device files agree: the same structure, strings and integers, and floats within
    `REL` relative (or `ABS` absolute)."""
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(map(same, a, b))
    if isinstance(a, float) or isinstance(b, float):
        numbers = (int, float)
        if (
            isinstance(a, bool)
            or isinstance(b, bool)
            or not (isinstance(a, numbers) and isinstance(b, numbers))
        ):
            return False
        return math.isclose(a, b, rel_tol=REL, abs_tol=ABS)
    return a == b


def compiled(recipe: dict) -> str:
    params = CompileParams(
        operating_point_v=recipe["operating_point_v"], **recipe.get("params", {})
    )
    return compile_device(two_dot_layout(**recipe["layout"]), params, seed=recipe["seed"]).dumps()


if __name__ == "__main__":
    check = "--check" in sys.argv[1:]
    recipes = json.loads((FOLDER.parent / "recipes.json").read_text(encoding="utf-8"))
    bad = []
    for name, recipe in recipes.items():
        path, text = FOLDER / f"{name}.json", compiled(recipe)
        if not check:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(
                f'"{name}": "{hashlib.sha256(path.read_bytes()).hexdigest()}",  # phantom {__version__}'
            )
            continue
        if not path.exists() or not same(
            json.loads(path.read_text(encoding="utf-8")), json.loads(text)
        ):
            bad.append(f"{name}: the recipe compiles to other text than the committed file")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != DEVICES.get(name):
            bad.append(f"{name}: the file's SHA-256 is not the one qdt_sim.scenarios.DEVICES pins")
    if set(DEVICES) != set(recipes):
        bad.append(f"DEVICES names {sorted(DEVICES)}, the recipes {sorted(recipes)}")
    if bad:
        print("make_sim_devices: FAIL\n  " + "\n  ".join(bad))
        sys.exit(1)
    if check:
        print(f"make_sim_devices: OK ({len(recipes)} devices, phantom {__version__})")
