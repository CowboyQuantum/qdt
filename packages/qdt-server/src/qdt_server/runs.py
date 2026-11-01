"""Run lifecycle (ADR 0034): accept a definition, compile it, execute it on a backend in the stream
server's worker thread, record it, ingest it. `Run` objects live in memory; the stand state (the held
operating point of ADR 0053, the limits and couplings of ADR 0075) is versioned in the registry through
`StandBook` (ADR 0085); records are durable and carry the operating point they ran at.
Every level set and every sweep compiled is checked against the limits in force, and refused beyond
them; a queued run is checked again when it starts, so a limit tightened meanwhile still holds.
A run may be aborted: queued, it never starts; running, it stops between frames and what it streamed
is recorded with outcome `aborted`."""

import asyncio
import logging
import threading
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qdt_lab.experiment import (
    Executor,
    LimitError,
    QuaEmitter,
    RunRecorder,
    SimulatedEmitter,
    check_limits,
    compile_sweep,
)
from qdt_lab.stream import Frame, Source, StreamServer
from qdt_registry import Registry, SyncReport
from qdt_schemas.activity import ExecutionPlan, FixedLevel, SweepDefinition
from qdt_schemas.control import ChannelLevel, Run
from qdt_schemas.data import AttrValue, Dataset
from qdt_schemas.operations import ChannelLimit, StandState
from qdt_schemas.stand import StandConfig

from .state import SERVER, StandBook, describe

BackendFactory = Callable[[dict[str, AttrValue]], Mapping[str, Any]]
"""Builds the backends for one run from the run's options (seed, noise, ...)."""

TERMINAL = frozenset({"completed", "aborted", "failed"})

log = logging.getLogger(__name__)


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



