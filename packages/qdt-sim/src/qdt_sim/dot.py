"""Constant-interaction double quantum dot with a charge sensor (ADR 0020).

Electrostatics only, no tunnel coupling, no spin: the classical honeycomb. Energies in eV, capacitances
in aF, voltages in V, charges in units of e. For gate voltages `V` the gate-induced charge on the dots
is `n_g = C_gate · V / E_UNIT`; the energy of occupation `N` is

    U(N) = ½ · E_UNIT · (N − n_g)ᵀ · C_dot⁻¹ · (N − n_g)      [eV]

(gate-only terms dropped). At electron temperature `T` the occupation is Boltzmann-distributed over a
window of integer states around `n_g`. A charge sensor (SET-like) sees a potential

    φ_s = α · V + β · ⟨N⟩ + δφ                                [V-equivalent]

and conducts a periodic train of thermally broadened Coulomb peaks in φ_s, so every dot transition shows
as a step in sensor current and the sensor's own peaks show as background stripes. Everything is a pure
function of (V, T, noise offsets): `SimulatedDevice` adds the time axis and the noise.
"""

import itertools
from dataclasses import dataclass, field

import numpy as np

E_CHARGE = 1.602176634e-19
E_UNIT = E_CHARGE / 1e-18
"""Volts per electron per aF: e / (1 aF). Converts aF·V to electrons and e²/aF to eV."""
K_B_EV = 8.617333262e-5
"""Boltzmann constant in eV/K."""


@dataclass(frozen=True)
class DoubleDotModel:
    """Parameters of the double dot and its sensor. Defaults are a plausible Si/SiGe-like device."""

    gate_names: tuple[str, ...] = ("P1", "P2", "SG")
    """Gate voltages the model takes, in this order: two plungers and the sensor gate."""
    c_dot: np.ndarray = field(default_factory=lambda: np.array([[85.0, -20.0], [-20.0, 90.0]]))
    """Dot capacitance matrix [[C1, -Cm], [-Cm, C2]] in aF (Cm = interdot mutual capacitance)."""
    c_gate: np.ndarray = field(
        default_factory=lambda: np.array([[12.0, 2.5, 0.3], [2.5, 11.5, 0.3]])
    )
    """Gate-to-dot capacitances [dot, gate] in aF; off-diagonals are cross-capacitance."""
    sensor_alpha: np.ndarray = field(default_factory=lambda: np.array([0.01, 0.01, 1.0]))
    """Sensor lever arm per gate: dφ_s/dV_gate (V/V)."""
    sensor_beta: np.ndarray = field(default_factory=lambda: np.array([-0.004, -0.003]))
    """Sensor potential shift per electron on each dot (V-equivalent)."""
    sensor_period_v: float = 0.25
    """Spacing of the sensor's Coulomb peaks in φ_s (V)."""
    sensor_width_v: float = 0.04
    """Thermal width of a sensor peak in φ_s (V)."""
    sensor_peak_a: float = 1.0e-9
    """Peak sensor current (A)."""
    sensor_background_a: float = 0.05e-9
    """Sensor current far from a peak (A)."""
    sensor_phase_v: float = -0.06
    """φ_s of one sensor peak (V); the rest follow at `sensor_period_v`. The default puts the empty
    dot at 1.5 widths above a peak, so ~20 added electrons walk the sensor up the flank monotonically."""
    temperature_k: float = 0.15
    """Electron temperature (K)."""
    window: int = 2
    """Integer occupations considered: round(n_g) ± window per dot."""

    def __post_init__(self) -> None:
        n_g = len(self.gate_names)
        if self.c_gate.shape != (2, n_g) or self.sensor_alpha.shape != (n_g,):
            raise ValueError(
                f"c_gate must be (2, {n_g}) and sensor_alpha ({n_g},) for gates {self.gate_names}"
            )
        if self.c_dot.shape != (2, 2) or self.sensor_beta.shape != (2,):
            raise ValueError("c_dot must be (2, 2) and sensor_beta (2,)")

    # --- electrostatics ------------------------------------------------------------------------

    def induced_charge(self, v: np.ndarray) -> np.ndarray:
        """Gate-induced charge on (dot 1, dot 2) in electrons for gate voltages `v` (last axis = gates)."""
        return np.asarray(v) @ self.c_gate.T / E_UNIT

    def energies(self, n_g: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Occupations `N` (k, 2) in the window around `n_g` (..., 2) and their energies (..., k) in eV."""
        n_g = np.asarray(n_g, dtype=float)
        center = np.rint(n_g).astype(int)
        offsets = np.array(
            list(itertools.product(range(-self.window, self.window + 1), repeat=2)), dtype=int
        )  # (k, 2)
        states = center[..., None, :] + offsets  # (..., k, 2)
        states = np.maximum(states, 0)
        d = states - n_g[..., None, :]
        c_inv = np.linalg.inv(self.c_dot)
        u = 0.5 * E_UNIT * np.einsum("...ki,ij,...kj->...k", d, c_inv, d)
        return states, u

    def occupation_probabilities(self, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """States (..., k, 2) and Boltzmann probabilities (..., k) at the model temperature."""
        states, u = self.energies(self.induced_charge(v))
        kt = K_B_EV * max(self.temperature_k, 1e-6)
        w = np.exp(-(u - u.min(axis=-1, keepdims=True)) / kt)
        return states, w / w.sum(axis=-1, keepdims=True)

    def mean_occupation(self, v: np.ndarray) -> np.ndarray:
        """Thermal-average occupation ⟨N⟩ (..., 2) for gate voltages `v`."""
        states, p = self.occupation_probabilities(v)
        return np.einsum("...k,...ki->...i", p, states)

    def sample_occupation(self, v: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        """One occupation (2,) drawn from the Boltzmann distribution at gate voltages `v` (1-D)."""
        states, p = self.occupation_probabilities(np.asarray(v, dtype=float))
        return states[rng.choice(len(p), p=p)]

    # --- sensor --------------------------------------------------------------------------------

    def sensor_potential(self, v: np.ndarray, n: np.ndarray, delta_phi: float = 0.0) -> np.ndarray:
        """φ_s for gate voltages `v` (..., gates) and occupation `n` (..., 2)."""
        return np.asarray(v) @ self.sensor_alpha + np.asarray(n) @ self.sensor_beta + delta_phi

    def sensor_current(self, phi: np.ndarray) -> np.ndarray:
        """Periodic thermally broadened Coulomb peaks: I(φ_s) in A."""
        p = self.sensor_period_v
        d = np.mod(np.asarray(phi) - self.sensor_phase_v + p / 2, p) - p / 2
        return self.sensor_background_a + self.sensor_peak_a / np.cosh(d / self.sensor_width_v) ** 2

    def current(self, v: np.ndarray, delta_phi: float = 0.0) -> np.ndarray:
        """Sensor current (A) at gate voltages `v` (..., gates) with thermal-average occupation."""
        return self.sensor_current(self.sensor_potential(v, self.mean_occupation(v), delta_phi))
