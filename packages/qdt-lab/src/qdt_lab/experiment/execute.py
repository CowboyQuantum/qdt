"""Walk an `ExecutionPlan` against backend objects and stream the Dataset (ADR 0019).

Loop order: repeats (outermost, executor) → software-stepped axes row-major (executor: set levels and
their coupled companions, settle, then the stage, the sensed levels, the captures) → the stage
(sequencer: a triggered axis, its axes and shots). Sensed levels are chunked one innermost stepped
line per frame; stage frames and capture frames are re-keyed into the full index space. A capture
arms its `WaveformSense` on a (record, time) slab per stepped point and passes every record it yields
(ADR 0047). A shot capture (ADR 0060) arms its scope for one record per shot before the stage runs,
drains it on a thread while the shots play (a real scope acquires only while its `frames()` is being
read), and re-keys each record to its shot after. A triggered axis (ADR 0064) is loaded as a list on
its `TriggeredLevelSource` before each program run and advanced by the sequencer's marker; the
executor releases the lists when the plan ends. The executor holds no data and never averages
(ADR 0018).
"""

import contextlib
import itertools
import math
import threading
import time
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime

import numpy as np

from qdt_schemas.activity import (
    CapturedWaveform,
    ExecutionPlan,
    ParameterBinding,
    SequencerProgram,
)
from qdt_schemas.data import (
    Dataset,
    DatasetChunk,
    DataVariable,
    Dimension,
    IndexSlice,
    LinearCoordinate,
)
from qdt_schemas.pulse import Capture
from qdt_schemas.stand import StandConfig

from ..protocols import (
    BackendFactory,
    LevelSense,
    LevelSource,
    Sequencer,
    TriggeredLevelSource,
    WaveformSense,
)
from ..stream.frame import Frame
from .compile import RECORD_DIM, REPEAT_DIM, SHOT_DIM

CAPTURE_ARM_GRACE_S = 0.5
"""Seconds between starting to drain a shot capture's records (which is when a real scope arms its
acquisition) and starting the sequencer that triggers it: the scope's arm must be in place before the
first marker. The bench's scope takes 0.45 s per record through `:DIGitize` (Probe 05, 2026-10-16);
the simulated scope needs nothing and pays this per program run."""


def resolve_parameters(
    program: SequencerProgram,
    bindings: tuple[ParameterBinding, ...],
    plan: ExecutionPlan,
    current: Mapping[str, float],
) -> dict[str, int]:
    """Integer parameter values for one run; `current` holds the stepped axes' present values."""
    out: dict[str, int] = {}
    for b in bindings:
        if b.source == "const":
            out[b.parameter] = b.value
            continue
        axis = plan.definition.axis(b.axis)
        scale = program.parameter(b.parameter).scale
        if b.source == "axis_num":
            out[b.parameter] = axis.num
        elif b.source == "axis_start":
            out[b.parameter] = round(axis.start / scale)
        elif b.source == "axis_step":
            out[b.parameter] = round(axis.step / scale)
        else:  # axis_value
            out[b.parameter] = round(current[b.axis] / scale)
    return out


def build_backends(
    stand: StandConfig, factories: Mapping[str, BackendFactory]
) -> dict[str, object]:
    """Instrument id → backend, each built by the factory for its `backend` key from its config and
    its channels (ADR 0021). Raises ValueError when no factory serves an instrument's backend. When a
    factory fails, the backends already built are closed first (a real instrument may allow one
    connection) and the error names the instrument."""
    out: dict[str, object] = {}
    for instrument in stand.instruments:
        factory = factories.get(instrument.backend)
        if factory is None:
            close_backends(out)
            raise ValueError(
                f"no backend factory for {instrument.backend!r} (instrument {instrument.id!r})"
            )
        try:
            out[instrument.id] = factory(instrument, stand.instrument_channels(instrument.id))
        except Exception as e:
            close_backends(out)
            raise RuntimeError(
                f"instrument {instrument.id!r} ({instrument.backend}) could not be built: {e}"
            ) from e
    return out


def close_backends(backends: Mapping[str, object]) -> None:
    """Close every backend that has a `close`, ignoring failures; the order is reverse of building."""
    for backend in reversed(list(backends.values())):
        close = getattr(backend, "close", None)
        if close is not None:
            with contextlib.suppress(Exception):  # best effort on the way out
                close()


def expected_points(plan: ExecutionPlan) -> int | None:
    """Points (repeats × every axis × shots) a bounded plan produces per variable family; None if unbounded."""
    d = plan.definition
    if d.repeats is None:
        return None
    n = d.repeats * math.prod(a.num for a in d.axes)
    return n * (d.stage.shots if d.stage else 1)


