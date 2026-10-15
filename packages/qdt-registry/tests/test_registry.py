"""Registry client (ADR 0024, 0026): ingest validates, queries answer the Step 3 exit question offline,
sync is idempotent and append-only, and the server answers the same query."""

import pytest

from qdt_registry import Registry


def test_full_loop_sweep_record_query_sync(tmp_path, server, device, recorded_run):
    dsn, store = server
    reg = Registry(tmp_path / "client", remote_dsn=dsn, remote_store=store)
    reg.register_device(device)
    record, path, plan, stand = recorded_run(tmp_path, campaign="c1")
    reg.ingest(record, path)

    assert record.outcome == "completed"
    by = {
        "device_id": record.device_id,
        "stand_sha256": stand.content_sha256(),
        "definition_sha256": plan.definition.content_sha256(),
    }
    assert reg.find(**by) == [record]
    assert reg.unsynced() == {
        "devices": 1,
        "objects": 3,
        "records": 1,
        "analysis_results": 0,
        "tuning_outcomes": 0,
    }

    report = reg.sync()
    assert (report.devices, report.objects, report.records) == (1, 3, 1)
    assert report.payload_bytes == record.payload.size_bytes
    assert reg.unsynced() == {
        "devices": 0,
        "objects": 0,
        "records": 0,
        "analysis_results": 0,
        "tuning_outcomes": 0,
    }
    assert reg.find(**by, remote=True) == [record]
    assert reg.find(stand_id=stand.stand_id, definition_name=plan.definition.name, remote=True) == [
        record
    ]
    assert (store / record.payload.path).read_bytes() == path.read_bytes()
    assert reg.object(record.definition_sha256, remote=True) == plan.definition

    again = reg.sync()
    assert (again.devices, again.objects, again.records, again.payload_bytes) == (0, 0, 0, 0)


def test_payload_reads_back_with_its_plan_and_stand(tmp_path, device, recorded_run):
    reg = Registry(tmp_path / "client")
    reg.register_device(device)
    record, path, plan, stand = recorded_run(tmp_path)
    reg.ingest(record, path)
    p = reg.payload(record.record_id)
    assert p.plan == plan and p.stand == stand
    assert p.arrays["I_sensor"].shape == (4, 5)


def test_two_clients_share_definitions_and_never_conflict(tmp_path, server, device, recorded_run):
    dsn, store = server
    a = Registry(tmp_path / "a", remote_dsn=dsn, remote_store=store)
    b = Registry(tmp_path / "b", remote_dsn=dsn, remote_store=store)
    ra, pa, plan, _ = recorded_run(tmp_path / "ra", seed=1)
    rb, pb, _, _ = recorded_run(tmp_path / "rb", seed=2)
    for reg, r, p in ((a, ra, pa), (b, rb, pb)):
        reg.register_device(device)
        reg.ingest(r, p)
    a.sync()
    report = b.sync()
    assert (report.devices, report.records) == (0, 1)
    assert report.objects == 1, (
        "the stand and definition are shared; only the plan (new plan_id) is new"
    )
    found = a.find(definition_sha256=plan.definition.content_sha256(), remote=True)
    assert {r.record_id for r in found} == {ra.record_id, rb.record_id}


def test_aborted_run_is_recorded_as_aborted(tmp_path, device, recorded_run):
    reg = Registry(tmp_path / "client")
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path, stop_after=2)
    assert record.outcome == "aborted"
    reg.ingest(record, path)
    assert reg.find(device_id=record.device_id)[0].outcome == "aborted"


def test_ingest_refuses_a_record_that_disagrees_with_its_payload(tmp_path, device, recorded_run):
    reg = Registry(tmp_path / "client")
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path)
    with pytest.raises(ValueError, match="definition_name"):
        reg.ingest(record.model_copy(update={"definition_name": "other"}), path)
    bad = record.model_copy(update={"payload": record.payload.model_copy(update={"size_bytes": 1})})
    with pytest.raises(ValueError, match="does not match"):
        reg.ingest(bad, path)
    assert reg.find() == [] and not (reg.store / record.payload.path).exists()


def test_ingest_needs_a_registered_device(tmp_path, device, recorded_run):
    reg = Registry(tmp_path / "client")
    record, path, _, _ = recorded_run(tmp_path)
    with pytest.raises(ValueError, match="not registered"):
        reg.ingest(record, path)


def test_rows_are_append_only(tmp_path, device, recorded_run):
    reg = Registry(tmp_path / "client")
    reg.register_device(device)
    reg.register_device(device)  # identical: a no-op
    with pytest.raises(ValueError, match="different body"):
        reg.register_device(device.model_copy(update={"kind": "single_dot"}))


def test_ingest_is_idempotent(tmp_path, device, recorded_run):
    reg = Registry(tmp_path / "client")
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path)
    reg.ingest(record, path)
    reg.ingest(record, path)
    assert len(reg.find()) == 1
    assert reg.unsynced()["records"] == 1


def test_sync_without_a_server_says_what_to_set(tmp_path):
    with pytest.raises(RuntimeError, match="QDT_REGISTRY_DSN"):
        Registry(tmp_path / "client").sync()


