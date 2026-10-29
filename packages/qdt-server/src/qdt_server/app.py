"""The API (ADR 0034): FastAPI routes over the registry, the run manager and the method catalogue.

Every body is a schema object. Errors: 404 for an unknown id, 400 for a definition the stand cannot
run or a method parameter out of range, 422 (FastAPI) for a body that is not the schema object at all.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from qdt_lab.simulated import SimulatedWaveformSense, exponential_decay
from qdt_lab.stream import PayloadSource, StreamServer
from qdt_registry import Registry
from qdt_schemas.activity import ExecutionPlan, FixedLevel, SweepDefinition
from qdt_schemas.control import ChannelLevel, MethodSpec, Run, RunRequest, TuneUp
from qdt_schemas.data import AttrValue
from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.identity import DeviceLayout, DeviceRecord
from qdt_schemas.modeling import AnalysisResult, CalibrationNode, NodeOutcome, SimScenario
from qdt_schemas.operations import ChannelLimit, QueuedRun, StandQueue, StandState
from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig
from qdt_sim.scenarios import (
    DEFAULT_DEVICE,
    DEVICE_ID,
    LATTICE_SPAN_V,
    MEASURE_NS,
    SENSOR_WINDOW_V,
    about,
    default_device,
    default_stand,
    layout,
    load_device,
    programmed,
    provenance,
)

from . import catalogue
from .auth import command_token, commander, read_tokens
from .run_queue import QueueError, RunQueue
from .runs import BackendFactory, RunManager
from .tuning import TuneUpManager

log = logging.getLogger(__name__)

SIMULATED_NODES: dict[str, dict[str, Any]] = {
    "sensor-operating-point": {
        "sg": about("SG", SENSOR_WINDOW_V),
        "near_v": programmed()["SG"],
        "flank_offset_v": 0.1,
    },
    "sensor-wing": {"span_v": 0.4},
    "charge-lattice": {
        "p1": about("P1", (-LATTICE_SPAN_V, LATTICE_SPAN_V)),
        "p2": (-LATTICE_SPAN_V, LATTICE_SPAN_V),
        "n": 64,
        "measure_ns": 10 * MEASURE_NS,
    },
}
"""The windows the simulated stand's tune-up nodes take, by node id (`qdt_tuning.TEMPLATES`, ADR 0088):
about the default device's programmed point and sized to it (plungers ~20 e/V, a sensor period ~1 V),
integrating 10 ms a lattice pixel, where Phantom's readout noise is ~5 pA. `virtual-lattice` takes the
charge lattice's window."""
SIMULATED_NODES["virtual-lattice"] = SIMULATED_NODES["charge-lattice"]


def simulated_device_record() -> DeviceRecord:
    """The registry's record of the simulated device, with what made it (ADR 0087): Phantom's version,
    its model versions and the device file's name and hash. A registry keeps the first record it was
    given for an id, so a later pin's provenance shows only in a fresh registry."""
    return DeviceRecord(
        device_id=DEVICE_ID,
        kind="double_dot",
        simulated=True,
        attrs=provenance(DEFAULT_DEVICE),
        registered_at=datetime(2026, 10, 13, tzinfo=UTC),
    )


SCOPE_ID = "scope"
"""The simulated stand's `WaveformSense` instrument (ADR 0047): one channel, `scope1`."""
SCOPE_OPTIONS = {"tau_s": 2e-3, "droop_v": 0.2, "scope_noise_v": 2e-3}
"""Run options for the simulated scope: what it records is a bias tee's droop (L2-3), a step of
`droop_v` at t = 0 decaying with `tau_s`, under `scope_noise_v` of noise (0 when `noise` is false)."""


def simulated_stand() -> StandConfig:
    """`qdt_sim`'s default stand plus a simulated scope: the Step 5 bench's shape in software, so a
    capture (ADR 0047) runs through the server before it runs on hardware."""
    base = default_stand()
    return base.model_copy(
        update={
            "instruments": (
                *base.instruments,
                InstrumentConfig(
                    id=SCOPE_ID, backend="simulated", capabilities=("waveform_sense",)
                ),
            ),
            "channels": (
                *base.channels,
                ChannelMap(logical="scope1", instrument=SCOPE_ID, channel="1", quantity="voltage"),
            ),
        }
    )