def with_operating_point(
    definition: SweepDefinition, held: Mapping[str, float]
) -> SweepDefinition:
    """`definition` with the held levels added for every channel it does not set, sweep, sense or
    capture itself (ADR 0053). A coupled companion (a virtual gate, ADR 0049) keeps its held level: it
    is the origin the companion moves from, `held + coupling × the axis value`; without it the companion
    would move from 0 V (#176)."""
    if not held:
        return definition
    touched = (
        {a.channel for a in definition.axes}
        | {s.channel for s in definition.sensed}
        | {c.channel for c in definition.captured}
        | {lv.channel for lv in definition.levels}
    )
    extra = tuple(
        FixedLevel(channel=c, value=v) for c, v in sorted(held.items()) if c not in touched
    )
    if not extra:
        return definition
    return definition.model_copy(update={"levels": (*definition.levels, *extra)})

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
        self._ended: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()
        self.book = StandBook(registry, stand)
        self._live: Mapping[str, Any] | None = None
        self._sync_lock = asyncio.Lock()
        self._syncs: set[asyncio.Task[SyncReport | None]] = set()

    # --- the registry server (ADR 0080) -----------------------------------------------------------

    async def sync(self) -> SyncReport | None:
        """Upload what the cache holds and the server lacks, if a server is configured (`QDT_REGISTRY_DSN`
        and `QDT_PAYLOAD_STORE`). None without one. A server or share that is unreachable is logged and
        leaves every row unsynced for the next attempt; this never raises and never touches a run.
        One sync at a time: two runs ending close together upload in turn, the second finding nothing."""
        if not self.registry.remote_dsn:
            return None
        async with self._sync_lock:
            try:
                return await asyncio.to_thread(self.registry.sync)
            except Exception as e:  # noqa: BLE001 — records stay in the cache; the next sync retries
                log.warning("registry sync failed; records stay in the local cache: %s", e)
                return None

    def sync_later(self) -> None:
        """Schedule `sync` without waiting for it: after a record is ingested and once at start."""
        task = asyncio.create_task(self.sync())
        self._syncs.add(task)
        task.add_done_callback(self._syncs.discard)

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
        held = self.book.held
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
                    held=held.get(channel.logical),
                    readback=readback,
                )
            )
        return out

    @property
    def state(self) -> StandState:
        """The stand state in force: the latest version (ADR 0075, 0085)."""
        return self.book.state

    def levels(self) -> list[FixedLevel]:
        """The operating point the server holds for the stand: DC levels every sweep inherits unless
        it sets, sweeps, couples, senses or captures the channel itself. Empty while a held point
        offered after a restart awaits confirmation."""
        return [FixedLevel(channel=c, value=v) for c, v in sorted(self.book.held.items())]

    def pending_levels(self) -> list[FixedLevel]:
        """The held point of the latest version, offered after a restart and not yet confirmed."""
        return list(self.book.pending)

    def _check_settable(self, levels: Sequence[FixedLevel]) -> None:
        """Raise KeyError for a channel the stand lacks, ValueError for one whose instrument is not a
        LevelSource, `LimitError` for a level beyond its limit: before anything is applied."""
        for lv in levels:
            channel = self.stand.channel(lv.channel)  # KeyError for an unknown channel
            if "level_source" not in self.stand.instrument(channel.instrument).capabilities:
                raise ValueError(
                    f"channel {lv.channel!r} is on {channel.instrument!r}, which is not a LevelSource"
                )
        beyond = self.state.violations({lv.channel: (lv.value, lv.value) for lv in levels})
        if beyond:
            raise LimitError(
                f"refused by stand state version {self.state.version}: " + "; ".join(beyond)
            )

    def _apply(self, levels: Sequence[FixedLevel]) -> None:
        backends = self.live_backends()
        for lv in levels:
            channel = self.stand.channel(lv.channel)
            backends[channel.instrument].set(channel.channel, lv.value)

    def set_levels(
        self, levels: Sequence[FixedLevel], *, by: str = SERVER, reason: str | None = None
    ) -> list[FixedLevel]:
        """Hold `levels` (merged over the current ones), apply them on the stand now and write the
        new held point as the next stand state version. Raises KeyError for a channel the stand
        lacks, ValueError for one whose instrument is not a LevelSource, and `LimitError` for a
        level beyond its limit; a refusal applies and writes nothing. Before a held point offered
        after a restart is confirmed, it is discarded: the new version holds only `levels`."""
        self._check_settable(levels)
        discarded = self.book.pending
        merged = self.book.held | {lv.channel: lv.value for lv in levels}
        self._apply(levels)
        why = reason or f"levels set: {describe(levels)}"
        if discarded:
            why += f"; the held point offered after the restart ({describe(discarded)}) was not re-applied"
        self.book.write(
            by=by,
            reason=why,
            held=[FixedLevel(channel=c, value=v) for c, v in sorted(merged.items())],
        )
        self.book.confirmed = True
        return self.levels()

    def clear_levels(self, *, by: str = SERVER, reason: str | None = None) -> list[FixedLevel]:
        """Forget the held operating point (the stand keeps whatever it is at) and write that as the
        next version; a held point offered after a restart is discarded the same way."""
        if self.state.held:
            discarded = self.book.pending
            why = reason or (
                f"the held point offered after the restart ({describe(discarded)}) was not re-applied"
                if discarded
                else f"held point released ({describe(self.state.held)})"
            )
            self.book.write(by=by, reason=why, held=())
        self.book.confirmed = True
        return []

    def confirm_levels(self) -> list[FixedLevel]:
        """Apply the held point offered after a restart and hold it (ADR 0075: only a person's
        confirmation re-applies it). The state does not change, so no version is written. Raises
        LookupError when nothing is offered; KeyError, ValueError or `LimitError` when the stand no
        longer has a channel, or the held point no longer fits it."""
        pending = self.book.pending
        if not pending:
            raise LookupError("no held point is waiting for confirmation")
        self._check_settable(pending)
        self._apply(pending)
        self.book.confirmed = True
        log.info(
            "held point of stand state v%d re-applied: %s", self.state.version, describe(pending)
        )
        return self.levels()

    def set_state(
        self,
        *,
        by: str,
        reason: str,
        limits: Sequence[ChannelLimit] | None = None,
        couplings: dict[str, dict[str, float]] | None = None,
    ) -> StandState:
        """Write the next version with new limits and/or couplings; the held point (offered or held)
        carries over and must fit the new limits. Raises KeyError for an unknown channel and
        ValueError for a limit on a channel nothing drives, a coupling off a LevelSource, or a held
        level beyond a new limit (lower or release it first)."""
        self.book.check_channels(limits or (), couplings)
        return self.book.write(by=by, reason=reason, limits=limits, couplings=couplings)

    def with_operating_point(self, definition: SweepDefinition) -> SweepDefinition:
        """`definition` with the held operating point merged in (`with_operating_point`). A coupled
        companion that nothing holds moves from the level the stand is at, its live setpoint (ADR
        0057), which the record then carries as its origin (#176, ADR 0092)."""
        origins = dict(self.book.held)
        in_levels = {lv.channel for lv in definition.levels}
        for logical in definition.coupled_channels():
            if logical in origins or logical in in_levels:
                continue
            setpoint = self.setpoint(logical)
            if setpoint is not None:
                origins[logical] = setpoint
        return with_operating_point(definition, origins)

    def setpoint(self, logical: str) -> float | None:
        """The level the stand's standing instrument last applied on `logical`, None when the channel
        is unknown or its instrument sets no levels or refuses it."""
        channel = next((c for c in self.stand.channels if c.logical == logical), None)
        if channel is None:
            return None
        backend = self.live_backends().get(channel.instrument)
        if backend is None or not hasattr(backend, "get"):
            return None
        try:
            return float(backend.get(channel.channel))
        except (KeyError, ValueError, TypeError, AttributeError):
            return None

    def compile(self, definition: SweepDefinition) -> ExecutionPlan:
        """Raises ValueError for a definition the stand cannot run, `LimitError` for one beyond the
        limits in force (ADR 0075). The held operating point is merged in first (ADR 0053), so the
        plan and the record carry it."""
        return compile_sweep(
            self.with_operating_point(definition),
            self.stand,
            {"simulated": SimulatedEmitter(), "qua": QuaEmitter()},
            stand_state=self.state,
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
        self._ended[run.run_id] = asyncio.Event()
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

    async def wait(self, run_id: str) -> Run:
        """The run once it has reached an end (completed, aborted or failed). KeyError for an
        unknown run. The run queue waits here before it starts the next entry (ADR 0086)."""
        run = self.runs[run_id]
        if run.state not in TERMINAL:
            await self._ended[run_id].wait()
        return self.runs[run_id]

    def _set(self, run_id: str, **update: Any) -> Run:
        run = self.runs[run_id].model_copy(update=update)
        self.runs[run_id] = run
        if run.state in TERMINAL and run_id in self._ended:
            self._ended[run_id].set()
        return run

    async def _execute(
        self, run_id: str, plan: ExecutionPlan, options: dict[str, AttrValue]
    ) -> None:
        async with self._lock:
            if self.runs[run_id].state == "aborted":  # aborted while queued
                return
            try:  # compiled against the state when it was queued; the state may have changed since
                check_limits(plan.definition, self.stand, self.state)
            except LimitError as e:
                self._set(run_id, state="failed", finished_at=datetime.now(UTC), error=str(e))
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
                self.sync_later()  # after the state is set: a slow server never holds a run
            except Exception as e:  # noqa: BLE001 — the run reports its failure
                self._set(run_id, state="failed", finished_at=datetime.now(UTC), error=str(e))
