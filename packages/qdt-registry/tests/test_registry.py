"""Registry client (ADR 0024, 0026): ingest validates, queries answer the Step 3 exit question offline,
sync is idempotent and append-only, and the server answers the same query."""

from datetime import UTC, datetime

import pytest

from qdt_registry import Registry
from qdt_schemas.activity import FixedLevel
from qdt_schemas.operations import ChannelLimit, StandState


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
        "stand_states": 0,
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
        "stand_states": 0,
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
    assert version == "4" and "analysis_results" in metadata.tables
    assert "tuning_outcomes" in metadata.tables  # DDL v3 (ADR 0050)
    assert "stand_states" in metadata.tables  # DDL v4 (ADR 0085)


def test_a_version_3_server_gains_stand_states_and_keeps_its_rows(tmp_path, device, recorded_run):
    """ADR 0085: v3 → v4 only adds `stand_states`; a v3 server with records keeps them and takes
    the stand's state on the next sync."""
    from sqlalchemy import create_engine, inspect, select

    from qdt_registry.tables import metadata, registry_meta, stand_states

    dsn = f"sqlite:///{(tmp_path / 'v3.sqlite').as_posix()}"
    engine = create_engine(dsn)
    metadata.create_all(engine, tables=[t for t in metadata.sorted_tables if t is not stand_states])
    with engine.begin() as conn:
        conn.execute(registry_meta.insert().values(key="ddl_version", value="3"))
    assert "stand_states" not in inspect(engine).get_table_names()
    reg = Registry(tmp_path / "client", remote_dsn=dsn, remote_store=tmp_path / "store")
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path)
    reg.ingest(record, path)
    reg.add_stand_state(stand_state(1))
    report = reg.sync()
    assert (report.records, report.stand_states) == (1, 1)
    with engine.connect() as conn:
        assert conn.execute(select(registry_meta.c.value)).scalar_one() == "4"
    assert reg.find(remote=True) == [record]
    assert reg.stand_state("sim-stand", remote=True) == stand_state(1)


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


def test_a_server_down_at_the_first_sync_is_prepared_when_it_answers(
    tmp_path, device, recorded_run
):
    """ADR 0080: the stand server retries after every record, so a connection that failed must not
    leave a half-made engine behind: the first sync that reaches the server still creates its tables."""
    server = tmp_path / "server"  # not created yet: the server is down
    reg = Registry(
        tmp_path / "client",
        remote_dsn=f"sqlite:///{(server / 'server.sqlite').as_posix()}",
        remote_store=server / "store",
    )
    reg.register_device(device)
    record, path, _, _ = recorded_run(tmp_path)
    reg.ingest(record, path)
    with pytest.raises(Exception, match="unable to open database file"):
        reg.sync()
    assert reg.unsynced()["records"] == 1

    server.mkdir()  # the server comes up
    assert reg.sync().records == 1
    assert reg.find(remote=True) == [record]


def test_a_reader_with_only_the_servers_address_reads_devices_records_and_payloads(
    tmp_path, server, device, recorded_run
):
    """ADR 0074: the read server and a script read the server side without a cache of their own;
    payload bytes come from the server's store, and a client without one says what to set."""
    dsn, store = server
    writer = Registry(tmp_path / "writer", remote_dsn=dsn, remote_store=store)
    writer.register_device(device)
    record, path, _, _ = recorded_run(tmp_path)
    writer.ingest(record, path)
    writer.sync()

    reader = Registry(tmp_path / "reader", remote_dsn=dsn, remote_store=store)
    assert reader.devices() == [] and reader.devices(remote=True) == [device]
    assert reader.find(remote=True) == [record]
    assert reader.payload_file(record.record_id, remote=True) == store / record.payload.path
    assert (
        reader.payload(record.record_id, remote=True).dataset
        == writer.payload(record.record_id).dataset
    )
    with pytest.raises(KeyError):
        reader.payload(record.record_id)  # not in the reader's own cache or store
    with pytest.raises(RuntimeError, match="QDT_PAYLOAD_STORE"):
        Registry(tmp_path / "no-store", remote_dsn=dsn).payload(record.record_id, remote=True)


def test_init_server_prepares_an_empty_server_once(tmp_path, server):
    """The runbook's schema step (ADR 0074): tables and the DDL version, then a client finds nothing."""
    dsn, store = server
    reg = Registry(tmp_path / "admin", remote_dsn=dsn, remote_store=store)
    assert reg.init_server() == reg.init_server()  # idempotent
    assert Registry(tmp_path / "reader", remote_dsn=dsn).find(remote=True) == []


def test_a_role_that_cannot_add_tables_is_told_to_run_the_schema_step(tmp_path):
    """ADR 0085: DDL 4 adds a table. The writer and the reader may not create one (ADR 0074), so a
    client meeting a version 3 server through them says to run `init` as the admin. A read-only
    SQLite file stands in for those roles (ADR 0081)."""
    from sqlalchemy import create_engine

    from qdt_registry.tables import metadata, registry_meta, stand_states

    db = tmp_path / "v3.sqlite"
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    metadata.create_all(engine, tables=[t for t in metadata.sorted_tables if t is not stand_states])
    with engine.begin() as conn:
        conn.execute(registry_meta.insert().values(key="ddl_version", value="3"))
    engine.dispose()
    reader = Registry(
        tmp_path / "reader", remote_dsn=f"sqlite:///file:{db.as_posix()}?mode=ro&uri=true"
    )
    with pytest.raises(
        RuntimeError, match=r"ddl_version 3; this client expects 4.*qdt_registry init"
    ):
        reader.find(remote=True)


