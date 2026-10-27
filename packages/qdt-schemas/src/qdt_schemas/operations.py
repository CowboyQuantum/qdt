"""Step 6c schema slice: operations — the state a stand is run under (ADR 0075, accepted by ADR 0084).

A `StandState` is the safety and operating state of one stand: a `ChannelLimit` per channel that has
one, the coupling matrix Flight Deck edits for coupled axes (ADR 0049), and the held operating point
(ADR 0053). It belongs to the stand, not to a browser: the stand server keeps it, enforces its limits
on every level it sets and every sweep it compiles, and writes every change as a new version with who
made it, when and why. Versions are append-only registry records; the latest one is in force.

A `QueuedRun` is one entry in a stand's run queue (ADR 0075, 0086): a run as asked for, waiting its
turn, then running, then finished, with who submitted it and the run and record it became. The stand
server keeps its queue in its own cache, so a restart keeps it; a `StandQueue` is the queue as the
server reports it, entries in order, and whether it is paused. The discovery types of ADR 0077 enter
with discovery. The slice is frozen at the step's exit by an ADR.
"""

import math
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from ._base import QdtModel
from .activity import FixedLevel
from .control import RunRequest

QueueState = Literal["queued", "running", "done", "aborted", "failed"]
"""queued → running → done | aborted | failed (ADR 0075). Removing a queued entry deletes it: it never
ran, so nothing is left to keep."""


class ChannelLimit(QdtModel):
    """The range one logical channel may be set to. A level outside it is refused, never clamped."""

    channel: str = Field(
        min_length=1, description="Logical channel (ChannelMap.logical) the limit applies to."
    )
    min_v: float = Field(
        allow_inf_nan=False,
        description=(
            "Lowest level allowed, inclusive, in the SI unit of the channel's quantity: volts for a "
            "voltage channel (the name's suffix), amperes for a current channel."
        ),
    )
    max_v: float = Field(
        allow_inf_nan=False,
        description="Highest level allowed, inclusive, in the same unit as `min_v`; not below it.",
    )

    @model_validator(mode="after")
    def _ordered(self) -> "ChannelLimit":
        if self.max_v < self.min_v:
            raise ValueError(
                f"limit on {self.channel!r}: max_v {self.max_v} is below min_v {self.min_v}"
            )
        return self

    def admits(self, low: float, high: float | None = None) -> bool:
        """True when every level from `low` to `high` (or `low` alone) lies within the limit. A NaN
        is never admitted."""
        high = low if high is None else high
        return self.min_v <= low <= self.max_v and self.min_v <= high <= self.max_v

    def describe(self) -> str:
        """The limit as a person reads it in a refusal, e.g. '[-0.5, 1.2]'."""
        return f"[{self.min_v:g}, {self.max_v:g}]"


class StandState(QdtModel):
    """One version of a stand's safety and operating state (ADR 0075). Append-only: a change writes
    the next version, and the highest version of a stand is the one in force."""

    stand_id: str = Field(
        min_length=1, description="StandConfig.stand_id of the stand this state belongs to."
    )
    version: int = Field(
        ge=1,
        description=(
            "1 for a stand's first state, then one more for every change; the registry refuses a gap "
            "or a second body under a version it holds."
        ),
    )
    limits: tuple[ChannelLimit, ...] = Field(
        default=(),
        description=(
            "Per-channel limits, at most one per channel. A channel without one is not limited by "
            "the stand state (its instrument's own range still applies)."
        ),
    )
    couplings: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description=(
            "The coupling matrix (ADR 0049): for the channel an axis steps, the volts per volt each "
            "other channel moves with it. The row of an axis's channel is what the Sweep widget puts "
            "in SweepAxis.couplings. No channel couples to itself; empty means no couplings."
        ),
    )
    held: tuple[FixedLevel, ...] = Field(
        default=(),
        description=(
            "The held operating point (ADR 0053): the DC levels the stand server applies and every "
            "sweep inherits on channels it does not touch, at most one per channel and each within "
            "its channel's limit. After a restart it is offered, and applied only once a person "
            "confirms it."
        ),
    )
    set_by: str = Field(
        min_length=1,
        description=(
            "Who made the change: the label of the command token it came with, 'local' for a "
            "command from the stand server's own computer, or the server itself (e.g. a tune-up)."
        ),
    )
    set_at: AwareDatetime = Field(description="When the stand server wrote this version.")
    reason: str = Field(
        min_length=1,
        description="Why it changed, in the words of the person who changed it or of the server.",
    )

    @model_validator(mode="after")
    def _consistent(self) -> "StandState":
        for what, channels in (
            ("limit", [lim.channel for lim in self.limits]),
            ("held level", [lv.channel for lv in self.held]),
        ):
            if len(set(channels)) != len(channels):
                raise ValueError(f"at most one {what} per channel")
        for axis, row in self.couplings.items():
            if axis in row:
                raise ValueError(f"channel {axis!r} couples to itself")
            for other, per_volt in row.items():
                if not math.isfinite(per_volt):
                    raise ValueError(f"coupling {axis!r} → {other!r} is not a finite number")
        beyond = self.violations({lv.channel: (lv.value, lv.value) for lv in self.held})
        if beyond:
            raise ValueError(f"the held point is beyond its limits: {'; '.join(beyond)}")
        return self

    def limit(self, channel: str) -> ChannelLimit | None:
        """The limit on `channel`, or None when it has none."""
        return next((lim for lim in self.limits if lim.channel == channel), None)

    def violations(self, extents: dict[str, tuple[float, float]]) -> list[str]:
        """One sentence per channel whose range of levels, `channel → (lowest, highest)`, leaves its
        limit; empty when everything is within. Channels without a limit are not checked."""
        out: list[str] = []
        for channel, (low, high) in sorted(extents.items()):
            lim = self.limit(channel)
            if lim is not None and not lim.admits(low, high):
                levels = f"{low:g}" if low == high else f"{low:g} to {high:g}"
                out.append(f"{channel} would reach {levels}, beyond its limit {lim.describe()}")
        return out


