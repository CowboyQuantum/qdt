"""`SimulatedInstrument`: a simulated stand behind `LevelSource`, `LevelSense`, `Sequencer` and
`TriggeredLevelSource` for backend `simulated` (ADR 0020, 0064, 0087), over a `SimulatedPhysics`.

The instrument is the interpreter; the physics is what it is connected to. Each vendor channel has a
role: one of the physics' inputs (several channels may drive the same input; their levels add, as a DC
line and a pulse line do through a bias tee) or its output, the one quantity the instrument reads. The
first channel of each input starts at the physics' default level for it; an input with no channel
stays at that default. The physics owns the clock: every reading and every pulse duration advances it,
through `sense` and `hold`, and nothing else does.

As a `Sequencer` it compiles only backend `"simulated"` programs: the body emitted by
`qdt_lab.experiment.SimulatedEmitter` (sequence JSON, symbol → parameter map, reductions). A body
with a `triggered` axis (ADR 0064) is the instrument triggering itself: at each point of that axis
every list loaded on it (`load`) sits on that point, as a marker line to a DAC would put it. A
`capture` on the instrument's own output channel (ADR 0069) is the instrument recording itself: `num`
samples of the output at the shot's levels over the window, one record per shot. Captures that follow
each other open together (ADR 0070): the clock advances once, by the longest window.

Built from a stand with `SimulatedInstrument.from_config` (the ADR 0021 `BackendFactory`): input
channels must be declared `voltage`, the output `current`, and an output channel's `integration_s` is
the time one `sense` integrates for (default `sense_integration_s`).
"""

import json
import time
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import NamedTuple, Protocol, Self

import numpy as np

from qdt_schemas.activity import SequencerProgram
from qdt_schemas.data import Dataset, DatasetChunk, IndexSlice
from qdt_schemas.pulse import Affine, PulseSequence, Symbol
from qdt_schemas.stand import ChannelMap, InstrumentConfig

from ..stream.frame import Frame


class SimulatedPhysics(Protocol):
    """What a `SimulatedInstrument` is connected to (ADR 0087). Levels are given for every input, by
    name; the physics keeps its own clock (s) and its own seeded randomness."""

    inputs: tuple[str, ...]  # the names a channel's role may take besides `output`
    output: str  # the role of the channel the instrument reads
    defaults: Mapping[str, float]  # each input's level before anything sets it
    clock_s: float

    def hold(self, levels: Mapping[str, float], duration_s: float) -> None:
        """Advance the clock by `duration_s` at `levels` without reading."""
        ...

    def sense(
        self, levels: Mapping[str, float], dwell_s: float, samples: int, gap_s: float = 0.0
    ) -> np.ndarray:
        """`samples` readings of the output at `levels`, each advancing the clock by `dwell_s + gap_s`
        (one addition) and taken at the clock after it."""
        ...


class LinearPhysics:
    """The simplest `SimulatedPhysics`, for testing the instrument: each reading is a fixed weighted
    sum of the input levels (an input without a weight does not reach the output), noiseless."""

    def __init__(
        self,
        weights: Mapping[str, float],
        inputs: Sequence[str] | None = None,
        output: str = "out",
        defaults: Mapping[str, float] | None = None,
    ) -> None:
        self.inputs = tuple(inputs or weights)
        self.output, self.weights = output, dict(weights)
        self.defaults = {i: 0.0 for i in self.inputs} | dict(defaults or {})
        self.clock_s = 0.0

    def hold(self, levels: Mapping[str, float], duration_s: float) -> None:
        self.clock_s += duration_s

    def sense(
        self, levels: Mapping[str, float], dwell_s: float, samples: int, gap_s: float = 0.0
    ) -> np.ndarray:
        self.clock_s += samples * (dwell_s + gap_s)
        value = sum(w * levels[i] for i, w in self.weights.items())
        return np.full(samples, value)


class CompiledInstrumentProgram(NamedTuple):
    """Handle returned by `SimulatedInstrument.compile`."""

    program: SequencerProgram
    sequence: PulseSequence
    symbols: dict[str, dict[str, str]]
    reduce: dict[str, str]
    compiled_id: str
    triggered: str | None = None  # the axis every loaded list follows (ADR 0064)