class Executor:
    """Binds a plan to backends (instrument id → object satisfying the role's protocol) and runs it."""

    def __init__(
        self, plan: ExecutionPlan, backends: Mapping[str, object], sleep=time.sleep
    ) -> None:
        self.plan, self._backends, self._sleep = plan, dict(backends), sleep
        needs = {
            "level_source": LevelSource,
            "level_sense": LevelSense,
            "sequencer": Sequencer,
            "waveform_sense": WaveformSense,
            "triggered_level_source": TriggeredLevelSource,
        }
        for c in plan.channels:
            if c.instrument not in self._backends:
                raise ValueError(f"no backend for instrument {c.instrument!r}")
            if not isinstance(self._backends[c.instrument], needs[c.role]):
                raise TypeError(
                    f"backend {c.instrument!r} does not satisfy {needs[c.role].__name__}"
                )
        stage = plan.definition.stage
        if stage is not None:
            if not isinstance(self._backends.get(stage.instrument), Sequencer):
                raise TypeError(f"backend {stage.instrument!r} does not satisfy Sequencer")
            # a stage whose program fills nothing (a stimulus with a shot capture) runs over the plan's
            # own Dataset: the sequencer checks every result it has, which is none
            self._slab = stage_slab(plan) if plan.stage_program.results else plan.dataset
            self._compiled = self._backends[stage.instrument].compile(plan.stage_program)

    def run(self) -> "_PlanSource":
        return _PlanSource(self)

    def _frames(self) -> Iterator[Frame]:
        plan, definition = self.plan, self.plan.definition
        triggered = plan.triggered_axis()  # how each axis advances is the plan's (ADR 0066)
        stepped = plan.software_axes()
        innermost = stepped[-1].name if stepped else None
        has_repeat = definition.repeats != 1
        repeats = itertools.count() if definition.repeats is None else range(definition.repeats)
        var_dims = {v.name: v.dims for v in plan.dataset.data_vars}
        current: dict[str, float] = {}
        applied: dict[str, float] = {}
        seq = 0
        # the operating point (ADR 0038): set once, settled once, held for the whole scan
        settle = 0.0
        held = {lv.channel: lv.value for lv in definition.levels}
        for lv in definition.levels:
            ch = plan.channel(lv.channel)
            self._backends[ch.instrument].set(ch.channel, lv.value)
            applied[lv.channel] = lv.value
            settle = max(settle, ch.settle_s)
        if settle > 0:
            self._sleep(settle)

        def set_level(logical: str, value: float) -> float:
            """Set `logical` to `value` if it is not there already; the channel's settle time if set."""
            ch = plan.channel(logical)
            if applied.get(logical) == value:
                return 0.0
            self._backends[ch.instrument].set(ch.channel, value)
            applied[logical] = value
            return ch.settle_s

        loaded: list[tuple[object, str]] = []  # (backend, vendor channel) with a list armed

        def load_lists() -> None:
            """ADR 0064: the triggered axis and its companions as lists, armed for the sequencer's
            marker; loaded again before every program run so each run starts at the first point."""
            values = [triggered.value(i) for i in range(triggered.num)]
            for logical, per_volt in ((triggered.channel, None), *triggered.couplings.items()):
                ch = plan.channel(logical)
                backend = self._backends[ch.instrument]
                points = (
                    values
                    if per_volt is None
                    else [held.get(logical, 0.0) + per_volt * v for v in values]
                )
                backend.load(ch.channel, points)
                if (backend, ch.channel) not in loaded:
                    loaded.append((backend, ch.channel))
                applied.pop(logical, None)  # a later `set` on it must be sent again

        try:
            for k in repeats:
                buffers: dict[str, list[float]] = {s.name: [] for s in definition.sensed}
                for idx in itertools.product(*(range(a.num) for a in stepped)):
                    settle = 0.0
                    for a, i in zip(stepped, idx, strict=True):
                        current[a.name] = a.value(i)
                        settle = max(settle, set_level(a.channel, current[a.name]))
                        # a virtual gate (ADR 0049): companions move from their held level, or 0
                        for companion, per_volt in a.couplings.items():
                            settle = max(
                                settle,
                                set_level(
                                    companion, held.get(companion, 0.0) + per_volt * current[a.name]
                                ),
                            )
                    if settle > 0:
                        self._sleep(settle)
                    prefix = (
                        *((IndexSlice(dim=REPEAT_DIM, start=k, stop=k + 1),) if has_repeat else ()),
                        *(
                            IndexSlice(dim=a.name, start=i, stop=i + 1)
                            for a, i in zip(stepped, idx, strict=True)
                        ),
                    )
                    if definition.stage is not None:
                        if triggered is not None:
                            load_lists()
                        params = resolve_parameters(
                            plan.stage_program, plan.stage_parameters, plan, current
                        )
                        sequencer = self._backends[definition.stage.instrument]
                        # ADR 0060: every shot capture's scope is armed before the shots run, one
                        # record per shot (per point of a triggered axis), drained on a thread while
                        # they play; its frames are re-keyed record → (point,) shot after
                        drains = []
                        for c in definition.stage.captures():
                            ch = plan.channel(c.channel)
                            slab = shot_capture_slab(plan, c)
                            source = self._backends[ch.instrument].arm(ch.channel, slab, c.result)
                            drains.append((c, _Drain(source)))
                        if drains:
                            self._sleep(CAPTURE_ARM_GRACE_S)
                        for f in sequencer.run(self._compiled, params, self._slab).frames():
                            yield Frame(
                                DatasetChunk(
                                    dataset_id=plan.dataset.dataset_id,
                                    seq=seq,
                                    region=(*prefix, *f.chunk.region),
                                    variables=f.chunk.variables,
                                    explicit_coords=f.chunk.explicit_coords,
                                    produced_at=f.chunk.produced_at,
                                ),
                                {
                                    name: a.reshape((1,) * len(prefix) + a.shape)
                                    for name, a in f.arrays.items()
                                },
                            )
                            seq += 1
                        shots = definition.stage.shots
                        keep_shot = shots > 1
                        for c, drain in drains:
                            for f in drain.frames():
                                record = next(s for s in f.chunk.region if s.dim == RECORD_DIM)
                                time_slice = next(s for s in f.chunk.region if s.dim != RECORD_DIM)
                                point = (
                                    (
                                        IndexSlice(
                                            dim=triggered.name,
                                            start=record.start // shots,
                                            stop=record.start // shots + 1,
                                        ),
                                    )
                                    if triggered is not None
                                    else ()
                                )
                                shot = (
                                    (
                                        IndexSlice(
                                            dim=SHOT_DIM,
                                            start=record.start % shots,
                                            stop=record.start % shots + 1,
                                        ),
                                    )
                                    if keep_shot
                                    else ()
                                )
                                yield Frame(
                                    DatasetChunk(
                                        dataset_id=plan.dataset.dataset_id,
                                        seq=seq,
                                        region=(*prefix, *point, *shot, time_slice),
                                        variables=f.chunk.variables,
                                        produced_at=f.chunk.produced_at,
                                    ),
                                    {
                                        name: np.asarray(a).reshape(
                                            (1,) * (len(prefix) + len(point) + len(shot))
                                            + (a.shape[-1],)
                                        )
                                        for name, a in f.arrays.items()
                                    },
                                )
                                seq += 1
                    if definition.sensed:
                        for s in definition.sensed:
                            ch = plan.channel(s.channel)
                            buffers[s.name].append(self._backends[ch.instrument].sense(ch.channel))
                        if innermost is None or idx[-1] == stepped[-1].num - 1:
                            region = prefix
                            if innermost is not None:
                                region = (
                                    *prefix[:-1],
                                    IndexSlice(dim=innermost, start=0, stop=stepped[-1].num),
                                )
                            arrays = {}
                            for s in definition.sensed:
                                shape = tuple(
                                    len(buffers[s.name]) if d == innermost else 1
                                    for d in var_dims[s.name]
                                )
                                arrays[s.name] = np.asarray(
                                    buffers[s.name], dtype=np.float64
                                ).reshape(shape)
                                buffers[s.name] = []
                            yield Frame(
                                DatasetChunk(
                                    dataset_id=plan.dataset.dataset_id,
                                    seq=seq,
                                    region=region,
                                    variables=tuple(s.name for s in definition.sensed),
                                    produced_at=datetime.now(UTC),
                                ),
                                arrays,
                            )
                            seq += 1
                    for c in definition.captured:  # ADR 0047: one slab per stepped point
                        ch = plan.channel(c.channel)
                        slab = capture_slab(plan, c)
                        keep_record = c.records > 1
                        for f in (
                            self._backends[ch.instrument].arm(ch.channel, slab, c.name).frames()
                        ):
                            record = next(s for s in f.chunk.region if s.dim == RECORD_DIM)
                            time_slice = next(s for s in f.chunk.region if s.dim != RECORD_DIM)
                            yield Frame(
                                DatasetChunk(
                                    dataset_id=plan.dataset.dataset_id,
                                    seq=seq,
                                    region=(
                                        *prefix,
                                        *((record,) if keep_record else ()),
                                        time_slice,
                                    ),
                                    variables=f.chunk.variables,
                                    produced_at=f.chunk.produced_at,
                                ),
                                {
                                    name: np.asarray(a).reshape(
                                        (1,) * len(prefix)
                                        + ((a.shape[0],) if keep_record else ())
                                        + (a.shape[1],)
                                    )
                                    for name, a in f.arrays.items()
                                },
                            )
                            seq += 1
        finally:
            for backend, channel in loaded:  # the last point holds (ADR 0038); `set` applies again
                with contextlib.suppress(Exception):
                    backend.release(channel)


