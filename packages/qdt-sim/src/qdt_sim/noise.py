"""Noise processes with a time axis (ADR 0020).

Every model is sampled at monotonically increasing times `t` (seconds) and returns a value in the unit
of whatever it is added to (a gate-voltage-equivalent offset, or amperes of readout noise). Processes
are stateful and seeded, so a run is reproducible for a given seed.

- `WhiteNoise`: memoryless Gaussian; readout noise per shot.
- `TelegraphNoise`: one two-level fluctuator with up/down rates; a single dominant charge trap.
- `OneOverFNoise`: an ensemble of symmetric fluctuators with log-uniform rates between `f_min` and
  `f_max`, whose summed spectrum is ~1/f in that band; slow charge noise that drifts the honeycomb and
  the sensor working point between pixels and between repeats.
- `Composite`: sum of models.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class NoiseModel(Protocol):
    def sample(self, t: float) -> float:
        """Value at time `t` (s); `t` never decreases between calls."""
        ...


@dataclass
class WhiteNoise:
    sigma: float
    seed: int = 0
    _rng: np.random.Generator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def sample(self, t: float) -> float:
        return float(self._rng.normal(0.0, self.sigma)) if self.sigma else 0.0


@dataclass
class TelegraphNoise:
    """Two-level fluctuator: value ±amplitude/2, switching with `rate_up` (0→1) and `rate_down` (1→0) Hz.

    Advancing by Δt uses the exact two-state Markov propagator, so the state is sampled correctly for any
    Δt (no time step to tune)."""

    amplitude: float
    rate_up: float
    rate_down: float
    seed: int = 0
    _rng: np.random.Generator = field(init=False, repr=False)
    _state: int = field(init=False, repr=False)
    _t: float | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if self.rate_up < 0 or self.rate_down < 0 or self.rate_up + self.rate_down <= 0:
            raise ValueError("rates must be non-negative with a positive sum")
        self._rng = np.random.default_rng(self.seed)
        p_up = self.rate_up / (self.rate_up + self.rate_down)
        self._state = int(self._rng.random() < p_up)

    def sample(self, t: float) -> float:
        if self._t is not None and t > self._t:
            total = self.rate_up + self.rate_down
            p_inf = self.rate_up / total
            decay = np.exp(-total * (t - self._t))
            p_one = p_inf + (self._state - p_inf) * decay
            self._state = int(self._rng.random() < p_one)
        self._t = t
        return self.amplitude * (self._state - 0.5)


@dataclass
class OneOverFNoise:
    """Sum of `n_fluctuators` symmetric telegraph processes, rates log-uniform in [f_min, f_max] Hz,
    scaled so the total rms is `amplitude`."""

    amplitude: float
    f_min: float = 1e-2
    f_max: float = 1e4
    n_fluctuators: int = 24
    seed: int = 0
    _fluctuators: list[TelegraphNoise] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not 0 < self.f_min < self.f_max:
            raise ValueError("need 0 < f_min < f_max")
        rng = np.random.default_rng(self.seed)
        rates = np.exp(rng.uniform(np.log(self.f_min), np.log(self.f_max), self.n_fluctuators))
        a = 2.0 * self.amplitude / np.sqrt(self.n_fluctuators)  # each ±a/2 → variance a²/4
        self._fluctuators = [
            TelegraphNoise(a, float(r) / 2, float(r) / 2, seed=int(rng.integers(2**31)))
            for r in rates
        ]

    def sample(self, t: float) -> float:
        return float(sum(f.sample(t) for f in self._fluctuators))


@dataclass
class Composite:
    models: tuple[NoiseModel, ...]

    def sample(self, t: float) -> float:
        return float(sum(m.sample(t) for m in self.models))


class NoNoise:
    def sample(self, t: float) -> float:
        return 0.0
