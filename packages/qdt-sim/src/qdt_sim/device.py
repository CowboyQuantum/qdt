"""`SimulatedDevice`: the double dot behind `LevelSource`, `LevelSense`, `Sequencer` and
`TriggeredLevelSource` (ADR 0020, 0064).

One object, three capabilities, one set of vendor channels. Each channel has a role: a gate name of
the model (several channels may drive the same gate; their levels add, as a DC line and a pulse line
do through a bias tee), `"bias"` (the sensor's source–drain voltage, ADR 0030; channels add likewise,
and its DC level starts at the model's `sensor_bias_v`) or `"sensor"`. The device keeps a clock (s) that every integration and every
pulse duration advances; noise processes are sampled on it. Pulse timing is otherwise quasi-static:
the charge state at a `measure` is the Boltzmann state (sampled per shot, or its mean) for the gate
levels at that instant.

As a `Sequencer` it compiles only backend `"simulated"` programs: the body emitted by
`qdt_lab.experiment.SimulatedEmitter` (sequence JSON, symbol → parameter map, reductions). A body
with a `triggered` axis (ADR 0064) is the device triggering itself: at each point of that axis every
list loaded on it (`load`) sits on that point, as a marker line to a DAC would put it. A `capture` on
the device's own sensor channel (ADR 0069) is the device recording itself: `num` samples of the sensor
current at the shot's levels over the window, one record per shot.

Built from a stand with `SimulatedDevice.from_config` (the ADR 0021 `BackendFactory`): gate channels
must be declared `voltage`, the sensor `current`, and a sensor channel's `integration_s` is the device
time one `sense` integrates for (default `sense_integration_s`).
"""

import json
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import NamedTuple

import numpy as np

from qdt_lab.stream.frame import Frame
from qdt_schemas.activity import SequencerProgram
from qdt_schemas.data import Dataset, DatasetChunk, IndexSlice
from qdt_schemas.pulse import Affine, PulseSequence, Symbol
from qdt_schemas.stand import ChannelMap, InstrumentConfig

from .dot import DoubleDotModel
from .noise import NoiseModel, NoNoise

SENSOR = "sensor"
BIAS = "bias"


@dataclass
class DeviceNoise:
    """Where noise enters: common-mode gate offset (V), sensor potential offset (V), readout (A)."""

    gate: NoiseModel = field(default_factory=NoNoise)
    sensor: NoiseModel = field(default_factory=NoNoise)
    readout: NoiseModel = field(default_factory=NoNoise)


class CompiledDeviceProgram(NamedTuple):
    """Handle returned by `SimulatedDevice.compile`."""

    program: SequencerProgram
    sequence: PulseSequence
    symbols: dict[str, dict[str, str]]
    reduce: dict[str, str]
    compiled_id: str
    triggered: str | None = None  # the axis every loaded list follows (ADR 0064)