def simulated_backends(options: dict[str, AttrValue]) -> Mapping[str, Any]:
    """The Step 4b backend: a run on the committed device `device` (default the default device, loaded
    once; refused unless its file hashes to `device_sha256` when a scenario gives one), with noise seed
    `seed` and noise by option; and the simulated scope, recording a droop per `SCOPE_OPTIONS`."""
    seed = int(options.get("seed", 0))
    noise = bool(options.get("noise", True))
    sha256 = options.get("device_sha256")
    device = load_device(
        str(options.get("device", DEFAULT_DEVICE)), str(sha256) if sha256 else None
    )
    scope = {k: float(options.get(k, v)) for k, v in SCOPE_OPTIONS.items()}
    return {
        DEVICE_ID: default_device(seed, noise, device=device),
        SCOPE_ID: SimulatedWaveformSense(
            noise=scope["scope_noise_v"] if noise else 0.0,
            seed=seed,
            response=exponential_decay(scope["tau_s"], scope["droop_v"]),
        ),
    }


def stand_backends(stand: StandConfig) -> BackendFactory:
    """The real instruments of `stand`, built once through the drivers' factories (Step 5) and reused
    for every run; run options do not change them."""
    from qdt_lab.drivers import FACTORIES
    from qdt_lab.experiment import build_backends

    built: dict[str, Any] = {}

    def backends(options: dict[str, AttrValue]) -> Mapping[str, Any]:
        if not built:
            built.update(build_backends(stand, FACTORIES))
        return built

    return backends


@dataclass
class Settings:
    """What a server instance is made of; tests pass a temp root and port 0."""

    root: Path
    stream_host: str = "127.0.0.1"
    stream_port: int = 8765
    stand: StandConfig = field(default_factory=simulated_stand)
    device: DeviceRecord = field(default_factory=simulated_device_record)
    layout: DeviceLayout | None = field(default_factory=layout)
    """The device's gates seen from above, for the Device widget (ADR 0089): the simulated device's
    from Phantom; None for a stand whose device has none (a real stand, for now)."""
    backends: BackendFactory = simulated_backends
    nodes: Mapping[str, Mapping[str, Any]] = field(default_factory=lambda: SIMULATED_NODES)
    """Per node id, the windows the stand's tune-up nodes take (`qdt_tuning.TEMPLATES`, ADR 0088); a
    node not named keeps its constructor's defaults."""
    ui: Path | None = None
    """A built Flight Deck (`apps/flightdeck/dist`) to serve at `/`, after the API routes; None serves none."""
    read_only: bool = False
    """A read server (ADR 0074): no backends, no stand, no command route; records, results, outcomes,
    payload bytes and replay from the registry server (`QDT_REGISTRY_DSN`, `QDT_PAYLOAD_STORE`), which
    it needs. Runs on the database PC, answers when the measurement PC is off."""
    tokens: Path | None = None
    """The command token file (ADR 0074, 0082): a command from another computer must carry one of its
    tokens; None means `<root>/tokens`. Missing, every command from elsewhere is refused."""

    @property
    def token_file(self) -> Path:
        return self.tokens if self.tokens is not None else self.root / "tokens"


class QueueMove(BaseModel):
    """Move a waiting queue entry (ADR 0086)."""

    position: int = Field(
        ge=0, description="Its new place among the waiting entries; 0 runs next."
    )


class StandStateChange(BaseModel):
    """Change a stand's limits and/or couplings (ADR 0075, 0085): the next `StandState` version. The
    held point changes through /levels, where it is applied; what is not given carries over."""

    limits: list[ChannelLimit] | None = Field(
        default=None,
        description=(
            "The stand's limits after the change, every one of them (a channel left out has none); "
            "null leaves the limits as they are."
        ),
    )
    couplings: dict[str, dict[str, float]] | None = Field(
        default=None,
        description=(
            "The coupling matrix after the change (axis channel → channel → volts per volt); null "
            "leaves it as it is, {} clears it."
        ),
    )
    reason: str = Field(
        min_length=1, description="Why the stand's state changes; kept with the version."
    )


class MethodRequest(BaseModel):
    """Run a curated method on a record."""

    method: str = Field(description="MethodSpec.name from GET /methods.")
    parameters: dict[str, AttrValue] = Field(
        default_factory=dict, description="Parameter values; unset ones take the spec's defaults."
    )