class _Drain:
    """Reads a `Source`'s frames on a thread from the moment it is made, so a `WaveformSense` whose
    acquisition starts when its frames are read (a scope's `:DIGitize`) is acquiring while the
    sequencer plays the shots; `frames()` joins and yields what was read, or re-raises."""

    def __init__(self, source) -> None:
        self._frames: list[Frame] = []
        self._error: BaseException | None = None

        def run() -> None:
            try:
                self._frames.extend(source.frames())
            except Exception as e:  # noqa: BLE001 - carried to the executor's thread and re-raised
                self._error = e

        self._thread = threading.Thread(target=run, name="qdt-capture-drain", daemon=True)
        self._thread.start()

    def frames(self) -> Iterator[Frame]:
        self._thread.join()
        if self._error is not None:
            raise self._error
        yield from self._frames


def stage_slab(plan: ExecutionPlan) -> Dataset:
    """The inner Dataset the sequencer fills per stepped point: stage axes (+ shot), stage results."""
    inner = {a.name for a in plan.program_axes()} | {SHOT_DIM}
    dims = tuple(d for d in plan.dataset.dims if d.name in inner)
    if not dims:
        raise ValueError("a stage needs at least one inner axis or kept shots")
    results = {r.name for r in plan.stage_program.results}
    return Dataset(
        dataset_id=f"{plan.dataset.dataset_id}:stage",
        name=f"{plan.dataset.name} (stage)",
        dims=dims,
        coords=tuple(
            c for c in plan.dataset.coords if isinstance(c, LinearCoordinate) and c.dim in inner
        ),
        data_vars=tuple(
            DataVariable(
                name=v.name,
                dims=tuple(d for d in v.dims if d in inner),
                unit=v.unit,
                dtype=v.dtype,
            )
            for v in plan.dataset.data_vars
            if v.name in results
        ),
        source=plan.dataset.source,
        created_at=plan.dataset.created_at,
    )


