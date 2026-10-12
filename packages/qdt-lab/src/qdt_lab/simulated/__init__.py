"""L0 backends: software doubles implementing the protocols exactly."""

import random


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