class SimulatedDevice:
    """A double dot with a charge sensor, addressable through vendor channels with declared roles."""

    backend = "simulated"

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
        self.model = model or DoubleDotModel()
        self.channels = dict(
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
            }
        )
        roles = set(self.model.gate_names) | {SENSOR, BIAS}
        bad = {ch: r for ch, r in self.channels.items() if r not in roles}
        if bad:
            raise ValueError(
                f"channel roles must be a gate of the model, 'bias' or 'sensor': {bad}"
            )
        if SENSOR not in self.channels.values():
            raise ValueError("the device needs a channel with role 'sensor'")
        self.noise = noise or DeviceNoise()
        self.sample_charge = sample_charge
        self.shot_overhead_s, self.sense_integration_s = shot_overhead_s, sense_integration_s
        self.points_per_second = points_per_second
        self.integration_s = dict(integration_s or {})
        unknown = set(self.integration_s) - set(self.channels)
        if unknown:
            raise ValueError(f"integration times for unknown channels {sorted(unknown)}")
        self._rng = np.random.default_rng(seed)
        self._dc: dict[str, float] = dict.fromkeys(self.channels, 0.0)
        self._lists: dict[str, tuple[float, ...]] = {}  # channel -> loaded list (ADR 0064)
        self._armed: dict[str, int] = {}  # channel -> index of the point last played
        bias = [ch for ch, role in self.channels.items() if role == BIAS]
        if bias:  # the sensor is read at its default bias until something sets it
            self._dc[bias[0]] = self.model.sensor_bias_v
        self.clock_s = 0.0

    @classmethod
    def from_config(
        cls,
        instrument: InstrumentConfig,
        channels: tuple[ChannelMap, ...],
        model: DoubleDotModel | None = None,
        roles: Mapping[str, str] | None = None,
        **kwargs,
    ) -> "SimulatedDevice":
        """`BackendFactory` (ADR 0021). `roles` maps vendor channel → gate or `"sensor"` (default: the
        constructor's); every declared channel must have a role, and its quantity must match it."""
        if instrument.backend != cls.backend:
            raise ValueError(
                f"SimulatedDevice serves backend 'simulated', not {instrument.backend!r}"
            )
        integration = {c.channel: c.integration_s for c in channels if c.integration_s is not None}
        device = cls(model, roles, integration_s=integration, **kwargs)
        for c in channels:
            role = device.channels.get(c.channel)
            if role is None:
                raise ValueError(f"channel {c.channel!r} has no role on the device")
            want = "current" if role == SENSOR else "voltage"
            if c.quantity != want:
                raise ValueError(f"channel {c.channel!r} ({role}) is {want}, declared {c.quantity}")
        return device

    # --- LevelSource ----------------------------------------------------------------------------

    def set(self, channel: str, value: float) -> None:
        self._check(channel)
        self._dc[channel] = float(value)

    def get(self, channel: str) -> float:
        self._check(channel)
        return self._dc[channel]

    # --- TriggeredLevelSource (ADR 0064) -----------------------------------------------------------

    def load(self, channel: str, values: Sequence[float]) -> None:
        self._check(channel)
        if not len(values):
            raise ValueError("a list needs at least one point")
        self._lists[channel] = tuple(float(v) for v in values)
        self._armed[channel] = -1

    def advance(self, channel: str) -> None:
        self._check(channel)
        if channel not in self._lists:
            raise ValueError(f"channel {channel!r} has no list loaded")
        self._play_point(channel, self._armed[channel] + 1)

    def release(self, channel: str) -> None:
        self._check(channel)
        self._lists.pop(channel, None)
        self._armed.pop(channel, None)

    def _play_point(self, channel: str, i: int) -> None:
        values = self._lists[channel]
        i = i % len(values)  # past the end the list starts again (Probe 05)
        self._armed[channel] = i
        self._dc[channel] = values[i]

    # --- LevelSense -----------------------------------------------------------------------------

    def sense(self, channel: str) -> float:
        self._check(channel)
        if self.channels[channel] != SENSOR:
            raise ValueError(
                f"channel {channel!r} is a gate ({self.channels[channel]}); sense the sensor"
            )
        aperture = self.integration_s.get(channel, self.sense_integration_s)
        return float(self.read(self.gate_vector(), 1, aperture, self.bias_level())[0])

    # --- Sequencer ------------------------------------------------------------------------------

    def compile(self, program: SequencerProgram) -> CompiledDeviceProgram:
        if program.backend != self.backend:
            raise ValueError(
                f"SimulatedDevice runs backend 'simulated' programs, not {program.backend!r}"
            )
        body = json.loads(program.body)
        sequence = PulseSequence.model_validate(body["sequence"])
        # a shot capture's channel is a scope's (ADR 0060) unless it is this device's own sensor, which
        # the device records itself (ADR 0069)
        scopes = {
            op.channel
            for op in sequence.expand()
            if op.op == "capture" and op.channel not in self.channels
        }
        unknown = set(sequence.channels()) - set(self.channels) - scopes
        if unknown:
            raise ValueError(f"sequence uses channels the device does not have: {sorted(unknown)}")
        for op in sequence.expand():
            if (
                op.op in ("measure", "capture")
                and op.channel in self.channels
                and self.channels[op.channel] != SENSOR
            ):
                raise ValueError(f"{op.op} on {op.channel!r}, which is not the sensor")
        return CompiledDeviceProgram(
            program,
            sequence,
            dict(body["symbols"]),
            dict(body.get("reduce", {})),
            f"{id(program):x}",
            (body.get("triggered") or {}).get("axis"),
        )

    def run(
        self, compiled: CompiledDeviceProgram, parameters: Mapping[str, int], dataset: Dataset
    ) -> "_DeviceRun":
        compiled.program.check_run(parameters, dataset)
        return _DeviceRun(self, compiled, dict(parameters), dataset)

    # --- physics with the clock and the noise ----------------------------------------------------

    def gate_vector(self, pulse: Mapping[str, float] | None = None) -> np.ndarray:
        """Gate voltages in model order: DC levels plus pulse offsets, summed per gate role."""
        v = np.zeros(len(self.model.gate_names))
        index = {g: i for i, g in enumerate(self.model.gate_names)}
        for ch, role in self.channels.items():
            if role in index:
                v[index[role]] += self._dc[ch] + (pulse or {}).get(ch, 0.0)
        return v

    def bias_level(self, pulse: Mapping[str, float] | None = None) -> float | None:
        """Sensor source–drain bias (V): DC levels plus pulse offsets of every `bias` channel, summed;
        None (the model's default) when the device has no bias channel."""
        chans = [ch for ch, role in self.channels.items() if role == BIAS]
        if not chans:
            return None
        return sum(self._dc[ch] + (pulse or {}).get(ch, 0.0) for ch in chans)

    def read(
        self,
        v: np.ndarray,
        shots: int,
        integration_s: float,
        v_sd: float | None = None,
        overhead_s: float | None = None,
    ) -> np.ndarray:
        """`shots` sensor-current samples (A) at gate voltages `v` and bias `v_sd` (None: the model's
        default), each advancing the clock by its integration and `overhead_s` (default: the shot
        overhead; 0 for the samples of one record)."""
        out = np.empty(shots)
        for s in range(shots):
            self.clock_s += integration_s + (
                self.shot_overhead_s if overhead_s is None else overhead_s
            )
            t = self.clock_s
            v_eff = v + self.noise.gate.sample(t)
            n = (
                self.model.sample_occupation(v_eff, self._rng)
                if self.sample_charge
                else self.model.mean_occupation(v_eff)
            )
            phi = self.model.sensor_potential(v_eff, n, self.noise.sensor.sample(t))
            out[s] = self.model.sensor_current(phi, v_sd) + self.noise.readout.sample(t)
        return out

    def _check(self, channel: str) -> None:
        if channel not in self.channels:
            raise ValueError(f"unknown channel {channel!r}; have {sorted(self.channels)}")


