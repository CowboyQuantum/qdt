"""`SimulatedDevice`: a Phantom device behind qdt-lab's protocols for backend `simulated` (ADR 0020,
0087). The instrument is `qdt_lab.simulated.SimulatedInstrument`; `PhantomPhysics`, what it is connected
to, computes nothing: one Phantom `Session` with the device's gates and `"bias"` (the sensor's
source–drain voltage) as inputs and `"sensor"` (its current) as output, all programmed voltages."""

from collections.abc import Mapping

import numpy as np
from phantom.api import Device

from qdt_lab.simulated import SimulatedInstrument

SENSOR, BIAS = "sensor", "bias"
DEFAULT_BIAS_V = 50e-6
"""The source–drain bias the sensor is read at until a `bias` channel sets it (Phantom's default, V)."""


def roles(device: Device) -> dict[str, str]:
    """Vendor channel → role on the simulated stand: a DC channel per gate, a pulse channel on each
    plunger (`P1_pulse`), the bias on a DC and a pulse channel, and the sensor."""
    layout = device.knowable().layout["gates"]
    pulses = {f"{g['name']}_pulse": g["name"] for g in layout if g["role"] == "plunger"}
    return {
        **{g: g for g in device.gate_names},
        **pulses,
        BIAS: BIAS,
        "bias_pulse": BIAS,
        SENSOR: SENSOR,
    }


class PhantomPhysics:
    """`SimulatedPhysics` over one Phantom session. With charge dynamics off (the default) the charge a
    sample sees is an independent Boltzmann draw (`sample_charge`) or the thermal mean at that sample's
    levels; with `dynamics` it evolves on the session's clock (ADR 0090). Each input starts at `levels`,
    else at the programmed point."""

    output = SENSOR

    def __init__(
        self,
        device: Device,
        *,
        noise: bool = True,
        seed: int | None = None,
        sample_charge: bool = True,
        dynamics: bool = False,
        levels: Mapping[str, float] | None = None,
    ) -> None:
        self.device, self.inputs = device, (*device.gate_names, BIAS)
        programmed = dict(zip(device.gate_names, device.programmed_point_v))
        self.defaults = programmed | dict(levels or {}) | {BIAS: DEFAULT_BIAS_V}
        charge = "sampled" if sample_charge else "mean"
        self.session = device.session(noise, dynamics, charge, noise_seed=seed)
        if dynamics:  # the charge evolves through every hold and dwell: point by point (ADR 0093)
            self.sense_many = None  # type: ignore[method-assign]

    @property
    def clock_s(self) -> float:
        return self.session.time_s

    def _gates(self, levels: Mapping[str, float]) -> np.ndarray:
        return np.array([levels[g] for g in self.device.gate_names], dtype=float)

    def hold(self, levels: Mapping[str, float], duration_s: float) -> None:
        if duration_s > 0:
            self.session.hold(self._gates(levels), duration_s)

    def sense(self, levels: Mapping[str, float], dwell_s: float, samples: int, gap_s: float = 0.0):
        v, bias = self._gates(levels), levels[BIAS]
        if not gap_s:
            return self.session.sense(v, dwell_s, samples, v_sd=bias).current_a
        out = np.empty(samples)
        for k in range(samples):  # a shot's overhead passes at its levels before the shot is read
            self.session.hold(v, gap_s)
            out[k] = self.session.sense(v, dwell_s, 1, v_sd=bias).current_a[0]
        return out

    def sense_many(self, levels, dwell_s: float, gap_s: float = 0.0) -> np.ndarray:
        """One reading per entry of `levels` from one Phantom call (ADR 0093, #179): the session reads
        the points in order, `dwell_s` of clock each, then the shots' overheads pass together."""
        v = np.array([self._gates(lv) for lv in levels])
        bias = np.array([lv[BIAS] for lv in levels])
        out = np.asarray(self.session.sense(v, dwell_s, v_sd=bias).current_a, dtype=float)
        if gap_s > 0:
            self.session.hold(v[-1], gap_s * len(levels))
        return out


class SimulatedDevice(SimulatedInstrument):
    """A Phantom device through vendor channels with declared roles (default `roles`); built from a
    stand by `SimulatedDevice.from_config(instrument, channels, device, roles)` (ADR 0021). `seed` is
    the noise seed: a new noise realisation of the same device, whose disorder is in its file;
    `dynamics` and `levels` go to `PhantomPhysics`."""

    def __init__(
        self,
        device: Device,
        channels: Mapping[str, str] | None = None,
        *,
        noise: bool = True,
        seed: int | None = 0,
        sample_charge: bool = True,
        dynamics: bool = False,
        levels: Mapping[str, float] | None = None,
        **kwargs,
    ) -> None:
        options = {"noise": noise, "seed": seed, "sample_charge": sample_charge}
        physics = PhantomPhysics(device, **options, dynamics=dynamics, levels=levels)
        super().__init__(physics, channels or roles(device), **kwargs)

    @property
    def device(self) -> Device:
        return self.physics.device
