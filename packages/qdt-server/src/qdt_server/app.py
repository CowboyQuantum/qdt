"""The API (ADR 0034): FastAPI routes over the registry, the run manager and the method catalogue.

Every body is a schema object. Errors: 404 for an unknown id, 400 for a definition the stand cannot
run or a method parameter out of range, 422 (FastAPI) for a body that is not the schema object at all.
"""

import asyncio
import dataclasses
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
from qdt_schemas.control import ChannelLevel, MethodSpec, Run, TuneUp
from qdt_schemas.data import AttrValue
from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.identity import DeviceRecord
from qdt_schemas.modeling import AnalysisResult, CalibrationNode, NodeOutcome, SimScenario
from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig
from qdt_sim.dot import DoubleDotModel
from qdt_sim.scenarios import DEVICE_ID, default_device, default_model, default_stand

from . import catalogue
from .auth import command_token, read_tokens
from .runs import BackendFactory, RunManager
from .tuning import TuneUpManager

log = logging.getLogger(__name__)

MODEL_OPTIONS = {
    f.name for f in dataclasses.fields(DoubleDotModel) if f.type in ("float", "int", float, int)
}
"""Run options that override a scalar of the default `DoubleDotModel`, e.g. `sensor_width_v` for the
cold sensor a diamond measurement wants (ADR 0030)."""


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
    """The Step 4b backend: the default simulated double dot, seeded and noisy by option, with any
    `MODEL_OPTIONS` applied to its model; and the simulated scope, recording a droop per
    `SCOPE_OPTIONS`."""
    seed = int(options.get("seed", 0))
    noise = bool(options.get("noise", True))
    overrides = {k: v for k, v in options.items() if k in MODEL_OPTIONS}
    model = dataclasses.replace(default_model(), **overrides) if overrides else None
    scope = {k: float(options.get(k, v)) for k, v in SCOPE_OPTIONS.items()}
    return {
        DEVICE_ID: default_device(seed=seed, noise=noise, model=model),
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
    device: DeviceRecord = field(
        default_factory=lambda: DeviceRecord(
            device_id=DEVICE_ID,
            kind="double_dot",
            simulated=True,
            registered_at=datetime(2026, 10, 13, tzinfo=UTC),
        )
    )
    backends: BackendFactory = simulated_backends
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


class RunRequest(BaseModel):
    """Start a run: the experiment and its options."""

    definition: SweepDefinition = Field(description="The sweep to compile and run on the stand.")
    options: dict[str, AttrValue] = Field(
        default_factory=dict,
        description=(
            "Backend and recording options: seed (int), noise (bool), campaign (str), any scalar "
            "field of the simulated model, e.g. sensor_width_v (float) for a colder sensor, and the "
            "simulated scope's tau_s, droop_v and scope_noise_v (floats)."
        ),
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
            "On the simulated stand: the scenario the backends are built from (seed, noise, model "
            "overrides become run options) and the outcomes are tagged with; ignored by a real stand."
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
            app.state.tuneups = TuneUpManager(app.state.runs)
            app.state.runs.sync_later()  # what an earlier session left in the cache (ADR 0080)
            if not read_tokens(settings.token_file):
                log.info(
                    "no command token in %s: commands from other computers are refused; "
                    "'python -m qdt_server --add-token <label>' makes one (ADR 0074)",
                    settings.token_file,
                )
            yield

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
        """Set these channels now and hold them; returns the whole operating point."""
        try:
            return runs(request).set_levels(body)
        except KeyError as e:
            raise HTTPException(400, f"no channel {e.args[0]!r} on the stand") from None
        except (ValueError, RuntimeError) as e:
            raise HTTPException(400, str(e)) from None

    @stand.delete("/levels", response_model=list[FixedLevel])
    def clear_levels(request: Request) -> list[FixedLevel]:
        """Forget the held operating point; the stand stays where it is."""
        return runs(request).clear_levels()

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
            raise HTTPException(404, f"payload of record {record_id!r} is not in this server's store")
        return FileResponse(
            path,
            media_type="application/x-hdf5",
            filename=path.name,
            headers={"X-Content-SHA256": record.payload.sha256},
        )

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