class _DeviceRun:
    """The `Source` a `SimulatedDevice.run` returns: one line (first-axis slab) per frame per result."""

    def __init__(
        self,
        device: SimulatedDevice,
        compiled: CompiledDeviceProgram,
        parameters: dict[str, int],
        dataset: Dataset,
    ) -> None:
        self._device, self._compiled, self._params = device, compiled, parameters
        self.dataset = dataset
        program = compiled.program
        # a capture on the device's own sensor (ADR 0069) is a result with its own time axis
        self._records = {
            op.result: op
            for op in compiled.sequence.expand()
            if op.op == "capture" and op.channel in device.channels
        }
        time_axes = {f"n_{r}" for r in self._records}
        # the stage axes are the parameters every result is laid over; a program with no result
        # (a stimulus whose readout is a shot capture on a scope, ADR 0060) still runs its shots
        self._axes = (
            tuple(d for d in program.results[0].dims if d != "shots" and d not in time_axes)
            if program.results
            else tuple(p.name for p in program.parameters if p.name.startswith("n_"))
        )
        self._shape = tuple(parameters[a] for a in self._axes)
        self._shots = parameters.get("shots", 1)

    def _symbol_values(self, index: tuple[int, ...]) -> dict[str, float]:
        program, params = self._compiled.program, self._params
        out = {}
        for name, spec in self._compiled.symbols.items():
            if "axis" in spec:
                i = index[self._axes.index(spec["axis"])]
                start = params[spec["start"]] * program.parameter(spec["start"]).scale
                step = params[spec["step"]] * program.parameter(spec["step"]).scale
                out[name] = start + i * step
            else:
                out[name] = params[spec["value"]] * program.parameter(spec["value"]).scale
        return out

    def _pixel(self, index: tuple[int, ...]) -> dict[str, np.ndarray]:
        """Run the sequence `shots` times at one pixel; result name → (shots,) samples. At a point of
        the triggered axis (ADR 0064) every loaded list is put on that point first: the device's own
        marker line."""
        device, ops = self._device, self._compiled.sequence.expand()
        if self._compiled.triggered is not None:
            i = index[self._axes.index(f"n_{self._compiled.triggered}")]
            for ch in list(device._lists):
                device._play_point(ch, i)
        values = self._symbol_values(index)

        def val(x):
            if isinstance(x, Symbol):
                return values[x.name]
            if isinstance(x, Affine):
                return x.of(values[x.symbol.name])
            return x

        samples: dict[str, list] = {}  # result -> per-shot values, or per-shot records
        for _ in range(self._shots):
            pulse: dict[str, float] = {}
            shot: dict[str, float] = {}
            for op in ops:
                if op.op == "difference":  # per shot, before any reduction; takes no time
                    shot[op.result] = shot[op.a] - shot[op.b]
                    samples.setdefault(op.result, []).append(shot[op.result])
                    continue
                duration_ns = val(op.duration)
                if op.op == "step":
                    pulse[op.channel] = val(op.level)
                elif op.op == "ramp":
                    pulse[op.channel] = val(op.stop)
                elif op.op == "measure":
                    i = device.read(
                        device.gate_vector(pulse), 1, duration_ns * 1e-9, device.bias_level(pulse)
                    )
                    shot[op.result] = float(i[0])
                    samples.setdefault(op.result, []).append(shot[op.result])
                    continue
                elif op.op == "capture" and op.channel in device.channels:
                    # ADR 0069: the device records its own sensor over the window: `num` samples of
                    # the current at the shot's levels, each one sample interval of clock
                    record = device.read(
                        device.gate_vector(pulse),
                        op.num,
                        duration_ns * 1e-9 / op.num,
                        device.bias_level(pulse),
                        overhead_s=0.0,
                    )
                    samples.setdefault(op.result, []).append(record)
                    continue
                device.clock_s += duration_ns * 1e-9
        return {k: np.asarray(v) for k, v in samples.items()}

    def _reduce(self, name: str, shots: np.ndarray) -> np.ndarray:
        """Reduce the shots axis (axis 1 of (pixels, shots[, samples])) as the stage says."""
        how = self._compiled.reduce.get(name, "keep")
        if how == "mean":
            return shots.mean(axis=1)
        if how == "sum":
            return shots.sum(axis=1)
        return shots if self._shots > 1 else np.take(shots, 0, axis=1)

    def frames(self) -> Iterator[Frame]:
        program, params = self._compiled.program, self._params
        variables = {v.name: v for v in self.dataset.data_vars}
        results = [r.name for r in program.results]
        if not results:
            for idx in np.ndindex(*self._shape) if self._shape else [()]:
                self._pixel(idx)  # the stimulus plays; the shot capture's scope records it
            return
        first = self._shape[0] if self._shape else 1
        rest = self._shape[1:]
        t0, done, seq = time.perf_counter(), 0, 0
        n_lines = first if len(self._shape) > 1 else 1
        for line in range(n_lines):
            if len(self._shape) > 1:
                indices = [(line, *idx) for idx in np.ndindex(*rest)]
            else:
                indices = [idx for idx in np.ndindex(*self._shape)] or [()]
            raw = {r: [] for r in results}
            for idx in indices:
                px = self._pixel(idx)
                for r in results:
                    raw[r].append(px[r])
            done += len(indices) * self._shots
            if self._device.points_per_second:
                delay = t0 + done / self._device.points_per_second - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
            for r in results:
                shots = np.stack(raw[r])  # (pixels in this frame, shots[, samples of a record])
                values = self._reduce(r, shots)
                keep = self._compiled.reduce.get(r, "keep") == "keep" and self._shots > 1
                tail = (
                    *((self._shots,) if keep else ()),
                    *((self._records[r].num,) if r in self._records else ()),
                )
                if len(self._shape) > 1:
                    values = values.reshape((1, *rest, *tail))
                else:
                    values = values.reshape((*self._shape, *tail))
                dims = variables[r].dims
                shape = program.result_shape(r, params)
                if len(self._shape) > 1:
                    region = (
                        IndexSlice(dim=dims[0], start=line, stop=line + 1),
                        *(
                            IndexSlice(dim=d, start=0, stop=n)
                            for d, n in zip(dims[1:], shape[1:], strict=True)
                        ),
                    )
                else:
                    region = tuple(
                        IndexSlice(dim=d, start=0, stop=n) for d, n in zip(dims, shape, strict=True)
                    )
                yield Frame(
                    DatasetChunk(
                        dataset_id=self.dataset.dataset_id,
                        seq=seq,
                        region=region,
                        variables=(r,),
                        produced_at=datetime.now(UTC),
                        final=line == n_lines - 1 and r == results[-1],
                    ),
                    {r: values.astype(variables[r].dtype)},
                )
                seq += 1