class QueuedRun(QdtModel):
    """One entry in a stand's run queue (ADR 0075, 0086). The stand server runs the entry at position 0
    when the stand is free and the queue is not paused; one run at a time, in order."""

    queue_id: str = Field(
        pattern=r"^[0-9a-f]{32}$", description="Server-minted UUID4 as 32 lowercase hex digits."
    )
    stand_id: str = Field(min_length=1, description="The stand whose queue holds the entry.")
    position: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Place among the waiting entries, 0 for the one that runs next; None once it has left the "
            "queue (running or finished)."
        ),
    )
    request: RunRequest = Field(description="The run as it was asked for: its sweep and its options.")
    submitted_by: str = Field(
        min_length=1,
        description="Who submitted it: the command token's label, or 'local' (as StandState.set_by).",
    )
    submitted_at: AwareDatetime = Field(description="When the stand server accepted it.")
    state: QueueState = Field(description="queued → running → done | aborted | failed.")
    run_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{32}$",
        description="The Run it started, once it left the queue; None while it waits.",
    )
    record_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{32}$",
        description="The MeasurementRecord its run produced (done, or aborted after some data).",
    )
    started_at: AwareDatetime | None = Field(default=None, description="When it left the queue.")
    finished_at: AwareDatetime | None = Field(
        default=None, description="When its run reached an end."
    )
    message: str = Field(
        default="", description="Why it failed or was aborted; empty otherwise."
    )

    @model_validator(mode="after")
    def _consistent(self) -> "QueuedRun":
        waiting = self.state == "queued"
        if waiting != (self.position is not None):
            raise ValueError("a queued entry has a position, and only a queued entry has one")
        if waiting and (self.run_id or self.started_at or self.finished_at):
            raise ValueError("a queued entry has not started")
        if self.state in ("done", "aborted", "failed") and self.finished_at is None:
            raise ValueError(f"a {self.state} entry says when it finished")
        if self.state == "failed" and not self.message:
            raise ValueError("a failed entry says why")
        return self


class StandQueue(QdtModel):
    """A stand's run queue as the stand server reports it (ADR 0086): the running entry, then the
    waiting ones in order, then the most recent finished ones, newest first."""

    stand_id: str = Field(min_length=1, description="The stand this queue runs on.")
    paused: bool = Field(
        description=(
            "True while the server starts no waiting entry: a person paused it, or the server "
            "restarted with entries waiting and a person has not resumed it."
        )
    )
    note: str = Field(default="", description="Why it is paused; empty when it is not.")
    entries: tuple[QueuedRun, ...] = Field(
        default=(), description="Running, then waiting by position, then finished, newest first."
    )

    @model_validator(mode="after")
    def _ordered(self) -> "StandQueue":
        positions = [e.position for e in self.entries if e.state == "queued"]
        if positions != list(range(len(positions))):
            raise ValueError("the waiting entries hold positions 0, 1, 2, … in order")
        if sum(e.state == "running" for e in self.entries) > 1:
            raise ValueError("one run at a time: at most one entry is running")
        return self
