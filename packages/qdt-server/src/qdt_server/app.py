"""The API (ADR 0034): FastAPI routes over the registry, the run manager and the method catalogue.

Every body is a schema object. Errors: 404 for an unknown id, 400 for a definition the stand cannot
run or a method parameter out of range, 422 (FastAPI) for a body that is not the schema object at all.
"""

import asyncio
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from qdt_lab.stream import PayloadSource, StreamServer
from qdt_registry import Registry
from qdt_schemas.activity import ExecutionPlan, SweepDefinition
from qdt_schemas.control import MethodSpec, Run
from qdt_schemas.data import AttrValue
from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.identity import DeviceRecord
from qdt_schemas.modeling import AnalysisResult
from qdt_schemas.stand import StandConfig
from qdt_sim.scenarios import DEVICE_ID, default_device, default_stand

from . import catalogue
from .runs import BackendFactory, RunManager


def simulated_backends(options: dict[str, AttrValue]) -> Mapping[str, Any]:
    """The Step 4b backend: the default simulated double dot, seeded and noisy by option."""
    seed = int(options.get("seed", 0))
    noise = bool(options.get("noise", True))
    return {DEVICE_ID: default_device(seed=seed, noise=noise)}


@dataclass
class Settings:
    """What a server instance is made of; tests pass a temp root and port 0."""

    root: Path
    stream_host: str = "127.0.0.1"
    stream_port: int = 8765
    stand: StandConfig = field(default_factory=default_stand)
    device: DeviceRecord = field(
        default_factory=lambda: DeviceRecord(
            device_id=DEVICE_ID,
            kind="double_dot",
            simulated=True,
            registered_at=datetime(2026, 10, 13, tzinfo=UTC),
        )
    )
    backends: BackendFactory = simulated_backends


class RunRequest(BaseModel):
    """Start a run: the experiment and its options."""

    definition: SweepDefinition = Field(description="The sweep to compile and run on the stand.")
    options: dict[str, AttrValue] = Field(
        default_factory=dict,
        description="Backend and recording options: seed (int), noise (bool), campaign (str).",
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


class StreamInfo(BaseModel):
    """Where Flight Deck connects for data."""

    url: str = Field(description="WebSocket URL of the Dataset stream.")


def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        registry = Registry.from_env(settings.root)
        registry.register_device(settings.device)
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
            yield

    app = FastAPI(title="qdt-server", version="0.1.0", lifespan=lifespan)

    def registry(request: Request) -> Registry:
        return request.app.state.registry

    def runs(request: Request) -> RunManager:
        return request.app.state.runs

    @app.get("/stand", response_model=StandConfig)
    def get_stand(request: Request) -> StandConfig:
        return runs(request).stand

    @app.get("/devices", response_model=list[DeviceRecord])
    def get_devices(request: Request) -> list[DeviceRecord]:
        return [registry(request).device(settings.device.device_id)]

    @app.get("/stream", response_model=StreamInfo)
    def get_stream(request: Request) -> StreamInfo:
        return StreamInfo(url=request.app.state.stream.url)

    @app.post("/sweeps/compile", response_model=ExecutionPlan)
    def compile_sweep_route(definition: SweepDefinition, request: Request) -> ExecutionPlan:
        try:
            return runs(request).compile(definition)
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e)) from None

    @app.post("/runs", response_model=Run, status_code=202)
    async def start_run(body: RunRequest, request: Request) -> Run:
        try:
            return await runs(request).start(body.definition, body.options)
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e)) from None

    @app.get("/runs", response_model=list[Run])
    def list_runs(request: Request) -> list[Run]:
        return list(runs(request).runs.values())

    @app.get("/runs/{run_id}", response_model=Run)
    def get_run(run_id: str, request: Request) -> Run:
        try:
            return runs(request).runs[run_id]
        except KeyError:
            raise HTTPException(404, f"no run {run_id!r}") from None

    @app.get("/records", response_model=list[MeasurementRecord])
    def find_records(
        request: Request,
        device_id: str | None = None,
        definition_name: str | None = None,
        campaign: str | None = None,
    ) -> list[MeasurementRecord]:
        return registry(request).find(
            device_id=device_id, definition_name=definition_name, campaign=campaign
        )

    @app.get("/records/{record_id}", response_model=MeasurementRecord)
    def get_record(record_id: str, request: Request) -> MeasurementRecord:
        try:
            return registry(request).get(record_id)
        except KeyError:
            raise HTTPException(404, f"no record {record_id!r}") from None

    @app.get("/methods", response_model=list[MethodSpec])
    def list_methods() -> list[MethodSpec]:
        return catalogue.specs()

    @app.post("/records/{record_id}/results", response_model=AnalysisResult, status_code=201)
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
        return registry(request).results(record_id=record_id, method_name=method)

    @app.get("/results/{result_id}", response_model=AnalysisResult)
    def get_result(result_id: str, request: Request) -> AnalysisResult:
        try:
            return registry(request).result(result_id)
        except KeyError:
            raise HTTPException(404, f"no result {result_id!r}") from None

    @app.post("/stream/replay", response_model=StreamInfo, status_code=202)
    async def replay(body: ReplayRequest, request: Request) -> StreamInfo:
        reg, stream = registry(request), request.app.state.stream
        try:
            if body.result_id:
                source = PayloadSource(
                    await asyncio.to_thread(reg.output, body.result_id), registry_ref=body.result_id
                )
            elif body.record_id:
                overlays = [
                    a
                    for r in reg.results(record_id=body.record_id, status="ok")
                    for a in r.annotations
                ]
                source = PayloadSource(
                    await asyncio.to_thread(reg.payload, body.record_id),
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

    return app