def test_ddl_export_matches_tables():
    from qdt_registry import render_ddl

    ddl = render_ddl("postgresql")
    assert "CREATE TABLE records" in ddl and "JSONB" in ddl and "DROP" not in ddl


def test_analysis_results_are_stored_queried_and_synced(tmp_path, server, device, recorded_run):
    from qdt_analysis.transitions import NAME, detect_transitions

    dsn, store = server
    reg = Registry(tmp_path / "client", remote_dsn=dsn, remote_store=store)
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path, n=(32, 32))
    reg.ingest(record, path)
    result = reg.add_result(*detect_transitions(record, reg.payload(record.record_id)))
    assert reg.add_result(result) == result  # idempotent, output already in the store

    assert reg.results(record_id=record.record_id) == [result]
    assert reg.results(method_name=NAME) == [result]
    assert reg.unsynced()["analysis_results"] == 1
    assert reg.sync().analysis_results == 1
    assert reg.results(record_id=record.record_id, remote=True) == [result]


def test_a_result_needs_its_record(tmp_path, device, recorded_run):
    from qdt_analysis.transitions import detect_transitions
    from qdt_schemas.payload_hdf5 import read_payload

    reg = Registry(tmp_path / "client")
    record, path, _, _ = recorded_run(tmp_path, n=(32, 32))
    result, output = detect_transitions(record, read_payload(path))
    with pytest.raises(ValueError, match="not in this registry"):
        reg.add_result(result, output)


def test_a_version_1_server_is_upgraded_by_adding_tables_only(tmp_path):
    from sqlalchemy import create_engine, select

    from qdt_registry.tables import analysis_results, metadata, registry_meta

    dsn = f"sqlite:///{(tmp_path / 'old.sqlite').as_posix()}"
    engine = create_engine(dsn)
    v1 = [t for t in metadata.sorted_tables if t is not analysis_results]
    metadata.create_all(engine, tables=v1)
    with engine.begin() as conn:
        conn.execute(registry_meta.insert().values(key="ddl_version", value="1"))
    reg = Registry(tmp_path / "client", remote_dsn=dsn, remote_store=tmp_path / "store")
    assert reg.find(remote=True) == []
    with engine.connect() as conn:
        version = conn.execute(select(registry_meta.c.value)).scalar_one()
    assert version == "3" and "analysis_results" in metadata.tables
    assert "tuning_outcomes" in metadata.tables  # DDL v3 (ADR 0050)


def test_node_outcomes_are_stored_queried_and_synced(tmp_path, server, device, recorded_run):
    """ADR 0050: a calibration node's outcome is a row that points at its record and result; a failed
    outcome may name neither; outcomes sync like results."""
    from datetime import UTC, datetime

    from qdt_schemas.modeling import AnalysisResult, Estimate, FitModel, NodeOutcome

    dsn, store = server
    reg = Registry(tmp_path / "client", remote_dsn=dsn, remote_store=store)
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path)
    reg.ingest(record, path)
    method = FitModel(name="m", version="1", parameters={})
    result = AnalysisResult(
        result_id="ab" * 16,
        record_id=record.record_id,
        dataset_id=record.plan_id,
        method=method,
        method_sha256=method.content_sha256(),
        status="ok",
        estimates=(Estimate(name="x", value=1.0, unit=""),),
        created_at=datetime(2026, 10, 15, tzinfo=UTC),
    )
    reg.add_result(result)
    accepted = NodeOutcome(
        outcome_id="cd" * 16,
        node_id="charge-lattice",
        tuneup_id="ef" * 16,
        record_id=record.record_id,
        result_id=result.result_id,
        status="accepted",
        outputs={"m_11": 1.0},
        created_at=datetime(2026, 10, 15, 1, tzinfo=UTC),
    )
    failed = NodeOutcome(
        outcome_id="01" * 16,
        node_id="virtual-lattice",
        tuneup_id="ef" * 16,
        status="failed",
        message="binding inputs",
        created_at=datetime(2026, 10, 15, 2, tzinfo=UTC),
    )
    assert reg.add_outcome(accepted) == accepted
    reg.add_outcome(accepted)  # idempotent
    reg.add_outcome(failed)
    assert reg.outcomes(tuneup_id="ef" * 16) == [accepted, failed]
    assert reg.outcomes(node_id="charge-lattice") == [accepted]
    assert reg.outcomes(status="failed") == [failed]
    assert reg.outcome("cd" * 16) == accepted
    with pytest.raises(KeyError):
        reg.outcome("00" * 16)
    with pytest.raises(ValueError, match="different body"):
        reg.add_outcome(accepted.model_copy(update={"message": "other"}))
    with pytest.raises(ValueError, match="not in this registry"):
        reg.add_outcome(
            accepted.model_copy(update={"outcome_id": "02" * 16, "record_id": "03" * 16})
        )
    assert reg.unsynced()["tuning_outcomes"] == 2
    report = reg.sync()
    assert report.tuning_outcomes == 2 and reg.unsynced()["tuning_outcomes"] == 0
    assert reg.outcomes(tuneup_id="ef" * 16, remote=True) == [accepted, failed]
    assert reg.sync().tuning_outcomes == 0