class SimulatedInstrument:
    """Vendor channels with declared roles over a `SimulatedPhysics`: the sequencer interpreter."""

    backend = "simulated"

    def __init__(
        self,
        physics: SimulatedPhysics,
        channels: Mapping[str, str] | None = None,
        *,
        shot_overhead_s: float = 10e-6,
        sense_integration_s: float = 1e-3,
        points_per_second: float | None = None,
        integration_s: Mapping[str, float] | None = None,
    ) -> None:
        self.physics = physics
        self.channels = dict(
            channels or {**{i: i for i in physics.inputs}, physics.output: physics.output}
        )
        roles = set(physics.inputs) | {physics.output}
        bad = {ch: r for ch, r in self.channels.items() if r not in roles}
        if bad:
            raise ValueError(
                f"channel roles must be one of {sorted(physics.inputs)} or {physics.output!r}: {bad}"
            )
        if physics.output not in self.channels.values():
            raise ValueError(f"the instrument needs a channel with role {physics.output!r}")
        self.shot_overhead_s, self.sense_integration_s = shot_overhead_s, sense_integration_s
        self.points_per_second = points_per_second
        self.integration_s = dict(integration_s or {})
        unknown = set(self.integration_s) - set(self.channels)
        if unknown:
            raise ValueError(f"integration times for unknown channels {sorted(unknown)}")
        self._dc: dict[str, float] = dict.fromkeys(self.channels, 0.0)
        self._lists: dict[str, tuple[float, ...]] = {}  # channel -> loaded list (ADR 0064)
        self._armed: dict[str, int] = {}  # channel -> index of the point last played
        for name in physics.inputs:  # each input sits at its default until something sets it
            first = next((ch for ch, role in self.channels.items() if role == name), None)
            if first is not None:
                self._dc[first] = physics.defaults[name]

    @classmethod
    def from_config(
        cls,
        instrument: InstrumentConfig,
        channels: tuple[ChannelMap, ...],
        connected: object,
        roles: Mapping[str, str] | None = None,
        **kwargs,
    ) -> Self:
        """`BackendFactory` (ADR 0021) once `connected` is bound: the constructor's first argument (the
        physics here; what a subclass builds its physics from). `roles` maps vendor channel → input or
        output (default: the constructor's); every declared channel must have a role, and its
        quantity must match it."""
        cls._check_backend(instrument)
        return cls(connected, roles, integration_s=cls._integration(channels), **kwargs)._declared(
            channels
        )

    @classmethod
    def _check_backend(cls, instrument: InstrumentConfig) -> None:
        if instrument.backend != cls.backend:
            raise ValueError(
                f"{cls.__name__} serves backend 'simulated', not {instrument.backend!r}"
            )

    @staticmethod
    def _integration(channels: tuple[ChannelMap, ...]) -> dict[str, float]:
        return {c.channel: c.integration_s for c in channels if c.integration_s is not None}

    def _declared(self, channels: tuple[ChannelMap, ...]) -> Self:
        """Check every declared channel against its role here: the output is a current, an input a
        voltage."""
        for c in channels:
            role = self.channels.get(c.channel)
            if role is None:
                raise ValueError(f"channel {c.channel!r} has no role on the instrument")
            want = "current" if role == self.physics.output else "voltage"
            if c.quantity != want:
                raise ValueError(f"channel {c.channel!r} ({role}) is {want}, declared {c.quantity}")
        return self

    @property
    def clock_s(self) -> float:
        """The physics' clock (s)."""
        return self.physics.clock_s

    def levels(self, pulse: Mapping[str, float] | None = None) -> dict[str, float]:
        """Every input's level: DC levels plus pulse offsets of its channels, summed in channel order;
        an input with no channel at its default."""
        out = {}
        for name in self.physics.inputs:
            chans = [ch for ch, role in self.channels.items() if role == name]
            if not chans:
                out[name] = self.physics.defaults[name]
                continue
            level = 0.0
            for ch in chans:
                level += self._dc[ch] + (pulse or {}).get(ch, 0.0)
            out[name] = level
        return out

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
        output = self.physics.output
        if self.channels[channel] != output:
            raise ValueError(
                f"channel {channel!r} is an input ({self.channels[channel]}); sense the {output}"
            )
        aperture = self.integration_s.get(channel, self.sense_integration_s)
        return float(self.physics.sense(self.levels(), aperture, 1, self.shot_overhead_s)[0])

    # --- Sequencer ------------------------------------------------------------------------------

    def compile(self, program: SequencerProgram) -> CompiledInstrumentProgram:
        if program.backend != self.backend:
            raise ValueError(
                f"{type(self).__name__} runs backend 'simulated' programs, not {program.backend!r}"
            )
        body = json.loads(program.body)
        sequence = PulseSequence.model_validate(body["sequence"])
        # a shot capture's channel is a scope's (ADR 0060) unless it is this instrument's own output,
        # which the instrument records itself (ADR 0069)
        scopes = {
            op.channel
            for op in sequence.expand()
            if op.op == "capture" and op.channel not in self.channels
        }
        unknown = set(sequence.channels()) - set(self.channels) - scopes
        if unknown:
            raise ValueError(
                f"sequence uses channels the instrument does not have: {sorted(unknown)}"
            )
        output = self.physics.output
        for op in sequence.expand():
            if (
                op.op in ("measure", "capture")
                and op.channel in self.channels
                and self.channels[op.channel] != output
            ):
                raise ValueError(f"{op.op} on {op.channel!r}, which is not the {output}")
        return CompiledInstrumentProgram(
            program,
            sequence,
            dict(body["symbols"]),
            dict(body.get("reduce", {})),
            f"{id(program):x}",
            (body.get("triggered") or {}).get("axis"),
        )

    def run(
        self, compiled: CompiledInstrumentProgram, parameters: Mapping[str, int], dataset: Dataset
    ) -> "_InstrumentRun":
        compiled.program.check_run(parameters, dataset)
        return _InstrumentRun(self, compiled, dict(parameters), dataset)

    def _check(self, channel: str) -> None:
        if channel not in self.channels:
            raise ValueError(f"unknown channel {channel!r}; have {sorted(self.channels)}")


