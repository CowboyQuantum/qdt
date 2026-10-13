"""Run lifecycle (ADR 0034): accept a definition, compile it, execute it on a backend in the stream
server's worker thread, record it, ingest it. `Run` objects are the only state; records are durable."""

import asyncio
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qdt_lab.experiment import Executor, RunRecorder, SimulatedEmitter, compile_sweep
from qdt_lab.stream import StreamServer
from qdt_registry import Registry
from qdt_schemas.activity import ExecutionPlan, SweepDefinition
from qdt_schemas.control import Run
from qdt_schemas.data import AttrValue
from qdt_schemas.stand import StandConfig

BackendFactory = Callable[[dict[str, AttrValue]], Mapping[str, Any]]
"""Builds the backends for one run from the run's options (seed, noise, ...)."""


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
        asyncio.create_task(self._execute(run.run_id, plan, options))
        return run

    def _set(self, run_id: str, **update: Any) -> Run:
        run = self.runs[run_id].model_copy(update=update)
        self.runs[run_id] = run
        return run

    async def _execute(
        self, run_id: str, plan: ExecutionPlan, options: dict[str, AttrValue]
    ) -> None:
        async with self._lock:
            campaign = options.get("campaign")
            recorder = RunRecorder(
                plan, self.stand, self.device_id, campaign=str(campaign) if campaign else None
            )
            try:
                backends = self._backends(options)
                source = recorder.wrap(Executor(plan, backends).run())
                self._set(run_id, state="running", started_at=datetime.now(UTC))
                await self.stream.feed(source)
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
