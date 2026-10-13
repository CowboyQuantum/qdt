"""Step 4 in the registry (ADR 0030): an AnalysisResult hangs off its record, syncs, and replays as
overlays; a DDL-1 database migrates forward on open."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, insert, select

from qdt_analysis import charge_transitions
from qdt_lab.stream import PayloadSource, StreamServer, collect
from qdt_registry import Registry, migrate
from qdt_registry.migrations import stored_version
from qdt_registry.tables import (
    DDL_VERSION,
    analyses,
    devices,
    metadata,
    objects,
    records,
    registry_meta,
)
from qdt_schemas.modeling import AnalysisResult, ScenarioRef

SCENARIO = ScenarioRef(kind="simulation", name="stability", seed=0, parameters={"n_outer": 4, "n_inner": 5})
T0 = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def analysed(reg: Registry, record, **kwargs) -> AnalysisResult:
    p = reg.payload(record.record_id)
    return charge_transitions(
        p.dataset, p.arrays, SCENARIO, record_id=record.record_id, created_at=T0, **kwargs
    )


def test_analysis_is_stored_queried_and_synced(tmp_path, server, device, recorded_run):
    dsn, store = server
    reg = Registry(tmp_path / "client", remote_dsn=dsn, remote_store=store)
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path)
    reg.ingest(record, path)
    result = analysed(reg, record, analysis_id="a" * 32)
    reg.record_analysis(result)
    reg.record_analysis(result)  # identical: a no-op
    assert reg.analyses(record.record_id) == [result]
    assert reg.analysis(result.analysis_id) == result
    assert reg.unsynced()["analyses"] == 1

    report = reg.sync()
    assert report.analyses == 1
    assert reg.unsynced()["analyses"] == 0
    assert reg.analyses(record.record_id, remote=True) == [result]
    assert reg.sync().analyses == 0


def test_analyses_come_back_oldest_first(tmp_path, device, recorded_run):
    reg = Registry(tmp_path / "client")
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path)
    reg.ingest(record, path)
    later = analysed(reg, record, analysis_id="b" * 32, sigma=1.5).model_copy(
        update={"created_at": T0.replace(hour=13)}
    )
    reg.record_analysis(later)
    reg.record_analysis(analysed(reg, record, analysis_id="a" * 32))
    assert [a.analysis_id for a in reg.analyses(record.record_id)] == ["a" * 32, "b" * 32]
    assert reg.analyses("f" * 32) == []
    with pytest.raises(KeyError):
        reg.analysis("f" * 32)


def test_analysis_must_name_a_record_it_fits(tmp_path, device, recorded_run):
    reg = Registry(tmp_path / "client")
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path)
    reg.ingest(record, path)
    result = analysed(reg, record)
    with pytest.raises(ValueError, match="set record_id"):
        reg.record_analysis(
            result.model_copy(
                update={"measurement": result.measurement.model_copy(update={"record_id": None})}
            )
        )
    with pytest.raises(KeyError):
        reg.record_analysis(
            result.model_copy(
                update={"measurement": result.measurement.model_copy(update={"record_id": "e" * 32})}
            )
        )
    with pytest.raises(ValueError, match="no variable"):
        reg.record_analysis(
            result.model_copy(
                update={"measurement": result.measurement.model_copy(update={"variable": "nope"})}
            )
        )
    other = result.model_copy(update={"summary": {"n_lines": -1}})
    reg.record_analysis(result)
    with pytest.raises(ValueError, match="different body"):
        reg.record_analysis(other)


def test_annotations_must_fit_the_recorded_dataset(tmp_path, device, recorded_run):
    reg = Registry(tmp_path / "client")
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path)
    reg.ingest(record, path)
    result = analysed(reg, record)
    bad = result.annotations[0].model_copy(update={"coords": ("P1", "nope")}) if result.annotations else None
    if bad is None:
        pytest.skip("the 4x5 run produced no lines to corrupt")
    with pytest.raises(ValueError, match="unknown coordinates"):
        reg.record_analysis(result.model_copy(update={"annotations": (bad,)}))


def test_served_record_carries_its_analysis_overlays(tmp_path, device, recorded_run):
    reg = Registry(tmp_path / "client")
    reg.register_device(device)
    record, path, plan, _ = recorded_run(tmp_path, n=(12, 16))
    reg.ingest(record, path)
    result = analysed(reg, record)
    reg.record_analysis(result)
    overlays = [a for r in reg.analyses(record.record_id) for a in r.annotations]

    async def replay():
        async with StreamServer() as server:
            await server.feed(
                PayloadSource(reg.payload(record.record_id), record.record_id, annotations=overlays)
            )
            return await collect(server.url)

    received = asyncio.run(replay())[plan.dataset.dataset_id]
    assert received.dataset.source.registry_ref == record.record_id
    assert tuple(received.annotations) == tuple(overlays)


def test_ddl_1_database_migrates_forward_on_open(tmp_path):
    dsn = f"sqlite:///{(tmp_path / 'old.sqlite').as_posix()}"
    engine = create_engine(dsn)
    metadata.create_all(engine, tables=[registry_meta, devices, objects, records])  # DDL 1
    with engine.begin() as conn:
        conn.execute(insert(registry_meta).values(key="ddl_version", value="1"))
    assert stored_version(engine) == 1
    assert not engine.dialect.has_table(engine.connect(), "analyses")

    assert migrate(engine) == 1
    assert stored_version(engine) == DDL_VERSION
    assert engine.dialect.has_table(engine.connect(), "analyses")
    assert migrate(engine) == DDL_VERSION  # already current: a no-op
    with engine.connect() as conn:
        assert conn.execute(select(analyses.c.analysis_id)).all() == []


def test_newer_database_is_refused(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'new.sqlite').as_posix()}")
    migrate(engine)
    with engine.begin() as conn:
        conn.execute(
            registry_meta.update()
            .where(registry_meta.c.key == "ddl_version")
            .values(value=str(DDL_VERSION + 1))
        )
    with pytest.raises(RuntimeError, match="upgrade qdt-registry"):
        migrate(engine)
