"""The stand state in force on a stand server (ADR 0075, 0085): limits, couplings and the held
operating point, loaded from the registry at start and written there as a new version on every change.

After a restart the held point of the latest version is *offered*, not applied: until a person
confirms it, the server holds nothing and no sweep inherits it. Confirming applies it to the
instruments and holds it (the state does not change, so no version is written). Discarding it, or
setting or releasing levels before confirming, writes a version that records what was not re-applied.
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from qdt_registry import Registry
from qdt_schemas.activity import FixedLevel
from qdt_schemas.operations import ChannelLimit, StandState
from qdt_schemas.stand import StandConfig

log = logging.getLogger(__name__)

SERVER = "qdt-server"
"""`StandState.set_by` for a version the server writes on its own (the first one)."""

DRIVABLE = frozenset({"level_source", "triggered_level_source", "sequencer", "waveform_source"})
"""Capabilities whose channels a sweep can drive: the channels a limit may name."""


def describe(levels: Sequence[FixedLevel]) -> str:
    """Levels as a person reads them in a reason, e.g. 'P1 = 0.05, SG = -0.04'."""
    return ", ".join(f"{lv.channel} = {lv.value:g}" for lv in levels) or "nothing"


class StandBook:
    """The latest `StandState` of one stand and whether its held point has been confirmed since
    this server started. Every change goes through `write`, which stores the next version."""

    def __init__(self, registry: Registry, stand: StandConfig) -> None:
        self.registry, self.stand = registry, stand
        try:
            self.state = registry.stand_state(stand.stand_id)
            self.confirmed = not self.state.held
            if self.state.held:
                log.info(
                    "stand state v%d holds %s: offered, not applied, until a person confirms it",
                    self.state.version,
                    describe(self.state.held),
                )
        except KeyError:
            self.state = self._store(
                StandState(
                    stand_id=stand.stand_id,
                    version=1,
                    set_by=SERVER,
                    set_at=datetime.now(UTC),
                    reason="first start of this stand: no limits, no couplings, nothing held",
                )
            )
            self.confirmed = True

    # --- what is in force ------------------------------------------------------------------------

    @property
    def held(self) -> dict[str, float]:
        """The operating point the server holds now: the latest version's, once confirmed."""
        return {lv.channel: lv.value for lv in self.state.held} if self.confirmed else {}

    @property
    def pending(self) -> tuple[FixedLevel, ...]:
        """The held point offered after a restart and not yet confirmed or discarded."""
        return () if self.confirmed else self.state.held

    # --- changes ---------------------------------------------------------------------------------

    def write(
        self,
        *,
        by: str,
        reason: str,
        limits: Sequence[ChannelLimit] | None = None,
        couplings: Mapping[str, Mapping[str, float]] | None = None,
        held: Sequence[FixedLevel] | None = None,
    ) -> StandState:
        """Store the next version with the given parts changed and the rest carried over. Raises
        ValueError (a pydantic ValidationError) for a state that contradicts itself, such as a held
        level beyond a new limit; nothing is stored then."""
        s = self.state
        new = StandState(
            stand_id=s.stand_id,
            version=s.version + 1,
            limits=tuple(limits) if limits is not None else s.limits,
            couplings={k: dict(v) for k, v in couplings.items()}
            if couplings is not None
            else s.couplings,
            held=tuple(held) if held is not None else s.held,
            set_by=by,
            set_at=datetime.now(UTC),
            reason=reason,
        )
        self.state = self._store(new)
        return self.state

    def check_channels(
        self,
        limits: Sequence[ChannelLimit] = (),
        couplings: Mapping[str, Mapping[str, float]] | None = None,
    ) -> None:
        """Raise ValueError for a limit on a channel no sweep can drive, or a coupling between
        channels that are not LevelSources of this stand; KeyError for a channel the stand lacks."""
        for lim in limits:
            channel = self.stand.channel(lim.channel)
            caps = set(self.stand.instrument(channel.instrument).capabilities)
            if not caps & DRIVABLE:
                raise ValueError(
                    f"channel {lim.channel!r} is on {channel.instrument!r}, which drives no level: "
                    "a limit there would limit nothing"
                )
        for axis, row in (couplings or {}).items():
            for ch in (axis, *row):
                channel = self.stand.channel(ch)
                if "level_source" not in self.stand.instrument(channel.instrument).capabilities:
                    raise ValueError(
                        f"coupling names {ch!r}, which is on {channel.instrument!r}, not a LevelSource"
                    )

    def _store(self, state: StandState) -> StandState:
        return self.registry.add_stand_state(state)
