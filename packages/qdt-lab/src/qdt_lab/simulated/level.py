"""Simulated level terminals."""

import random
from collections.abc import Callable

from ..protocols import LevelSource


class SimulatedLevelSource:
    """Ideal level source with optional additive Gaussian noise on readback for realism tests."""

    def __init__(self, noise: float = 0.0) -> None:
        self._levels: dict[str, float] = {}
        self._noise = noise

    def set(self, channel: str, value: float) -> None:
        self._levels[channel] = value

    def get(self, channel: str) -> float:
        base = self._levels.get(channel, 0.0)
        return base + (random.gauss(0, self._noise) if self._noise else 0.0)


class SimulatedLevelSense:
    """Senses a level. By default it follows a paired `LevelSource` (the L0 model of the L1 loopback,
    QDAC → sense), through an optional `load` function of (channel, applied level); without a source it
    returns what `set_reading` stored. Optional Gaussian noise."""

    def __init__(
        self,
        follow: LevelSource | None = None,
        load: Callable[[str, float], float] | None = None,
        noise: float = 0.0,
    ) -> None:
        self._follow, self._load, self._noise = follow, load, noise
        self._readings: dict[str, float] = {}

    def set_reading(self, channel: str, value: float) -> None:
        """Simulation-only: what `sense` returns on `channel` when not following a source."""
        self._readings[channel] = value

    def sense(self, channel: str) -> float:
        base = self._follow.get(channel) if self._follow else self._readings.get(channel, 0.0)
        value = self._load(channel, base) if self._load else base
        return value + (random.gauss(0, self._noise) if self._noise else 0.0)
