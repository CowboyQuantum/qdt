"""Run lifecycle (ADR 0034): accept a definition, compile it, execute it on a backend in the stream
server's worker thread, record it, ingest it. `Run` objects and the held operating point (ADR 0053) are
the only state; records are durable and carry the operating point they ran at.
A run may be aborted: queued, it never starts; running, it stops between frames and what it streamed
is recorded with outcome `aborted`."""

import asyncio
import threading
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qdt_lab.experiment import Executor, QuaEmitter, RunRecorder, SimulatedEmitter, compile_sweep
from qdt_lab.stream import Frame, Source, StreamServer
from qdt_registry import Registry
from qdt_schemas.activity import ExecutionPlan, FixedLevel, SweepDefinition
from qdt_schemas.control import ChannelLevel, Run
from qdt_schemas.data import AttrValue, Dataset
from qdt_schemas.stand import StandConfig

BackendFactory = Callable[[dict[str, AttrValue]], Mapping[str, Any]]
"""Builds the backends for one run from the run's options (seed, noise, ...)."""

TERMINAL = frozenset({"completed", "aborted", "failed"})


class _Stoppable:
    """`source`, ending after the frame in flight once `stop` is set; counts the frames that passed."""

    def __init__(self, source: Source, stop: threading.Event) -> None:
        self.dataset: Dataset = source.dataset
        self._source, self._stop = source, stop
        self.passed = 0

    def frames(self) -> Iterator[Frame]:
        frames = self._source.frames()
        try:
            for frame in frames:
                yield frame
                self.passed += 1
                if self._stop.is_set():
                    return
        finally:
            close = getattr(frames, "close", None)
            if close is not None:
                close()  # stop the executor's generator now, not at garbage collection