def stand_state(version: int, **update) -> StandState:
    base = {
        "stand_id": "sim-stand",
        "version": version,
        "limits": (ChannelLimit(channel="P1", min_v=-0.5, max_v=0.5),),
        "held": (FixedLevel(channel="P1", value=0.01 * version),),
        "set_by": "local",
        "set_at": datetime(2026, 10, 27, 12, version, tzinfo=UTC),
        "reason": f"change {version}",
    }
    return StandState(**(base | update))


def test_stand_states_are_versioned_append_only_and_synced(tmp_path, server):
    """ADR 0075, 0085 (L0 row "StandState": versions round-trip; the latest is in force)."""
    dsn, store = server
    reg = Registry(tmp_path / "client", remote_dsn=dsn, remote_store=store)
    with pytest.raises(KeyError):
        reg.stand_state("sim-stand")
    with pytest.raises(ValueError, match="leaves a gap"):
        reg.add_stand_state(stand_state(2))  # a stand's first version is 1
    v1, v2 = stand_state(1), stand_state(2)
    assert reg.add_stand_state(v1) == v1
    reg.add_stand_state(v1)  # idempotent
    reg.add_stand_state(v2)
    with pytest.raises(ValueError, match="different body"):
        reg.add_stand_state(stand_state(2, reason="another writer"))
    with pytest.raises(ValueError, match="leaves a gap"):
        reg.add_stand_state(stand_state(4))
    reg.add_stand_state(stand_state(1, stand_id="other-stand"))
    assert reg.stand_state("sim-stand") == v2  # the latest is in force
    assert reg.stand_state("sim-stand", 1) == v1
    assert reg.stand_states("sim-stand") == [v1, v2]
    assert [s.stand_id for s in reg.stand_states()] == ["other-stand", "sim-stand", "sim-stand"]
    assert reg.unsynced()["stand_states"] == 3
    assert reg.sync().stand_states == 3 and reg.unsynced()["stand_states"] == 0
    assert reg.stand_states("sim-stand", remote=True) == [v1, v2]
    assert reg.sync().stand_states == 0


def test_a_new_cache_continues_the_stands_history_from_the_server(tmp_path, server):
    """ADR 0085: a stand server on a rebuilt computer pulls the stand's versions before writing its
    own, so its next version follows the server's latest instead of colliding with version 1."""
    dsn, store = server
    first = Registry(tmp_path / "first", remote_dsn=dsn, remote_store=store)
    first.add_stand_state(stand_state(1))
    first.add_stand_state(stand_state(2))
    first.sync()
    rebuilt = Registry(tmp_path / "rebuilt", remote_dsn=dsn, remote_store=store)
    assert rebuilt.pull_stand_states("sim-stand") == 2
    assert rebuilt.pull_stand_states("sim-stand") == 0
    assert rebuilt.unsynced()["stand_states"] == 0  # what came from the server is not sent back
    assert rebuilt.stand_state("sim-stand").version == 2
    rebuilt.add_stand_state(stand_state(3))
    assert rebuilt.sync().stand_states == 1
    assert [s.version for s in first.stand_states("sim-stand", remote=True)] == [1, 2, 3]
    clash = Registry(tmp_path / "clash", remote_dsn=dsn, remote_store=store)
    clash.add_stand_state(stand_state(1, reason="a second cache claims the stand"))
    with pytest.raises(ValueError, match="different body"):
        clash.pull_stand_states("sim-stand")


def test_the_run_queue_is_cache_local_mutable_and_never_synced(tmp_path, server):
    """ADR 0086: queue entries are operating state, rewritten as they move, kept across a restart of
    the client, and never sent to the registry server."""
    from qdt_schemas.control import RunRequest
    from qdt_schemas.operations import QueuedRun
    from qdt_sim.scenarios import stability

    dsn, store = server
    reg = Registry(tmp_path / "client", remote_dsn=dsn, remote_store=store)
    t0 = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
    waiting = QueuedRun(
        queue_id="ab" * 16,
        stand_id="sim-stand",
        position=0,
        request=RunRequest(definition=stability(4, 4)),
        submitted_by="local",
        submitted_at=t0,
        state="queued",
    )
    other = waiting.model_copy(update={"queue_id": "cd" * 16, "stand_id": "other-stand"})
    reg.queue_put(waiting, other)
    assert reg.queue_entries("sim-stand") == [waiting]
    running = waiting.model_copy(
        update={"state": "running", "position": None, "run_id": "ef" * 16, "started_at": t0}
    )
    reg.queue_put(running)  # rewritten in place
    assert Registry(tmp_path / "client").queue_entries("sim-stand") == [running]  # kept on disk
    reg.queue_drop(running.queue_id)
    assert reg.queue_entries("sim-stand") == [] and reg.queue_entries("other-stand") == [other]
    assert "run_queue" not in reg.unsynced()
    reg.sync()
    from sqlalchemy import create_engine, inspect

    assert "run_queue" not in inspect(create_engine(dsn)).get_table_names()  # never on the server
