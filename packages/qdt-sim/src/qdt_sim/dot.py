"""Constant-interaction double quantum dot with a charge sensor (ADR 0020).

Electrostatics only, no tunnel coupling, no spin: the classical honeycomb. Energies in eV, capacitances
in aF, voltages in V, charges in units of e. For gate voltages `V` the gate-induced charge on the dots
is `n_g = C_gate · V / E_UNIT`; the energy of occupation `N` is

    U(N) = ½ · E_UNIT · (N − n_g)ᵀ · C_dot⁻¹ · (N − n_g)      [eV]

(gate-only terms dropped). At electron temperature `T` the occupation is Boltzmann-distributed over a
window of integer states around `n_g`. A charge sensor (SET-like) sees a potential

    φ_s = α · V + β · ⟨N⟩ + δφ                                [V-equivalent]

and is itself a single-electron transistor (SET) with charging energy `E_c = sensor_charging_ev` and
lever arm `α_s = E_c / sensor_period_v` (eV per V of φ_s), biased by a source–drain voltage `V_sd`
(ADR 0030). Its levels are `μ_k = E_c·k − α_s·(φ_s − sensor_phase_v)`; sequential tunnelling at the
sensor's thermal energy `kT_s = α_s·sensor_width_v / 2` gives

    I = I_bg + I_0 · Σ_k [ f((μ_k − eV_sd/2)/kT_s) − f((μ_k + eV_sd/2)/kT_s) ],   f(x) = 1/(1+eˣ),

a periodic train of thermally broadened Coulomb peaks at small bias (every dot transition shows as a
step in sensor current; the sensor's own peaks show as background stripes) and Coulomb diamonds of
height `E_c/e` against `V_sd`. `I_0 = 4 kT_s · sensor_peak_a / (e · sensor_bias_v)` makes
`sensor_peak_a` the linear-response peak current at the default bias `sensor_bias_v`. Everything is a
pure function of (V, V_sd, T, noise offsets): `SimulatedDevice` adds the time axis and the noise.
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
    sensor_charging_ev: float = 1.0e-3
    """Charging energy of the sensor SET (eV): e times the bias at a Coulomb diamond's apex (ADR 0030)."""
    sensor_bias_v: float = 50e-6
    """Source–drain bias the sensor is read at unless a `bias` channel sets it (V). `sensor_peak_a` is
    the linear-response peak current at this bias; the diamonds' saturation current follows from it."""
    temperature_k: float = 0.15
    """Electron temperature of the dots (K). The sensor's own thermal width is `sensor_width_v`."""
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

    def charge_lattice(self, x_gate: str = "P1", y_gate: str = "P2") -> np.ndarray:
        """Electrons per volt on (dot 1, dot 2) from (x_gate, y_gate): rows of C_gate / e, shape (2, 2).

        The honeycomb is periodic under one-electron shifts of the gate-induced charge, so these rows are
        its reciprocal lattice vectors in the (x, y) gate plane: the injection truth that charge-lattice
        estimation must recover (away from the empty-dot corner, where the pattern is not periodic).
        """
        i, j = self.gate_names.index(x_gate), self.gate_names.index(y_gate)
        return self.c_gate[:, [i, j]] / E_UNIT

    # --- sensor --------------------------------------------------------------------------------

    def sensor_potential(self, v: np.ndarray, n: np.ndarray, delta_phi: float = 0.0) -> np.ndarray:
        """φ_s for gate voltages `v` (..., gates) and occupation `n` (..., 2)."""
        return np.asarray(v) @ self.sensor_alpha + np.asarray(n) @ self.sensor_beta + delta_phi

    @property
    def sensor_lever_arm(self) -> float:
        """α_s: sensor level shift per volt of φ_s (eV/V); one period in φ_s adds one electron."""
        return self.sensor_charging_ev / self.sensor_period_v

    @property
    def sensor_kt_ev(self) -> float:
        """Thermal energy of the sensor SET (eV), set so its zero-bias peaks have width `sensor_width_v`."""
        return self.sensor_lever_arm * self.sensor_width_v / 2

    def sensor_levels(self, phi: np.ndarray) -> np.ndarray:
        """μ_k (..., 5) in eV: the five sensor levels nearest the bias window at potential `phi`."""
        x = (np.asarray(phi, dtype=float) - self.sensor_phase_v) / self.sensor_period_v
        k = np.rint(x)[..., None] + np.arange(-2, 3)
        return self.sensor_charging_ev * (k - x[..., None])

    def sensor_current(self, phi: np.ndarray, v_sd: float | np.ndarray | None = None) -> np.ndarray:
        """Sensor current (A) at potential `phi` and source–drain bias `v_sd` (V; default
        `sensor_bias_v`): thermally broadened Coulomb peaks at small bias, diamonds at finite bias."""
        v_sd = self.sensor_bias_v if v_sd is None else np.asarray(v_sd, dtype=float)
        kt = self.sensor_kt_ev
        mu = self.sensor_levels(phi)
        half = np.asarray(v_sd)[..., None] / 2  # eV numerically, for V_sd in V
        with np.errstate(over="ignore"):
            window = 1 / (1 + np.exp((mu - half) / kt)) - 1 / (1 + np.exp((mu + half) / kt))
        i_0 = 4 * kt * self.sensor_peak_a / self.sensor_bias_v
        return self.sensor_background_a + i_0 * window.sum(axis=-1)

    def diamond_edges(self, k: int) -> tuple[tuple[float, float], tuple[float, float]]:
        """The two Coulomb-diamond edge lines through the k-th zero-bias degeneracy point, as
        (φ_s intercept at V_sd = 0, slope dV_sd/dφ_s): the edge rising with φ_s and the falling one.
        An edge is where level k crosses a lead: μ_k = ±eV_sd/2 → V_sd = ±2 α_s (φ_s − φ_k)."""
        phi_k = self.sensor_phase_v + k * self.sensor_period_v
        s = 2 * self.sensor_lever_arm
        return (phi_k, s), (phi_k, -s)

    def current(
        self, v: np.ndarray, delta_phi: float = 0.0, v_sd: float | np.ndarray | None = None
    ) -> np.ndarray:
        """Sensor current (A) at gate voltages `v` (..., gates) with thermal-average occupation."""
        return self.sensor_current(
            self.sensor_potential(v, self.mean_occupation(v), delta_phi), v_sd
        )