class ReplayRequest(BaseModel):
    """Publish a stored payload on the stream: a record (with its overlays) or a result's output."""

    record_id: str | None = Field(
        default=None, description="Record to replay, with stored overlays."
    )
    result_id: str | None = Field(
        default=None, description="Result whose output Dataset to replay."
    )


class TuneUpRequest(BaseModel):
    """Start a tune-up (ADR 0050): which node templates (GET /nodes), in any order, on which scenario."""

    node_ids: list[str] = Field(
        min_length=1,
        description="Node ids from GET /nodes; the server orders them by their dependencies.",
    )
    options: dict[str, AttrValue] = Field(
        default_factory=dict, description="Run options for every node's sweep, as in RunRequest."
    )
    scenario: SimScenario | None = Field(
        default=None,
        description=(
            "On the simulated stand: the scenario the backends are built from (its device, noise seed "
            "and noise become run options) and the outcomes are tagged with; ignored by a real stand."
        ),
    )
    name: str | None = Field(
        default=None, description="Display name; default: the node ids joined."
    )


class StreamInfo(BaseModel):
    """Where Flight Deck connects for data."""

    url: str = Field(description="WebSocket URL of the Dataset stream.")


class ServerInfo(BaseModel):
    """What kind of server answered (ADR 0074): Flight Deck shows no command against a read server."""

    read_only: bool = Field(
        description="True for a read server: no stand, no command route; records and replay only."
    )
    stand_id: str | None = Field(description="The stand this server drives; null on a read server.")
    device_id: str | None = Field(
        description="The device the stand server's records are about; null on a read server."
    )


def _register_or_reuse(registry: Registry, device: DeviceRecord) -> None:
    """Register the server's device, or accept the one already registered under that id when it is
    the same kind of device (a restart registers at a later time; the registry treats a differing
    body as a conflict)."""
    try:
        existing = registry.device(device.device_id)
    except KeyError:
        registry.register_device(device)
        return
    if (existing.kind, existing.simulated) != (device.kind, device.simulated):
        raise ValueError(
            f"device {device.device_id!r} is registered as {existing.kind} "
            f"(simulated={existing.simulated}); this server was given {device.kind} "
            f"(simulated={device.simulated})"
        )


PULL_TIMEOUT_S = 10.0
"""How long a starting stand server waits for the registry server's stand states (ADR 0085)."""


