"""`scripts/make_sim_devices.py --check` compares a recompiled device file with the committed one within
Phantom's cross-platform bound, not text for text (#154)."""

import copy
import json

from make_sim_devices import FOLDER, same

DEVICE = json.loads((FOLDER / "two-dot-sige-a.json").read_text(encoding="utf-8"))


def scaled(device: dict, factor: float) -> dict:
    """A copy with every float multiplied by `factor`: another platform's last digits, or a real change."""
    out = copy.deepcopy(device)

    def walk(o):
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        return o * factor if isinstance(o, float) else o

    return walk(out)


def test_a_file_whose_floats_differ_in_their_last_digits_is_the_same_device():
    assert same(DEVICE, DEVICE)
    assert same(DEVICE, scaled(DEVICE, 1 + 1e-12))


def test_a_real_change_is_not_the_same_device():
    assert not same(DEVICE, scaled(DEVICE, 1 + 1e-6))
    other = copy.deepcopy(DEVICE)
    other["seed"] += 1
    assert not same(DEVICE, other)
    del other["seed"]
    assert not same(DEVICE, other)
    assert not same({"x": 0.5}, {"x": "0.5"}) and not same({"x": 1.0}, {"x": True})


def test_the_committed_files_are_what_their_recipes_compile_to_here():
    """The check itself, as check_all runs it, on this platform."""
    from make_sim_devices import compiled

    recipes = json.loads((FOLDER.parent / "recipes.json").read_text(encoding="utf-8"))
    for name, recipe in recipes.items():
        assert same(
            json.loads((FOLDER / f"{name}.json").read_text(encoding="utf-8")),
            json.loads(compiled(recipe)),
        )
