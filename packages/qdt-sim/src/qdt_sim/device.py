"""`SimulatedDevice`: the double dot behind `LevelSource`, `LevelSense`, `Sequencer` and
`TriggeredLevelSource` (ADR 0020, 0064, 0087).

The instrument behaviour (channels and roles, the bias tee's sum, the sequencer interpreter, triggered
lists, captures, shot reduction, frames) is `qdt_lab.simulated.SimulatedInstrument`; this module is the
physics it is connected to. `DoubleDotPhysics` takes the model's gates and `"bias"` (the sensor's
source–drain voltage, ADR 0030, starting at the model's `sensor_bias_v`) as inputs and `"sensor"` as
its output. It keeps the clock (s) that every reading and every pulse duration advances; noise
processes are sampled on it. Pulse timing is otherwise quasi-static: the charge state at a reading is
the Boltzmann state (sampled per shot, or its mean) for the gate levels at that instant.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from qdt_lab.simulated import CompiledInstrumentProgram, SimulatedInstrument
from qdt_schemas.stand import ChannelMap, InstrumentConfig

from .dot import DoubleDotModel
from .noise import NoiseModel, NoNoise

SENSOR = "sensor"
BIAS = "bias"

CompiledDeviceProgram = CompiledInstrumentProgram  # the handle `SimulatedDevice.compile` returns


@dataclass
class DeviceNoise:
    """Where noise enters: common-mode gate offset (V), sensor potential offset (V), readout (A)."""

    gate: NoiseModel = field(default_factory=NoNoise)
    sensor: NoiseModel = field(default_factory=NoNoise)
    readout: NoiseModel = field(default_factory=NoNoise)


class DoubleDotPhysics:
    """`SimulatedPhysics` over a `DoubleDotModel` and its noise: inputs are the model's gates and the
    sensor bias, the output is the sensor current (A)."""

    output = SENSOR

    def __init__(
        self,
        model: DoubleDotModel,
        noise: DeviceNoise,
        *,
        seed: int = 0,
        sample_charge: bool = True,
    ) -> None:
        self.model, self.noise, self.sample_charge = model, noise, sample_charge
        self.inputs = (*model.gate_names, BIAS)
        self.defaults = {**dict.fromkeys(model.gate_names, 0.0), BIAS: model.sensor_bias_v}
        self._rng = np.random.default_rng(seed)
        self.clock_s = 0.0

    def hold(self, levels: Mapping[str, float], duration_s: float) -> None:
        self.clock_s += duration_s

    def sense(
        self, levels: Mapping[str, float], dwell_s: float, samples: int, gap_s: float = 0.0
    ) -> np.ndarray:
        v = np.array([levels[g] for g in self.model.gate_names], dtype=float)
        out = np.empty(samples)
        for s in range(samples):
            self.clock_s += dwell_s + gap_s
            t = self.clock_s
            v_eff = v + self.noise.gate.sample(t)
            n = (
                self.model.sample_occupation(v_eff, self._rng)
                if self.sample_charge
                else self.model.mean_occupation(v_eff)
            )
            phi = self.model.sensor_potential(v_eff, n, self.noise.sensor.sample(t))
            out[s] = self.model.sensor_current(phi, levels[BIAS]) + self.noise.readout.sample(t)
        return out


class SimulatedDevice(SimulatedInstrument):
    """A double dot with a charge sensor, addressable through vendor channels with declared roles."""

    def __init__(
        self,
        model: DoubleDotModel | None = None,
        channels: Mapping[str, str] | None = None,
        noise: DeviceNoise | None = None,
        *,
        seed: int = 0,
        sample_charge: bool = True,
        shot_overhead_s: float = 10e-6,
        sense_integration_s: float = 1e-3,
        points_per_second: float | None = None,
        integration_s: Mapping[str, float] | None = None,
    ) -> None:
        physics = DoubleDotPhysics(
            model or DoubleDotModel(),
            noise or DeviceNoise(),
            seed=seed,
            sample_charge=sample_charge,
        )
        super().__init__(
            physics,
            channels
            or {
                "P1": "P1",
                "P2": "P2",
                "SG": "SG",
                "P1_pulse": "P1",
                "P2_pulse": "P2",
                BIAS: BIAS,
                "bias_pulse": BIAS,
                SENSOR: SENSOR,
            },
            shot_overhead_s=shot_overhead_s,
            sense_integration_s=sense_integration_s,
            points_per_second=points_per_second,
            integration_s=integration_s,
        )

    @classmethod
    def from_config(
        cls,
        instrument: InstrumentConfig,
        channels: tuple[ChannelMap, ...],
        model: DoubleDotModel | None = None,
        roles: Mapping[str, str] | None = None,
        **kwargs,
    ) -> "SimulatedDevice":
        """`BackendFactory` (ADR 0021). `roles` maps vendor channel → gate, `"bias"` or `"sensor"`
        (default: the constructor's); every declared channel must have a role, and its quantity must
        match it."""
        cls._check_backend(instrument)
        return cls(model, roles, integration_s=cls._integration(channels), **kwargs)._declared(
            channels
        )

    @property
    def model(self) -> DoubleDotModel:
        return self.physics.model

    @property
    def noise(self) -> DeviceNoise:
        return self.physics.noise

    def gate_vector(self, pulse: Mapping[str, float] | None = None) -> np.ndarray:
        """Gate voltages in model order: DC levels plus pulse offsets, summed per gate role."""
        levels = self.levels(pulse)
        return np.array([levels[g] for g in self.model.gate_names], dtype=float)