async def _pull_stand_states(registry: Registry, stand_id: str) -> None:
    """Before the stand state is loaded: copy the registry server's versions of this stand that the
    cache lacks, so a new cache continues the stand's history (ADR 0085). The registry server being
    unreachable or slow is logged and the cache's own history is used, as for a sync (ADR 0080)."""
    if not registry.remote_dsn:
        return
    try:
        copied = await asyncio.wait_for(
            asyncio.to_thread(registry.pull_stand_states, stand_id), PULL_TIMEOUT_S
        )
        if copied:
            log.info(
                "took %d stand state version(s) of %r from the registry server", copied, stand_id
            )
    except Exception as e:  # noqa: BLE001 — the cache's history stands; a conflict shows on sync
        log.warning("stand states of %r not read from the registry server: %s", stand_id, e)


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        registry = Registry.from_env(settings.root)
        if settings.read_only:
            if not (registry.remote_dsn and registry.remote_store):
                raise RuntimeError(
                    "a read server reads the registry server: set QDT_REGISTRY_DSN (reader role) "
                    "and QDT_PAYLOAD_STORE (the payload store's path on this machine)"
                )
            async with StreamServer(settings.stream_host, settings.stream_port) as stream:
                app.state.registry = registry
                app.state.stream = stream
                yield
            return
        _register_or_reuse(registry, settings.device)
        await _pull_stand_states(registry, settings.stand.stand_id)
        async with StreamServer(settings.stream_host, settings.stream_port) as stream:
            app.state.registry = registry
            app.state.stream = stream
            app.state.runs = RunManager(
                settings.stand,
                settings.device.device_id,
                settings.backends,
                registry,
                stream,
                settings.root / "outbox",
            )
            app.state.tuneups = TuneUpManager(app.state.runs, settings.nodes)
            app.state.queue = RunQueue(app.state.runs, registry, settings.stand.stand_id)
            app.state.queue.start()
            app.state.runs.sync_later()  # what an earlier session left in the cache (ADR 0080)
            if not read_tokens(settings.token_file):
                log.info(
                    "no command token in %s: commands from other computers are refused; "
                    "'python -m qdt_server --add-token <label>' makes one (ADR 0074)",
                    settings.token_file,
                )
            try:
                yield
            finally:
                await app.state.queue.stop()

    # one schema per model (no -Input/-Output pairs): the UI's generated types mirror qdt-schemas 1:1
    app = FastAPI(
        title="qdt-server", version="0.1.0", lifespan=lifespan, separate_input_output_schemas=False
    )
    # Flight Deck is served from another origin (Vite's port, or the read server on `qdt-db`). CORS is
    # open; what guards a command is the token (ADR 0074), and this middleware sits outside the router
    # so a 401 reaches the browser with CORS headers and the preflight (OPTIONS) is never challenged.
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    def registry(request: Request) -> Registry:
        return request.app.state.registry

    def runs(request: Request) -> RunManager:
        return request.app.state.runs

    def tuneups(request: Request) -> TuneUpManager:
        return request.app.state.tuneups

    def queue(request: Request) -> RunQueue:
        return request.app.state.queue

    # A read server answers from the registry server; a stand server from its own cache (ADR 0074).
    remote = settings.read_only
    # Everything that needs a stand: the routes below on `stand` exist only on a stand server, and a
    # command among them (any method but a read) from another computer needs a token (ADR 0074).
    stand = APIRouter(dependencies=[Depends(command_token(settings.token_file))])

    @app.get("/server", response_model=ServerInfo)
    def get_server() -> ServerInfo:
        if settings.read_only:
            return ServerInfo(read_only=True, stand_id=None, device_id=None)
        return ServerInfo(
            read_only=False, stand_id=settings.stand.stand_id, device_id=settings.device.device_id
        )

    @stand.get("/stand", response_model=StandConfig)
    def get_stand(request: Request) -> StandConfig:
        return runs(request).stand

    @stand.get("/device/layout", response_model=DeviceLayout)
    def get_device_layout() -> DeviceLayout:
        """The device's gates seen from above, to scale (ADR 0089): what the Device widget draws,
        coloured by `GET /levels/state`. 404 when the stand's device has no layout."""
        if settings.layout is None:
            raise HTTPException(404, f"no layout for device {settings.device.device_id!r}")
        return settings.layout

    @app.get("/devices", response_model=list[DeviceRecord])
    def get_devices(request: Request) -> list[DeviceRecord]:
        if remote:
            return registry(request).devices(remote=True)
        return [registry(request).device(settings.device.device_id)]

    @app.get("/stream", response_model=StreamInfo)
    def get_stream(request: Request) -> StreamInfo:
        return StreamInfo(url=request.app.state.stream.url)

    # --- the stand's operating point (ADR 0053): click-to-set lands here ----------------------------

    @stand.get("/levels", response_model=list[FixedLevel])
    def get_levels(request: Request) -> list[FixedLevel]:
        """The DC levels the server holds for the stand; every sweep inherits them (ADR 0038, 0053)."""
        return runs(request).levels()

    @stand.get("/levels/state", response_model=list[ChannelLevel])
    def level_state(request: Request) -> list[ChannelLevel]:
        """Every level-setting or level-sensing channel of the stand now: its setpoint, the held level
        and its readback (ADR 0057). Read by the Levels widget; polled, never stored."""
        return runs(request).level_state()

    @stand.post("/levels", response_model=list[FixedLevel])
    def set_levels(body: list[FixedLevel], request: Request) -> list[FixedLevel]:
        """Set these channels now and hold them; returns the whole operating point. A level beyond
        its channel's limit is refused (400) and nothing is set (ADR 0075). Each change is the next
        stand state version, with who sent it."""
        try:
            return runs(request).set_levels(body, by=commander(request))
        except KeyError as e:
            raise HTTPException(400, f"no channel {e.args[0]!r} on the stand") from None
        except (ValueError, RuntimeError) as e:
            raise HTTPException(400, str(e)) from None

    @stand.delete("/levels", response_model=list[FixedLevel])
    def clear_levels(request: Request) -> list[FixedLevel]:
        """Forget the held operating point; the stand stays where it is."""
        return runs(request).clear_levels(by=commander(request))

    @stand.get("/levels/pending", response_model=list[FixedLevel])
    def pending_levels(request: Request) -> list[FixedLevel]:
        """The held point of the latest stand state, offered after a restart and not re-applied
        until a person confirms it (ADR 0075); empty when nothing waits."""
        return runs(request).pending_levels()

    @stand.post("/levels/pending/confirm", response_model=list[FixedLevel])
    def confirm_levels(request: Request) -> list[FixedLevel]:
        """Re-apply the offered held point and hold it; returns the operating point. 409 when
        nothing is offered, 400 when the stand no longer fits it."""
        try:
            return runs(request).confirm_levels()
        except LookupError as e:
            if isinstance(e, KeyError):
                raise HTTPException(400, f"no channel {e.args[0]!r} on the stand") from None
            raise HTTPException(409, str(e)) from None
        except (ValueError, RuntimeError) as e:
            raise HTTPException(400, str(e)) from None

    @stand.delete("/levels/pending", response_model=list[FixedLevel])
    def discard_levels(request: Request) -> list[FixedLevel]:
        """Do not re-apply the offered held point: the next version holds nothing and says so."""
        manager = runs(request)
        if not manager.pending_levels():
            raise HTTPException(409, "no held point is waiting for confirmation")
        return manager.clear_levels(by=commander(request))

    # --- the stand's state (ADR 0075, 0085): limits, couplings, the held point, versioned ---------

    @stand.get("/stand/state", response_model=StandState)
    def get_stand_state(request: Request) -> StandState:
        """The stand state in force: the latest version, whose limits every level and sweep meets."""
        return runs(request).state

    @stand.post("/stand/state", response_model=StandState, status_code=201)
    def change_stand_state(body: StandStateChange, request: Request) -> StandState:
        """Change the limits and/or the couplings; returns the new version. 400 for a channel the
        stand lacks or cannot drive, or a held level the new limits would put out of bounds."""
        try:
            return runs(request).set_state(
                by=commander(request),
                reason=body.reason,
                limits=body.limits,
                couplings=body.couplings,
            )
        except KeyError as e:
            raise HTTPException(400, f"no channel {e.args[0]!r} on the stand") from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @stand.post("/sweeps/compile", response_model=ExecutionPlan)
    def compile_sweep_route(definition: SweepDefinition, request: Request) -> ExecutionPlan:
        try:
            return runs(request).compile(definition)
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e)) from None

    @stand.post("/runs", response_model=Run, status_code=202)
    async def start_run(body: RunRequest, request: Request) -> Run:
        try:
            return await runs(request).start(body.definition, body.options)
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e)) from None

    @stand.get("/runs", response_model=list[Run])
    def list_runs(request: Request) -> list[Run]:
        return list(runs(request).runs.values())

    @stand.get("/runs/{run_id}", response_model=Run)
    def get_run(run_id: str, request: Request) -> Run:
        try:
            return runs(request).runs[run_id]
        except KeyError:
            raise HTTPException(404, f"no run {run_id!r}") from None

    @stand.post("/runs/{run_id}/abort", response_model=Run, status_code=202)
    def abort_run(run_id: str, request: Request) -> Run:
        """Queued: aborted at once. Running: stops between frames; poll the run for its record."""
        try:
            return runs(request).abort(run_id)
        except KeyError:
            raise HTTPException(404, f"no run {run_id!r}") from None
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    # --- the run queue (ADR 0075, 0086): ordered, persisted, one run at a time ------------------------
    # async: every queue route runs in the event loop, as the queue's worker does, so none races it

    @stand.get("/queue", response_model=StandQueue)
    async def get_queue(request: Request) -> StandQueue:
        """The running entry, the waiting ones in order, then the latest finished; and whether it is
        paused (after a restart with entries waiting, until a person resumes it)."""
        return queue(request).view()

    @stand.post("/queue", response_model=QueuedRun, status_code=201)
    async def submit(body: RunRequest, request: Request) -> QueuedRun:
        """Add a run at the end of the queue. Compiled now: a sweep the stand cannot run, or one beyond
        a limit, is refused (400) before it waits; checked again when it starts."""
        try:
            return queue(request).submit(body, by=commander(request))
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e)) from None

    def _queue_call(request: Request, call) -> StandQueue:
        try:
            return call(queue(request))
        except KeyError as e:
            raise HTTPException(404, e.args[0]) from None
        except QueueError as e:
            raise HTTPException(409, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @stand.post("/queue/pause", response_model=StandQueue)
    async def pause_queue(request: Request) -> StandQueue:
        """Start no further entry; the one running finishes."""
        return _queue_call(request, lambda q: q.pause(by=commander(request)))

    @stand.post("/queue/resume", response_model=StandQueue)
    async def resume_queue(request: Request) -> StandQueue:
        """Run the waiting entries again, in order."""
        return _queue_call(request, lambda q: q.resume())

    @stand.post("/queue/{queue_id}/move", response_model=StandQueue)
    async def move_entry(queue_id: str, body: QueueMove, request: Request) -> StandQueue:
        """Move a waiting entry; 409 for one that has started, 400 for a position out of range."""
        return _queue_call(request, lambda q: q.move(queue_id, body.position))

    @stand.delete("/queue/{queue_id}", response_model=StandQueue)
    async def remove_entry(queue_id: str, request: Request) -> StandQueue:
        """Remove a waiting entry: it never runs. 409 for one that has started."""
        return _queue_call(request, lambda q: q.remove(queue_id))

    @stand.post("/queue/{queue_id}/abort", response_model=StandQueue)
    async def abort_entry(queue_id: str, request: Request) -> StandQueue:
        """Abort the running entry: its run stops between frames and is recorded as aborted."""
        return _queue_call(request, lambda q: q.abort(queue_id))

    @app.get("/records", response_model=list[MeasurementRecord])
    def find_records(
        request: Request,
        device_id: str | None = None,
        definition_name: str | None = None,
        campaign: str | None = None,
    ) -> list[MeasurementRecord]:
        return registry(request).find(
            device_id=device_id, definition_name=definition_name, campaign=campaign, remote=remote
        )

    @app.get("/records/{record_id}", response_model=MeasurementRecord)
    def get_record(record_id: str, request: Request) -> MeasurementRecord:
        try:
            return registry(request).get(record_id, remote=remote)
        except KeyError:
            raise HTTPException(404, f"no record {record_id!r}") from None

    @app.get("/records/{record_id}/payload", response_class=FileResponse)
    def get_payload(record_id: str, request: Request) -> FileResponse:
        """The record's payload bytes (`qdt-hdf5-v1`), with its SHA-256 in `X-Content-SHA256` so a
        reader on another machine can check what it got (ADR 0074). No reader mounts the share."""
        reg = registry(request)
        try:
            record = reg.get(record_id, remote=remote)
        except KeyError:
            raise HTTPException(404, f"no record {record_id!r}") from None
        path = reg.payload_file(record_id, remote=remote)
        if not path.is_file():
            raise HTTPException(
                404, f"payload of record {record_id!r} is not in this server's store"
            )
        return FileResponse(
            path,
            media_type="application/x-hdf5",
            filename=path.name,
            headers={"X-Content-SHA256": record.payload.sha256},
        )

    @app.get("/stand-states", response_model=list[StandState])
    def list_stand_states(request: Request, stand_id: str | None = None) -> list[StandState]:
        """Every stored stand state version, by stand then version, oldest first: the audit trail.
        A read server answers from the registry server, a stand server from its own cache."""
        return registry(request).stand_states(stand_id, remote=remote)

    @app.get("/methods", response_model=list[MethodSpec])
    def list_methods() -> list[MethodSpec]:
        return catalogue.specs()

    @stand.post("/records/{record_id}/results", response_model=AnalysisResult, status_code=201)
    async def analyse(record_id: str, body: MethodRequest, request: Request) -> AnalysisResult:
        reg = registry(request)
        try:
            record = reg.get(record_id)
        except KeyError:
            raise HTTPException(404, f"no record {record_id!r}") from None
        if body.method not in catalogue.METHODS:
            raise HTTPException(404, f"no method {body.method!r}") from None
        try:
            payload = await asyncio.to_thread(reg.payload, record_id)
            result, output = await asyncio.to_thread(
                catalogue.run_method, body.method, record, payload, body.parameters
            )
            return await asyncio.to_thread(reg.add_result, result, output)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/results", response_model=list[AnalysisResult])
    def list_results(
        request: Request, record_id: str | None = None, method: str | None = None
    ) -> list[AnalysisResult]:
        return registry(request).results(record_id=record_id, method_name=method, remote=remote)

    @app.get("/results/{result_id}", response_model=AnalysisResult)
    def get_result(result_id: str, request: Request) -> AnalysisResult:
        try:
            return registry(request).result(result_id, remote=remote)
        except KeyError:
            raise HTTPException(404, f"no result {result_id!r}") from None

    @app.post("/stream/replay", response_model=StreamInfo, status_code=202)
    async def replay(body: ReplayRequest, request: Request) -> StreamInfo:
        """Put a stored record (with its overlays) or a result's output on the stream. A record whose
        Dataset is already on the stream (it was just run live) gets only its overlays published, so
        "analyse, then show me" works without a second copy of the data."""
        reg, stream = registry(request), request.app.state.stream
        try:
            if body.result_id:
                source = PayloadSource(
                    await asyncio.to_thread(reg.output, body.result_id, remote=remote),
                    registry_ref=body.result_id,
                )
            elif body.record_id:
                record = reg.get(body.record_id, remote=remote)
                overlays = [
                    a
                    for r in reg.results(record_id=body.record_id, status="ok", remote=remote)
                    for a in r.annotations
                ]
                if record.plan_id in stream.datasets:
                    for a in overlays:
                        stream.publish_annotation(a)
                    return StreamInfo(url=stream.url)
                source = PayloadSource(
                    await asyncio.to_thread(reg.payload, body.record_id, remote=remote),
                    registry_ref=body.record_id,
                    annotations=overlays,
                )
            else:
                raise HTTPException(400, "give record_id or result_id")
        except KeyError as e:
            raise HTTPException(404, str(e)) from None
        try:
            await stream.feed(source)
        except ValueError as e:  # already announced on this stream
            raise HTTPException(409, str(e)) from None
        return StreamInfo(url=stream.url)

    # --- tune-ups (Step 6, ADR 0050) -----------------------------------------------------------

    @stand.get("/nodes", response_model=list[CalibrationNode])
    def list_nodes(request: Request) -> list[CalibrationNode]:
        """The calibration nodes this server can run: every template, built for the stand's sequencer."""
        return tuneups(request).templates()

    @stand.post("/tuneups", response_model=TuneUp, status_code=202)
    async def start_tuneup(body: TuneUpRequest, request: Request) -> TuneUp:
        try:
            nodes = tuneups(request).nodes_for(body.node_ids)
            return await tuneups(request).start(
                nodes, body.options, scenario=body.scenario, name=body.name
            )
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e)) from None

    @stand.get("/tuneups", response_model=list[TuneUp])
    def list_tuneups(request: Request) -> list[TuneUp]:
        return list(tuneups(request).tuneups.values())

    @stand.get("/tuneups/{tuneup_id}", response_model=TuneUp)
    def get_tuneup(tuneup_id: str, request: Request) -> TuneUp:
        try:
            return tuneups(request).tuneups[tuneup_id]
        except KeyError:
            raise HTTPException(404, f"no tune-up {tuneup_id!r}") from None

    @stand.post("/tuneups/{tuneup_id}/stop", response_model=TuneUp)
    def stop_tuneup(tuneup_id: str, request: Request) -> TuneUp:
        try:
            return tuneups(request).stop(tuneup_id)
        except KeyError:
            raise HTTPException(404, f"no tune-up {tuneup_id!r}") from None
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @app.get("/outcomes", response_model=list[NodeOutcome])
    def list_outcomes(
        request: Request,
        tuneup_id: str | None = None,
        node_id: str | None = None,
        status: str | None = None,
    ) -> list[NodeOutcome]:
        return registry(request).outcomes(
            tuneup_id=tuneup_id, node_id=node_id, status=status, remote=remote
        )

    @app.get("/outcomes/{outcome_id}", response_model=NodeOutcome)
    def get_outcome(outcome_id: str, request: Request) -> NodeOutcome:
        try:
            return registry(request).outcome(outcome_id, remote=remote)
        except KeyError:
            raise HTTPException(404, f"no outcome {outcome_id!r}") from None

    if not settings.read_only:  # a read server has no stand: these routes do not exist on it
        app.include_router(stand)

    # last, so every API route matches first: the UI is static files on the same origin, nothing more
    if settings.ui is not None:
        app.mount("/", StaticFiles(directory=settings.ui, html=True), name="ui")

    return app
