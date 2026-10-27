"""Step 6c schema slice: operations — the state a stand is run under (ADR 0075, accepted by ADR 0084).

A `StandState` is the safety and operating state of one stand: a `ChannelLimit` per channel that has
one, the coupling matrix Flight Deck edits for coupled axes (ADR 0049), and the held operating point
(ADR 0053). It belongs to the stand, not to a browser: the stand server keeps it, enforces its limits
on every level it sets and every sweep it compiles, and writes every change as a new version with who
made it, when and why. Versions are append-only registry records; the latest one is in force.

`QueuedRun` (ADR 0075) enters with the run queue it describes (Step 6c deliverable 8), in the same
commit as its consumer; the discovery types of ADR 0077 enter with discovery. The slice is frozen at
the step's exit by an ADR.
"""

import math

from pydantic import AwareDatetime, Field, model_validator

from ._base import QdtModel
from .activity import FixedLevel


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