def shot_capture_slab(plan: ExecutionPlan, capture: Capture) -> Dataset:
    """The (record, time) Dataset a `WaveformSense` fills for a shot capture at one stepped point: one
    record per shot on the capture's time axis from 0 (ADR 0060), times the points of a triggered axis
    (ADR 0064). The executor re-keys record → (point,) shot."""
    shots = plan.definition.stage.shots
    triggered = plan.triggered_axis()
    if triggered is not None:
        shots *= triggered.num
    tdim = plan.definition.capture_time_dim(capture.result)
    var = next(v for v in plan.dataset.data_vars if v.name == capture.result)
    coord = next(c for c in plan.dataset.coords if c.dim == tdim)
    return Dataset(
        dataset_id=f"{plan.dataset.dataset_id}:{capture.result}",
        name=f"{plan.dataset.name} ({capture.result})",
        dims=(Dimension(name=RECORD_DIM, size=shots), Dimension(name=tdim, size=capture.num)),
        coords=(coord,),
        data_vars=(
            DataVariable(
                name=capture.result, dims=(RECORD_DIM, tdim), unit=var.unit, dtype=var.dtype
            ),
        ),
        source=plan.dataset.source,
        created_at=plan.dataset.created_at,
    )


def capture_slab(plan: ExecutionPlan, capture: CapturedWaveform) -> Dataset:
    """The (record, time) Dataset a `WaveformSense` fills for `capture` at one stepped point: the
    capture's records and its time coordinate, one variable (ADR 0047)."""
    tdim = plan.definition.capture_time_dim(capture.name)
    var = next(v for v in plan.dataset.data_vars if v.name == capture.name)
    coord = next(c for c in plan.dataset.coords if c.dim == tdim)
    return Dataset(
        dataset_id=f"{plan.dataset.dataset_id}:{capture.name}",
        name=f"{plan.dataset.name} ({capture.name})",
        dims=(
            Dimension(name=RECORD_DIM, size=capture.records),
            Dimension(name=tdim, size=capture.num),
        ),
        coords=(coord,),
        data_vars=(
            DataVariable(
                name=capture.name, dims=(RECORD_DIM, tdim), unit=var.unit, dtype=var.dtype
            ),
        ),
        source=plan.dataset.source,
        created_at=plan.dataset.created_at,
    )


class _PlanSource:
    """The `Source` an `Executor.run` returns."""

    def __init__(self, executor: Executor) -> None:
        self._executor = executor
        self.dataset = executor.plan.dataset

    def frames(self) -> Iterator[Frame]:
        """Frames in seq order; the last one carries `final=True` when the plan is bounded."""
        pending: Frame | None = None
        for f in self._executor._frames():
            if pending is not None:
                yield pending
            pending = f
        if pending is not None:
            yield Frame(pending.chunk.model_copy(update={"final": True}), pending.arrays)