class _InstrumentRun:
    """The `Source` a `SimulatedInstrument.run` returns: one line (first-axis slab) per frame per
    result."""

    def __init__(
        self,
        instrument: SimulatedInstrument,
        compiled: CompiledInstrumentProgram,
        parameters: dict[str, int],
        dataset: Dataset,
    ) -> None:
        self._instrument, self._compiled, self._params = instrument, compiled, parameters
        self.dataset = dataset
        program = compiled.program
        # a capture on the instrument's own output (ADR 0069) is a result with its own time axis
        self._records = {
            op.result: op
            for op in compiled.sequence.expand()
            if op.op == "capture" and op.channel in instrument.channels
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
        the triggered axis (ADR 0064) every loaded list is put on that point first: the instrument's
        own marker line."""
        instrument, ops = self._instrument, self._compiled.sequence.expand()
        physics = instrument.physics
        if self._compiled.triggered is not None:
            i = index[self._axes.index(f"n_{self._compiled.triggered}")]
            for ch in list(instrument._lists):
                instrument._play_point(ch, i)
        values = self._symbol_values(index)

        def val(x):
            if isinstance(x, Symbol):
                return values[x.name]
            if isinstance(x, Affine):
                return x.of(values[x.symbol.name])
            return x

        samples: dict[str, list] = {}  # result -> per-shot values, or per-shot records

        def capture_group(group, pulse: dict[str, float]) -> None:
            """Consecutive captures open together (ADR 0070): the instrument's own output records
            each window (ADR 0069: `num` samples, one sample interval of clock each), and the clock
            advances by whatever the longest scope window adds beyond them."""
            own_s, longest_s = 0.0, 0.0
            for c in group:
                window_s = val(c.duration) * 1e-9
                if c.channel in instrument.channels:
                    record = physics.sense(instrument.levels(pulse), window_s / c.num, c.num, 0.0)
                    samples.setdefault(c.result, []).append(record)
                    own_s += window_s
                else:
                    longest_s = max(longest_s, window_s)
            physics.hold(instrument.levels(pulse), max(0.0, longest_s - own_s))

        for _ in range(self._shots):
            pulse: dict[str, float] = {}
            shot: dict[str, float] = {}
            i = 0
            while i < len(ops):
                op = ops[i]
                if op.op == "capture":
                    j = i
                    while j < len(ops) and ops[j].op == "capture":
                        j += 1
                    capture_group(ops[i:j], pulse)
                    i = j
                    continue
                i += 1
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
                    reading = physics.sense(
                        instrument.levels(pulse), duration_ns * 1e-9, 1, instrument.shot_overhead_s
                    )
                    shot[op.result] = float(reading[0])
                    samples.setdefault(op.result, []).append(shot[op.result])
                    continue
                physics.hold(instrument.levels(pulse), duration_ns * 1e-9)
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
            if self._instrument.points_per_second:
                delay = t0 + done / self._instrument.points_per_second - time.perf_counter()
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
