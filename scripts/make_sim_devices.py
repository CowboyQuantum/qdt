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
computed number outside the shape grid is about 1.5e-11)."""


def close(a, b, abs_tol: float = ABS) -> bool:
    """Two values agree: equal strings, integers, booleans and containers, and floats within `REL`
    relative (or `abs_tol` absolute)."""
    if isinstance(a, float) or isinstance(b, float):
        numbers = (int, float)
        if (
            isinstance(a, bool)
            or isinstance(b, bool)
            or not (isinstance(a, numbers) and isinstance(b, numbers))
        ):
            return False
        return math.isclose(a, b, rel_tol=REL, abs_tol=abs_tol)
    return a == b


def same(a, b) -> bool:
    """Two parsed device files agree: `differences` finds nothing."""
    return next(differences(a, b), None) is None


def differences(a, b, path: str = ""):
    """Every place two parsed device files disagree, as `path: a against b`: the same structure,
    strings and integers, and floats `close`, except that a shape-grid change
    (`.shape.changes[gate][node][quantity]`) is held within `REL` of the largest change of that
    quantity along that gate (ADR 0091). A change is a difference of compiled quantities, whose last
    digits differ between processors by about 1e-12 of the quantity (Phantom ADR 0033); a change a
    thousand times smaller than its quantity then differs by about 1e-9 of itself, as CI's runners
    showed."""
    if path == ".shape.changes" and isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for g, (rows, others) in enumerate(zip(a, b)):
            if [len(r) for r in rows] != [len(r) for r in others]:
                yield f"{path}[{g}]: rows of {[len(r) for r in rows]} against {[len(r) for r in others]}"
                continue
            scale = [max(abs(r[q]) for r in rows) for q in range(len(rows[0]))] if rows else []
            for i, (row, other) in enumerate(zip(rows, others)):
                for q, (x, y) in enumerate(zip(row, other)):
                    if not close(x, y, max(ABS, REL * scale[q])):
                        yield f"{path}[{g}][{i}][{q}]: {x!r} against {y!r}"
        return
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        for k in a:
            yield from differences(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            yield from differences(x, y, f"{path}[{i}]")
    elif not close(a, b):
        yield f"{path}: {repr(a)[:80]} against {repr(b)[:80]}"


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
        found = path.exists() and list(
            differences(json.loads(path.read_text(encoding="utf-8")), json.loads(text))
        )
        if found is False or found:
            where = f": {len(found)} values, first {'; '.join(found[:5])}" if found else ""
            bad.append(f"{name}: the recipe compiles to other text than the committed file{where}")
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
