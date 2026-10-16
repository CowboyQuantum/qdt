"""Simulated level terminals."""

import random
import time
from collections.abc import Callable, Iterable, Sequence

from qdt_schemas.stand import ChannelMap, InstrumentConfig

from ..protocols import LevelSource


class SimulatedLevelSource:
    """Ideal level source with optional additive Gaussian noise on readback for realism tests. Also a
    `TriggeredLevelSource` (ADR 0064): a loaded list advances on `advance`, the host-fired trigger."""

    def __init__(self, noise: float = 0.0) -> None:
        self._levels: dict[str, float] = {}
        self._noise = noise
        self._lists: dict[str, tuple[tuple[float, ...], int]] = {}  # channel -> (values, index)

    @classmethod
    def from_config(
        cls, instrument: InstrumentConfig, channels: tuple[ChannelMap, ...], **kwargs
    ) -> "SimulatedLevelSource":
        """`BackendFactory` (ADR 0021): an ideal source has nothing to take from its channels."""
        return cls(**kwargs)

    def set(self, channel: str, value: float) -> None:
        self.release(channel)
        self._levels[channel] = value

    def get(self, channel: str) -> float:
        base = self._levels.get(channel, 0.0)
        return base + (random.gauss(0, self._noise) if self._noise else 0.0)

    # --- TriggeredLevelSource (ADR 0064) -----------------------------------------------------------

    def load(self, channel: str, values: Sequence[float]) -> None:
        if not len(values):
            raise ValueError("a list needs at least one point")
        self._lists[channel] = (tuple(float(v) for v in values), -1)

    def advance(self, channel: str) -> None:
        if channel not in self._lists:
            raise ValueError(f"channel {channel!r} has no list loaded")
        values, i = self._lists[channel]
        i = (i + 1) % len(values)  # past the end the list starts again (Probe 05)
        self._lists[channel] = (values, i)
        self._levels[channel] = values[i]

    def release(self, channel: str) -> None:
        self._lists.pop(channel, None)

    def armed(self) -> tuple[str, ...]:
        """Simulation-only: the channels with a list loaded, for a simulated sequencer's trigger."""
        return tuple(self._lists)


class SimulatedLevelSense:
    """Senses a level. By default it follows a paired `LevelSource` (the L0 model of the L1 loopback,
    QDAC → sense), through an optional `load` function of (channel, applied level); without a source it
    returns what `set_reading` stored. Optional Gaussian noise.

    A channel declared with `integration_s` takes at least that long to sense (wall clock, through
    `sleep`), as a real aperture does; undeclared channels return at once (ADR 0021)."""

    def __init__(
        self,
        follow: LevelSource | None = None,
        load: Callable[[str, float], float] | None = None,
        noise: float = 0.0,
        channels: Iterable[ChannelMap] = (),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._follow, self._load, self._noise = follow, load, noise
        self._readings: dict[str, float] = {}
        self._integration = {c.channel: c.integration_s for c in channels if c.integration_s}
        self._sleep = sleep

    @classmethod
    def from_config(
        cls, instrument: InstrumentConfig, channels: tuple[ChannelMap, ...], **kwargs
    ) -> "SimulatedLevelSense":
        """`BackendFactory` (ADR 0021): keeps each channel's integration time."""
        return cls(channels=channels, **kwargs)

    def set_reading(self, channel: str, value: float) -> None:
        """Simulation-only: what `sense` returns on `channel` when not following a source."""
        self._readings[channel] = value

    def sense(self, channel: str) -> float:
        if channel in self._integration:
            self._sleep(self._integration[channel])
        base = self._follow.get(channel) if self._follow else self._readings.get(channel, 0.0)
        value = self._load(channel, base) if self._load else base
        return value + (random.gauss(0, self._noise) if self._noise else 0.0)
