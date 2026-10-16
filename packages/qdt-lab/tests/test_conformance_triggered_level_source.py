"""TriggeredLevelSource conformance (ADR 0064). Test names are the spec; drivers pass these unchanged.

The backends here fire the trigger from the host (`advance`): the simulated source directly, the
QDAC-II on its `bus` trigger source (`*TRG`). On the bench the same list advances on an external
input driven by the OPX's marker line; Probe 05 proves that wiring and the count."""

import pytest

from qdt_lab.protocols import LevelSource, TriggeredLevelSource

LIST = (0.1, 0.2, 0.3)


def test_backend_satisfies_both_protocols(triggered_level_source):
    assert isinstance(triggered_level_source, TriggeredLevelSource)
    assert isinstance(triggered_level_source, LevelSource)


def test_a_loaded_list_advances_one_point_per_trigger_and_starts_again_past_its_end(
    triggered_level_source,
):
    src = triggered_level_source
    src.set("ch00", -0.5)
    src.load("ch00", LIST)
    assert abs(src.get("ch00") + 0.5) < 1e-3  # nothing moves until the first trigger
    for expected in LIST:
        src.advance("ch00")
        assert abs(src.get("ch00") - expected) < 1e-3
    src.advance("ch00")  # past the end: the list starts again (the QDAC-II's behaviour, Probe 05)
    assert abs(src.get("ch00") - LIST[0]) < 1e-3
    src.release("ch00")
    assert abs(src.get("ch00") - LIST[0]) < 1e-3  # release holds the point the channel is at


def test_release_restores_set_and_a_second_load_replaces_the_list(triggered_level_source):
    src = triggered_level_source
    src.load("ch00", LIST)
    src.advance("ch00")
    src.load("ch00", (1.0, 2.0))
    src.advance("ch00")
    assert abs(src.get("ch00") - 1.0) < 1e-3
    src.release("ch00")
    src.release("ch00")  # idempotent
    src.set("ch00", 0.25)
    assert abs(src.get("ch00") - 0.25) < 1e-3


def test_a_list_needs_at_least_one_point(triggered_level_source):
    with pytest.raises(ValueError):
        triggered_level_source.load("ch00", ())
