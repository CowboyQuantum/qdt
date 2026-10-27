"""The operations slice (ADR 0075): a limit is a closed range, and a stand state is consistent with it."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from qdt_schemas.activity import FixedLevel, SensedLevel, SweepAxis, SweepDefinition
from qdt_schemas.control import RunRequest
from qdt_schemas.operations import ChannelLimit, QueuedRun, StandQueue, StandState

T0 = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def state(**update) -> StandState:
    base = {
        "stand_id": "sim-stand",
        "version": 1,
        "limits": (ChannelLimit(channel="P1", min_v=-0.5, max_v=0.5),),
        "couplings": {"P1": {"P2": -0.2}},
        "held": (FixedLevel(channel="P1", value=0.1),),
        "set_by": "local",
        "set_at": T0,
        "reason": "first limits",
    }
    return StandState(**(base | update))


def test_a_state_round_trips_through_json():
    s = state()
    assert StandState.model_validate_json(s.model_dump_json()) == s
    assert s.limit("P1") == ChannelLimit(channel="P1", min_v=-0.5, max_v=0.5)
    assert s.limit("P2") is None


def test_a_limit_is_a_closed_range_and_never_admits_nan():
    lim = ChannelLimit(channel="P1", min_v=-0.5, max_v=0.5)
    assert lim.admits(-0.5) and lim.admits(0.5) and lim.admits(-0.5, 0.5)
    assert not lim.admits(0.50001) and not lim.admits(-0.6, 0.0) and not lim.admits(0.0, 0.6)
    assert not lim.admits(float("nan"))
    with pytest.raises(ValidationError, match="below min_v"):
        ChannelLimit(channel="P1", min_v=0.5, max_v=-0.5)
    with pytest.raises(ValidationError):
        ChannelLimit(channel="P1", min_v=float("-inf"), max_v=0.5)


def test_violations_name_every_channel_beyond_its_limit_and_skip_channels_without_one():
    s = state(
        limits=(
            ChannelLimit(channel="P1", min_v=-0.5, max_v=0.5),
            ChannelLimit(channel="SG", min_v=0.0, max_v=0.2),
        )
    )
    assert s.violations({"P1": (-0.5, 0.5), "SG": (0.0, 0.2), "P2": (-9.0, 9.0)}) == []
    found = s.violations({"P1": (0.0, 0.7), "SG": (-0.1, -0.1)})
    assert found == [
        "P1 would reach 0 to 0.7, beyond its limit [-0.5, 0.5]",
        "SG would reach -0.1, beyond its limit [0, 0.2]",
    ]


def test_a_state_refuses_a_held_level_beyond_its_own_limit():
    with pytest.raises(ValidationError, match="held point is beyond its limits"):
        state(held=(FixedLevel(channel="P1", value=0.6),))


def test_a_state_refuses_duplicates_and_self_couplings():
    with pytest.raises(ValidationError, match="one limit per channel"):
        state(
            limits=(
                ChannelLimit(channel="P1", min_v=0, max_v=1),
                ChannelLimit(channel="P1", min_v=0, max_v=1),
            )
        )
    with pytest.raises(ValidationError, match="one held level per channel"):
        state(held=(FixedLevel(channel="P2", value=0), FixedLevel(channel="P2", value=0.1)))
    with pytest.raises(ValidationError, match="couples to itself"):
        state(couplings={"P1": {"P1": 1.0}})
    with pytest.raises(ValidationError, match="finite"):
        state(couplings={"P1": {"P2": float("nan")}})


def test_a_state_says_who_set_it_and_why():
    with pytest.raises(ValidationError):
        state(reason="")
    with pytest.raises(ValidationError):
        state(set_by="")
    with pytest.raises(ValidationError):
        state(version=0)
    with pytest.raises(ValidationError):
        state(set_at=datetime(2026, 10, 27, 12, 0))  # a time without a zone


# --- the run queue (ADR 0075, 0086) ----------------------------------------------------------------


def request() -> RunRequest:
    sweep = SweepDefinition(
        name="queued sweep",
        axes=(SweepAxis(name="P1", channel="P1", start=0.0, stop=0.1, num=3),),
        sensed=(SensedLevel(name="I", channel="sensor"),),
    )
    return RunRequest(definition=sweep, options={"seed": 1})


def entry(**update) -> QueuedRun:
    base = {
        "queue_id": "a" * 32,
        "stand_id": "sim-stand",
        "position": 0,
        "request": request(),
        "submitted_by": "local",
        "submitted_at": T0,
        "state": "queued",
    }
    return QueuedRun(**(base | update))


def test_a_queue_entry_round_trips_and_keeps_its_request():
    e = entry()
    assert QueuedRun.model_validate_json(e.model_dump_json()) == e
    assert e.request.definition.name == "queued sweep" and e.request.options == {"seed": 1}
    # a request body without schema_version, as scripts send it, is still a RunRequest
    assert RunRequest.model_validate({"definition": request().definition.model_dump(mode="json")})


def test_only_a_waiting_entry_has_a_position_and_a_finished_one_says_when_and_why():
    with pytest.raises(ValidationError, match="has a position"):
        entry(position=None)
    with pytest.raises(ValidationError, match="has a position"):
        entry(state="running", run_id="b" * 32, started_at=T0)
    with pytest.raises(ValidationError, match="has not started"):
        entry(run_id="b" * 32)
    running = entry(state="running", position=None, run_id="b" * 32, started_at=T0)
    assert running.position is None
    with pytest.raises(ValidationError, match="says when it finished"):
        entry(state="done", position=None, run_id="b" * 32, started_at=T0)
    with pytest.raises(ValidationError, match="says why"):
        entry(state="failed", position=None, finished_at=T0)


def test_a_stand_queue_holds_positions_in_order_and_one_running_entry():
    waiting = [entry(queue_id=f"{i:032x}", position=i) for i in range(3)]
    running = entry(
        queue_id="f" * 32, state="running", position=None, run_id="b" * 32, started_at=T0
    )
    q = StandQueue(stand_id="sim-stand", paused=False, entries=(running, *waiting))
    assert [e.position for e in q.entries] == [None, 0, 1, 2]
    with pytest.raises(ValidationError, match="positions 0, 1, 2"):
        StandQueue(stand_id="sim-stand", paused=False, entries=(waiting[1], waiting[0]))
    with pytest.raises(ValidationError, match="at most one entry is running"):
        StandQueue(
            stand_id="sim-stand",
            paused=False,
            entries=(running, running.model_copy(update={"queue_id": "e" * 32})),
        )
