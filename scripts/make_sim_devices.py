"""Compile the simulator's device files in packages/qdt-sim/src/qdt_sim/devices/ from their recipes
(ADR 0087, 0088): the one writer of those files.

Run only when a recipe changes or qdt moves its Phantom pin: `uv run python scripts/make_sim_devices.py`.
It compiles each recipe in `qdt_sim/recipes.json` with the pinned Phantom, writes `<name>.json` (Phantom's
canonical text) and prints its SHA-256 and its sensor set point: paste the new hashes into
`qdt_sim.scenarios.DEVICES` and the set points into `SENSOR_SET_V` (ADR 0090), then
regenerate the simulator fixtures (`make_sim_fixtures.py`, `make_tuning_fixtures.py`).
`--check` (check_all) writes nothing and fails when a recipe no longer compiles to its committed file
or a file's hash is not the one `DEVICES` pins, or a set point is not the one `SENSOR_SET_V` holds. "Compiles to" is `same`: Phantom is bit for bit on one
platform and within 1e-9 relative across platforms (its CONTRACT.md), so floats compare within that and
everything else exactly (#154).
"""

import hashlib
import json
import math
import pathlib
import sys

from phantom.api import CompileParams, Device, __version__, compile_device, optimum, two_dot_layout

from qdt_sim.scenarios import DEVICES, SENSOR_SET_V, SENSOR_TAIL_V

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


def set_point(text: str) -> float:
    """Where a fresh stand holds a device file's sensor gate, to 1 µV (`SENSOR_SET_V`, ADR 0090):
    `SENSOR_TAIL_V` from the wing of the sensor's peak a period above Phantom's set point."""
    device = Device.loads(text)
    sharp = optimum(device).sensor.v_sensor_gate_v
    broad = device.truth(near_v=sharp + device.truth(near_v=sharp).sensor.period_v).sensor
    return round(broad.wing_v + SENSOR_TAIL_V, 6)


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
            print(f'  SENSOR_SET_V "{name}": {set_point(text)}')
            continue
        if not path.exists() or not same(
            json.loads(path.read_text(encoding="utf-8")), json.loads(text)
        ):
            bad.append(f"{name}: the recipe compiles to other text than the committed file")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != DEVICES.get(name):
            bad.append(f"{name}: the file's SHA-256 is not the one qdt_sim.scenarios.DEVICES pins")
        elif not math.isclose(set_point(text), SENSOR_SET_V.get(name, math.nan), abs_tol=2e-6):
            bad.append(f"{name}: its sensor set point is not the one SENSOR_SET_V holds")
    if set(DEVICES) != set(recipes) or set(SENSOR_SET_V) != set(recipes):
        bad.append(
            f"DEVICES names {sorted(DEVICES)}, SENSOR_SET_V {sorted(SENSOR_SET_V)}, "
            f"the recipes {sorted(recipes)}"
        )
    if bad:
        print("make_sim_devices: FAIL\n  " + "\n  ".join(bad))
        sys.exit(1)
    if check:
        print(f"make_sim_devices: OK ({len(recipes)} devices, phantom {__version__})")
