"""Run lifecycle (ADR 0034): accept a definition, compile it, execute it on a backend in the stream
server's worker thread, record it, ingest it. `Run` objects are the only state; records are durable.
A run may be aborted: queued, it never starts; running, it stops between frames and what it streamed
is recorded with outcome `aborted`."""

import asyncio
import threading
import uuid
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qdt_lab.experiment import Executor, RunRecorder, SimulatedEmitter, compile_sweep
from qdt_lab.stream import Frame, Source, StreamServer
from qdt_registry import Registry
from qdt_schemas.activity import ExecutionPlan, SweepDefinition
from qdt_schemas.control import Run
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

    def compile(self, definition: SweepDefinition) -> ExecutionPlan:
        """Raises ValueError for a definition the stand cannot run."""
        return compile_sweep(definition, self.stand, {"simulated": SimulatedEmitter()})

    async def start(
        self, definition: SweepDefinition, options: dict[str, AttrValue] | None = None
    ) -> Run:
        """Compile now (errors raise), then execute in the background; returns the queued run."""
        options = dict(options or {})
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
