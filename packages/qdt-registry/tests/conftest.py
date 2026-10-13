"""Registry fixtures: a recorded Step 2 run, and the server backends the suite runs against.

The server is SQLite by default. Set QDT_TEST_PG_DSN (e.g. postgresql+psycopg://qdt:qdt@127.0.0.1:5432/qdt_test,
which `docker compose -f deploy/registry.compose.yml up -d` provides) to run every server test against
Postgres too; CI sets it with an ephemeral Postgres service. Each test gets a fresh schema-less database
state: tables are dropped after the test (test databases only).
"""

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine

from qdt_lab.experiment import Executor, RunRecorder, SimulatedEmitter, compile_sweep
from qdt_registry.tables import metadata
from qdt_schemas.identity import DeviceRecord
from qdt_sim.scenarios import DEVICE_ID, default_device, default_stand, stability

PG = os.environ.get("QDT_TEST_PG_DSN")
SERVERS = ["sqlite"] + (["postgresql"] if PG else [])


def device() -> DeviceRecord:
    return DeviceRecord(
        device_id=DEVICE_ID,
        kind="double_dot",
        simulated=True,
        registered_at=datetime(2026, 10, 13, tzinfo=UTC),
    )


def recorded_run(tmp_path, *, n=(4, 5), seed=0, campaign=None, stop_after=None):
    """Compile + execute + record a small stability sweep; returns (record, payload path, plan, stand)."""
    stand = default_stand()
    plan = compile_sweep(stability(*n), stand, {"simulated": SimulatedEmitter()})
    recorder = RunRecorder(plan, stand, DEVICE_ID, campaign=campaign)
    source = recorder.wrap(Executor(plan, {DEVICE_ID: default_device(seed=seed)}).run())
    for i, _ in enumerate(source.frames()):
        if stop_after is not None and i + 1 >= stop_after:
            break
    record, path = recorder.finish(tmp_path / "outbox")
    return record, path, plan, stand


@pytest.fixture(name="device")
def device_fixture() -> DeviceRecord:
    return device()


@pytest.fixture(name="recorded_run")
def recorded_run_fixture():
    return recorded_run


@pytest.fixture(params=SERVERS)
def server(request, tmp_path):
    """(dsn, payload store dir) of an empty server."""
    if request.param == "sqlite":
        yield f"sqlite:///{(tmp_path / 'server.sqlite').as_posix()}", tmp_path / "server_store"
        return
    engine = create_engine(PG)
    metadata.drop_all(engine)
    yield PG, tmp_path / "server_store"
    metadata.drop_all(engine)
    engine.dispose()
