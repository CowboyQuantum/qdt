"""L0 backends: software doubles implementing the protocols exactly."""

import random


class SimulatedDCSource:
    """Ideal DC source with optional additive Gaussian noise for realism tests."""

    def __init__(self, noise_v: float = 0.0) -> None:
        self._v: dict[str, float] = {}
        self._noise = noise_v

    def set_voltage(self, channel: str, volts: float) -> None:
        self._v[channel] = volts

    def get_voltage(self, channel: str) -> float:
        base = self._v.get(channel, 0.0)
        return base + (random.gauss(0, self._noise) if self._noise else 0.0)