class RunManager:
    """Compiles and executes sweeps against `backends(options)`, streaming to `stream` and recording
    into `registry`. One run at a time per manager (the stream server holds one live history)."""

    def __init__(
        self,
        stand: StandConfig,
        device_id: str,
        backends: BackendFactory,
        registry: Registry,
        stream: StreamServer,
        outbox: Path,
    ) -> None:
        self.stand, self.device_id, self._backends = stand, device_id, backends
        self.registry, self.stream, self.outbox = registry, stream, outbox
        self.runs: dict[str, Run] = {}
        self._stops: dict[str, threading.Event] = {}
        self._lock = asyncio.Lock()
        self._levels: dict[str, float] = {}
        self._live: Mapping[str, Any] | None = None

    # --- the stand's operating point (ADR 0053, 0057) ---------------------------------------------

    def live_backends(self) -> Mapping[str, Any]:
        """The instruments as the stand's standing state: built once and kept, so a level set now is
        the level read back later. On hardware these are the same objects every run uses; on the
        simulator a run builds its own seeded device, and this set is the one the operating point and
        the readbacks live on (ADR 0057)."""
        if self._live is None:
            self._live = self._backends({})
        return self._live

    def level_state(self) -> list[ChannelLevel]:
        """Every channel on an instrument that sets or senses levels: its setpoint, the held level and
        its readback; None where the instrument has no such capability or refuses the channel."""
        out: list[ChannelLevel] = []
        backends = self.live_backends()
        for channel in self.stand.channels:
            caps = self.stand.instrument(channel.instrument).capabilities
            if "level_source" not in caps and "level_sense" not in caps:
                continue
            backend = backends.get(channel.instrument)
            setpoint = readback = None
            if backend is not None and "level_source" in caps:
                try:
                    setpoint = float(backend.get(channel.channel))
                except (KeyError, ValueError):
                    setpoint = None
            if backend is not None and "level_sense" in caps:
                try:
                    readback = float(backend.sense(channel.channel))
                except (KeyError, ValueError):
                    readback = None
            out.append(
                ChannelLevel(
                    channel=channel.logical,
                    instrument=channel.instrument,
                    quantity=channel.quantity,
                    setpoint=setpoint,
                    held=self._levels.get(channel.logical),
                    readback=readback,
                )
            )
        return out

    def levels(self) -> list[FixedLevel]:
        """The operating point the server holds for the stand: DC levels every sweep inherits unless
        it sets, sweeps, couples, senses or captures the channel itself."""
        return [FixedLevel(channel=c, value=v) for c, v in sorted(self._levels.items())]

    def set_levels(self, levels: Sequence[FixedLevel]) -> list[FixedLevel]:
        """Hold `levels` (merged over the current ones) and apply them on the stand now. Raises KeyError
        for a channel the stand lacks, ValueError for one whose instrument is not a LevelSource."""
        for lv in levels:
            channel = self.stand.channel(lv.channel)  # KeyError for an unknown channel
            if "level_source" not in self.stand.instrument(channel.instrument).capabilities:
                raise ValueError(
                    f"channel {lv.channel!r} is on {channel.instrument!r}, which is not a LevelSource"
                )
        backends = self.live_backends()
        for lv in levels:
            channel = self.stand.channel(lv.channel)
            backends[channel.instrument].set(channel.channel, lv.value)
            self._levels[lv.channel] = lv.value
        return self.levels()

    def clear_levels(self) -> list[FixedLevel]:
        """Forget the held operating point (the stand keeps whatever it is at)."""
        self._levels.clear()
        return []

    def with_operating_point(self, definition: SweepDefinition) -> SweepDefinition:
        """`definition` with the held levels added for every channel it does not touch itself."""
        if not self._levels:
            return definition
        touched = (
            {a.channel for a in definition.axes}
            | set(definition.coupled_channels())
            | {s.channel for s in definition.sensed}
            | {c.channel for c in definition.captured}
            | {lv.channel for lv in definition.levels}
        )
        extra = tuple(
            FixedLevel(channel=c, value=v)
            for c, v in sorted(self._levels.items())
            if c not in touched
        )
        if not extra:
            return definition
        return definition.model_copy(update={"levels": (*definition.levels, *extra)})

    def compile(self, definition: SweepDefinition) -> ExecutionPlan:
        """Raises ValueError for a definition the stand cannot run. The held operating point is merged
        in first (ADR 0053), so the plan and the record carry it."""
        return compile_sweep(
            self.with_operating_point(definition),
            self.stand,
            {"simulated": SimulatedEmitter(), "qua": QuaEmitter()},
        )

    async def start(
        self, definition: SweepDefinition, options: dict[str, AttrValue] | None = None
    ) -> Run:
        """Compile now (errors raise), then execute in the background; returns the queued run."""
        options = dict(options or {})
        definition = self.with_operating_point(definition)
        plan = self.compile(definition)
        run = Run(
            run_id=uuid.uuid4().hex,
            plan_id=plan.plan_id,
            definition_name=definition.name,
            definition_sha256=definition.content_sha256(),
            stand_id=self.stand.stand_id,
            device_id=self.device_id,
            state="queued",
            created_at=datetime.now(UTC),
            attrs=options,
        )
        self.runs[run.run_id] = run
        self._stops[run.run_id] = threading.Event()
        asyncio.create_task(self._execute(run.run_id, plan, options))
        return run

    def abort(self, run_id: str) -> Run:
        """Ask a run to stop. Queued: aborted now. Running: stops between frames, then is recorded as
        aborted. Raises KeyError for an unknown run, ValueError for one that has already finished."""
        run = self.runs[run_id]
        if run.state in TERMINAL:
            raise ValueError(f"run {run_id!r} already {run.state}")
        self._stops[run_id].set()
        if run.state == "queued":
            return self._set(run_id, state="aborted", finished_at=datetime.now(UTC))
        return run

    def _set(self, run_id: str, **update: Any) -> Run:
        run = self.runs[run_id].model_copy(update=update)
        self.runs[run_id] = run
        return run

    async def _execute(
        self, run_id: str, plan: ExecutionPlan, options: dict[str, AttrValue]
    ) -> None:
        async with self._lock:
            if self.runs[run_id].state == "aborted":  # aborted while queued
                return
            campaign = options.get("campaign")
            recorder = RunRecorder(
                plan, self.stand, self.device_id, campaign=str(campaign) if campaign else None
            )
            try:
                backends = self._backends(options)
                source = _Stoppable(
                    recorder.wrap(Executor(plan, backends).run()), self._stops[run_id]
                )
                self._set(run_id, state="running", started_at=datetime.now(UTC))
                await self.stream.feed(source)
                if source.passed == 0:  # stopped before its first frame: nothing to record
                    self._set(run_id, state="aborted", finished_at=datetime.now(UTC))
                    return
                record, path = await asyncio.to_thread(recorder.finish, self.outbox)
                await asyncio.to_thread(self.registry.ingest, record, path)
                self._set(
                    run_id,
                    state="completed" if record.outcome == "completed" else "aborted",
                    finished_at=datetime.now(UTC),
                    record_id=record.record_id,
                )
            except Exception as e:  # noqa: BLE001 — the run reports its failure
                self._set(run_id, state="failed", finished_at=datetime.now(UTC), error=str(e))
