"""The registry client: write to a local cache first, sync to the server when it is reachable (ADR 0024).

    reg = Registry(root)                              # cache at root/cache.sqlite, payloads at root/payloads/
    reg.register_device(device)
    reg.ingest(record, "run.h5")                      # validates payload ↔ envelope, copies it into the store
    reg.find(device_id="dev", definition_sha256=h)    # the Step 3 exit query, offline
    reg.add_result(result, output)                    # an AnalysisResult (+ its output payload, ADR 0031)
    reg.results(record_id=...); reg.output(result_id) # ... and back
    reg.add_outcome(outcome); reg.outcomes(tuneup_id=...)  # a calibration node's verdict (ADR 0050)
    reg.sync()                                        # needs remote_dsn + remote_store (or the env vars)

Every write is insert-if-absent keyed by a client-minted id or a content hash, so a sync can be retried
or run concurrently without harm. Writing a different body under an existing key is refused: rows are
append-only (ADR 0026).
"""

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, Table, and_, create_engine, event, select
from sqlalchemy.engine import Connection

from qdt_schemas import QdtModel
from qdt_schemas.envelope import MeasurementRecord, PayloadRef
from qdt_schemas.identity import DeviceRecord
from qdt_schemas.migrations import load
from qdt_schemas.modeling import AnalysisResult, NodeOutcome
from qdt_schemas.payload_hdf5 import PAYLOAD_TYPE, Payload, read_payload, write_payload

from .tables import (
    ADDITIVE_UPGRADES,
    DDL_VERSION,
    analysis_results,
    cache_metadata,
    devices,
    metadata,
    objects,
    records,
    registry_meta,
    sync_state,
    tuning_outcomes,
)

DSN_ENV = "QDT_REGISTRY_DSN"
STORE_ENV = "QDT_PAYLOAD_STORE"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _body(model: QdtModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _insert_absent(conn: Connection, table: Table, row: dict[str, Any]) -> bool:
    """Insert `row` unless its primary key exists; True if inserted. Raises ValueError when the key
    exists with a different body (append-only)."""
    key = [c.name for c in table.primary_key.columns]
    where = and_(*(table.c[k] == row[k] for k in key))
    existing = conn.execute(select(table.c.body).where(where)).scalar_one_or_none()
    if existing is not None:
        if existing != row["body"]:
            raise ValueError(f"{table.name} {[row[k] for k in key]} exists with a different body")
        return False
    if conn.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    # RETURNING, not rowcount: psycopg's rowcount for INSERT .. ON CONFLICT is not reliable
    stmt = insert(table).values(row).on_conflict_do_nothing().returning(*table.primary_key.columns)
    return conn.execute(stmt).first() is not None


def _prepare(engine: Engine) -> None:
    """Create missing tables (never alters or drops) and check the DDL version."""
    metadata.create_all(engine)
    with engine.begin() as conn:
        row = conn.execute(
            select(registry_meta.c.value).where(registry_meta.c.key == "ddl_version")
        ).scalar_one_or_none()
        if row is None:
            conn.execute(registry_meta.insert().values(key="ddl_version", value=str(DDL_VERSION)))
        elif int(row) < DDL_VERSION and all(
            v in ADDITIVE_UPGRADES for v in range(int(row), DDL_VERSION)
        ):
            # only new tables since that version: create_all above already added them
            conn.execute(
                registry_meta.update()
                .where(registry_meta.c.key == "ddl_version")
                .values(value=str(DDL_VERSION))
            )
        elif int(row) != DDL_VERSION:
            raise RuntimeError(
                f"registry at {engine.url!r} has ddl_version {row}; this client expects {DDL_VERSION}"
            )


def _sqlite_engine(path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{path.as_posix()}")

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):  # SQLite leaves foreign keys off unless asked
        dbapi_conn.execute("PRAGMA foreign_keys = ON")

    return engine


@dataclass(frozen=True)
class SyncReport:
    """What one `sync` uploaded; all zero when there was nothing new."""

    devices: int
    objects: int
    records: int
    payload_bytes: int
    analysis_results: int = 0
    tuning_outcomes: int = 0


class Registry:
    """A client: local cache + payload store under `root`, optional server (`remote_dsn`, `remote_store`)."""

    def __init__(
        self,
        root: str | Path,
        *,
        remote_dsn: str | None = None,
        remote_store: str | Path | None = None,
    ) -> None:
        self.root = Path(root)
        self.store = self.root / "payloads"
        self.store.mkdir(parents=True, exist_ok=True)
        self.remote_dsn = remote_dsn
        self.remote_store = Path(remote_store) if remote_store else None
        self._cache = _sqlite_engine(self.root / "cache.sqlite")
        _prepare(self._cache)
        cache_metadata.create_all(self._cache)
        self._remote: Engine | None = None

    @classmethod
    def from_env(cls, root: str | Path) -> "Registry":
        """Server settings from `QDT_REGISTRY_DSN` and `QDT_PAYLOAD_STORE`; both optional."""
        return cls(root, remote_dsn=os.environ.get(DSN_ENV), remote_store=os.environ.get(STORE_ENV))

    # --- writes (cache only) ---------------------------------------------------------------------

    def register_device(self, device: DeviceRecord) -> None:
        """Add `device`; a no-op if it is already registered identically."""
        with self._cache.begin() as conn:
            if _insert_absent(conn, devices, self._device_row(device)):
                self._mark(conn, "devices", device.device_id, False)

    def ingest(self, record: MeasurementRecord, payload_file: str | Path) -> None:
        """Validate `payload_file` against `record`, copy it into the store, and add the record with its
        stand, definition and plan. Raises ValueError on any disagreement; nothing is written then."""
        payload_file = Path(payload_file)
        size = payload_file.stat().st_size
        digest = file_sha256(payload_file)
        if (digest, size) != (record.payload.sha256, record.payload.size_bytes):
            raise ValueError("payload file does not match record.payload (sha256 or size)")
        p = read_payload(payload_file)
        if p.plan is None or p.stand is None:
            raise ValueError("a recorded run's payload must carry its plan and stand")
        definition = p.plan.definition
        checks = {
            "plan_id": (record.plan_id, p.plan.plan_id),
            "stand_id": (record.stand_id, p.stand.stand_id),
            "stand_sha256": (record.stand_sha256, p.stand.content_sha256()),
            "definition_name": (record.definition_name, definition.name),
            "definition_sha256": (record.definition_sha256, definition.content_sha256()),
            "source": (record.source, p.dataset.source),
        }
        wrong = {k: v for k, v in checks.items() if v[0] != v[1]}
        if wrong:
            raise ValueError(f"record disagrees with its payload: {wrong}")
        with self._cache.connect() as conn:
            if (
                conn.execute(
                    select(devices.c.device_id).where(devices.c.device_id == record.device_id)
                ).first()
                is None
            ):
                raise ValueError(f"device {record.device_id!r} is not registered")
        target = self.store / record.payload.path
        _place(payload_file, target, digest)
        with self._cache.begin() as conn:
            for obj in (p.stand, definition, p.plan):
                if _insert_absent(conn, objects, self._object_row(obj)):
                    self._mark(conn, "objects", obj.content_sha256(), False)
            row = self._record_row(record, p.plan.content_sha256())
            if _insert_absent(conn, records, row):
                self._mark(conn, "records", record.record_id, False)

    def add_result(self, result: AnalysisResult, output: Payload | None = None) -> AnalysisResult:
        """Store an analysis of a record already in this cache (append-only, idempotent) and, when the
        method produced arrays, its `output` payload (ADR 0031): written once to the store as
        `analysis/<YYYY>/<MM>/<result_id>.h5`; `result.output` is filled from it. Returns the stored
        result. A result that already names an output must find that file in the store."""
        with self._cache.connect() as conn:
            if (
                conn.execute(
                    select(records.c.record_id).where(records.c.record_id == result.record_id)
                ).first()
                is None
            ):
                raise ValueError(f"record {result.record_id!r} is not in this registry")
        if output is not None:
            if result.output is not None:
                raise ValueError("result already names an output payload; pass one or the other")
            if output.dataset.source.kind != "analysis":
                raise ValueError("an analysis output Dataset has source.kind 'analysis'")
            relative = f"analysis/{result.created_at:%Y/%m}/{result.result_id}.h5"
            target = self.store / relative
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(".tmp")
                tmp.unlink(missing_ok=True)
                write_payload(tmp, output.dataset, output.arrays, annotations=output.annotations)
                tmp.replace(target)
            result = result.model_copy(
                update={
                    "output": PayloadRef(
                        type=PAYLOAD_TYPE,
                        path=relative,
                        sha256=file_sha256(target),
                        size_bytes=target.stat().st_size,
                    )
                }
            )
        elif result.output is not None:
            target = self.store / result.output.path
            if not target.exists() or file_sha256(target) != result.output.sha256:
                raise ValueError(
                    f"output payload {result.output.path!r} is not in this client's store"
                )
        with self._cache.begin() as conn:
            row = {
                "result_id": result.result_id,
                "record_id": result.record_id,
                "method_name": result.method.name,
                "method_sha256": result.method_sha256,
                "status": result.status,
                "created_at": result.created_at,
                "schema_version": result.schema_version,
                "body": _body(result),
            }
            if _insert_absent(conn, analysis_results, row):
                self._mark(conn, "analysis_results", result.result_id, False)
        return result

    # --- reads (cache or server) -----------------------------------------------------------------

    def find(
        self,
        *,
        device_id: str | None = None,
        stand_id: str | None = None,
        stand_sha256: str | None = None,
        definition_name: str | None = None,
        definition_sha256: str | None = None,
        campaign: str | None = None,
        remote: bool = False,
    ) -> list[MeasurementRecord]:
        """Records matching every given filter, oldest first. `remote=True` asks the server."""
        filters = {
            "device_id": device_id,
            "stand_id": stand_id,
            "stand_sha256": stand_sha256,
            "definition_name": definition_name,
            "definition_sha256": definition_sha256,
            "campaign": campaign,
        }
        q = select(records.c.body).order_by(records.c.started_at, records.c.record_id)
        for k, v in filters.items():
            if v is not None:
                q = q.where(records.c[k] == v)
        with self._engine(remote).connect() as conn:
            return [load("MeasurementRecord", b) for b in conn.execute(q).scalars()]

    def get(self, record_id: str, *, remote: bool = False) -> MeasurementRecord:
        with self._engine(remote).connect() as conn:
            body = conn.execute(
                select(records.c.body).where(records.c.record_id == record_id)
            ).scalar_one_or_none()
        if body is None:
            raise KeyError(f"no record {record_id!r}")
        return load("MeasurementRecord", body)

    def object(self, sha256: str, *, remote: bool = False) -> QdtModel:
        """A stored stand, definition or plan by content hash."""
        with self._engine(remote).connect() as conn:
            row = conn.execute(
                select(objects.c.type, objects.c.body).where(objects.c.sha256 == sha256)
            ).first()
        if row is None:
            raise KeyError(f"no object {sha256}")
        return load(row.type, row.body)

    def device(self, device_id: str, *, remote: bool = False) -> DeviceRecord:
        with self._engine(remote).connect() as conn:
            body = conn.execute(
                select(devices.c.body).where(devices.c.device_id == device_id)
            ).scalar_one_or_none()
        if body is None:
            raise KeyError(f"no device {device_id!r}")
        return load("DeviceRecord", body)

    def devices(self, *, remote: bool = False) -> list[DeviceRecord]:
        """Every registered device, oldest first. `remote=True` asks the server."""
        q = select(devices.c.body).order_by(devices.c.registered_at, devices.c.device_id)
        with self._engine(remote).connect() as conn:
            return [load("DeviceRecord", b) for b in conn.execute(q).scalars()]

    def payload_file(self, record_id: str, *, remote: bool = False) -> Path:
        """Where a record's payload lies: in this client's store, or (`remote=True`) in the server's
        store, which a read server or a stand server mounts (ADR 0074)."""
        return self._store(remote) / self.get(record_id, remote=remote).payload.path

    def payload(self, record_id: str, *, remote: bool = False) -> Payload:
        """The payload of a record in this client's store (sync does not download), or the server's."""
        return read_payload(self.payload_file(record_id, remote=remote))

    def results(
        self,
        *,
        record_id: str | None = None,
        method_name: str | None = None,
        status: str | None = None,
        remote: bool = False,
    ) -> list[AnalysisResult]:
        """Analysis results matching every given filter, oldest first."""
        q = select(analysis_results.c.body).order_by(
            analysis_results.c.created_at, analysis_results.c.result_id
        )
        for col, v in (("record_id", record_id), ("method_name", method_name), ("status", status)):
            if v is not None:
                q = q.where(analysis_results.c[col] == v)
        with self._engine(remote).connect() as conn:
            return [load("AnalysisResult", b) for b in conn.execute(q).scalars()]

    def result(self, result_id: str, *, remote: bool = False) -> AnalysisResult:
        with self._engine(remote).connect() as conn:
            body = conn.execute(
                select(analysis_results.c.body).where(analysis_results.c.result_id == result_id)
            ).scalar_one_or_none()
        if body is None:
            raise KeyError(f"no analysis result {result_id!r}")
        return load("AnalysisResult", body)

    def output(self, result_id: str, *, remote: bool = False) -> Payload:
        """The output payload of a result in this client's store (ADR 0031), or the server's;
        KeyError without one."""
        ref = self.result(result_id, remote=remote).output
        if ref is None:
            raise KeyError(f"result {result_id!r} has no output payload")
        return read_payload(self._store(remote) / ref.path)

    def _store(self, remote: bool) -> Path:
        if not remote:
            return self.store
        if self.remote_store is None:
            raise RuntimeError(f"no server payload store configured: set {STORE_ENV}")
        return self.remote_store

    def add_outcome(self, outcome: NodeOutcome) -> NodeOutcome:
        """Store a calibration node's outcome (ADR 0050; append-only, idempotent). The record and the
        result it names must already be in this cache. Returns the stored outcome."""
        with self._cache.connect() as conn:
            if (
                outcome.record_id is not None
                and conn.execute(
                    select(records.c.record_id).where(records.c.record_id == outcome.record_id)
                ).first()
                is None
            ):
                raise ValueError(f"record {outcome.record_id!r} is not in this registry")
            if (
                outcome.result_id is not None
                and conn.execute(
                    select(analysis_results.c.result_id).where(
                        analysis_results.c.result_id == outcome.result_id
                    )
                ).first()
                is None
            ):
                raise ValueError(f"result {outcome.result_id!r} is not in this registry")
        with self._cache.begin() as conn:
            row = {
                "outcome_id": outcome.outcome_id,
                "tuneup_id": outcome.tuneup_id,
                "node_id": outcome.node_id,
                "record_id": outcome.record_id,
                "result_id": outcome.result_id,
                "status": outcome.status,
                "created_at": outcome.created_at,
                "schema_version": outcome.schema_version,
                "body": _body(outcome),
            }
            if _insert_absent(conn, tuning_outcomes, row):
                self._mark(conn, "tuning_outcomes", outcome.outcome_id, False)
        return outcome

    def outcomes(
        self,
        *,
        tuneup_id: str | None = None,
        node_id: str | None = None,
        status: str | None = None,
        remote: bool = False,
    ) -> list[NodeOutcome]:
        """Node outcomes matching every given filter, oldest first."""
        q = select(tuning_outcomes.c.body).order_by(
            tuning_outcomes.c.created_at, tuning_outcomes.c.outcome_id
        )
        for col, v in (("tuneup_id", tuneup_id), ("node_id", node_id), ("status", status)):
            if v is not None:
                q = q.where(tuning_outcomes.c[col] == v)
        with self._engine(remote).connect() as conn:
            return [load("NodeOutcome", b) for b in conn.execute(q).scalars()]

    def outcome(self, outcome_id: str, *, remote: bool = False) -> NodeOutcome:
        with self._engine(remote).connect() as conn:
            body = conn.execute(
                select(tuning_outcomes.c.body).where(tuning_outcomes.c.outcome_id == outcome_id)
            ).scalar_one_or_none()
        if body is None:
            raise KeyError(outcome_id)
        return load("NodeOutcome", body)

    def unsynced(self) -> dict[str, int]:
        with self._cache.connect() as conn:
            rows = conn.execute(select(sync_state.c.table_name).where(~sync_state.c.synced))
            out = {
                "devices": 0,
                "objects": 0,
                "records": 0,
                "analysis_results": 0,
                "tuning_outcomes": 0,
            }
            for (t,) in rows:
                out[t] += 1
            return out

    # --- sync ------------------------------------------------------------------------------------

    def sync(self) -> SyncReport:
        """Upload everything not yet confirmed: devices, objects, each record after its payload, then
        analysis results, each after its output payload if it has one, then node outcomes.
        Safe to repeat and to interrupt; raises RuntimeError without a server configured."""
        if not self.remote_dsn or self.remote_store is None:
            raise RuntimeError(f"sync needs a server: set {DSN_ENV} and {STORE_ENV}")
        remote = self._engine(True)
        counts = {
            "devices": 0,
            "objects": 0,
            "records": 0,
            "analysis_results": 0,
            "tuning_outcomes": 0,
        }
        sent_bytes = 0
        for name, table, key in (
            ("devices", devices, "device_id"),
            ("objects", objects, "sha256"),
            ("records", records, "record_id"),
            ("analysis_results", analysis_results, "result_id"),
            ("tuning_outcomes", tuning_outcomes, "outcome_id"),
        ):
            for row in self._pending(name, table, key):
                payload = None
                if name == "records":
                    payload = (row["payload_path"], row["payload_sha256"])
                elif name == "analysis_results" and row["body"].get("output"):
                    payload = (row["body"]["output"]["path"], row["body"]["output"]["sha256"])
                if payload is not None:
                    source = self.store / payload[0]
                    target = self.remote_store / payload[0]
                    if _place(source, target, payload[1]):
                        sent_bytes += source.stat().st_size
                with remote.begin() as conn:
                    counts[name] += _insert_absent(conn, table, row)
                with self._cache.begin() as conn:
                    self._mark(conn, name, row[key], True)
        return SyncReport(**counts, payload_bytes=sent_bytes)

    # --- internals -------------------------------------------------------------------------------

    def _engine(self, remote: bool) -> Engine:
        if not remote:
            return self._cache
        if self._remote is None:
            if not self.remote_dsn:
                raise RuntimeError(f"no server configured: set {DSN_ENV}")
            engine = create_engine(self.remote_dsn)
            _prepare(engine)  # kept only once it answered: a server down now is retried next time
            self._remote = engine
        return self._remote

    def _pending(self, name: str, table: Table, key: str) -> list[dict[str, Any]]:
        """Rows of `table` not yet confirmed by the server, read in one go (SQLite: no open reader
        while sync writes the flags)."""
        with self._cache.connect() as conn:
            pending = (
                select(table)
                .join(
                    sync_state,
                    and_(sync_state.c.key == table.c[key], sync_state.c.table_name == name),
                )
                .where(~sync_state.c.synced)
            )
            return [dict(r) for r in conn.execute(pending).mappings()]

    @staticmethod
    def _mark(conn: Connection, table_name: str, key: str, synced: bool) -> None:
        from sqlalchemy.dialects.sqlite import insert

        stmt = insert(sync_state).values(table_name=table_name, key=key, synced=synced)
        conn.execute(
            stmt.on_conflict_do_update(
                index_elements=["table_name", "key"], set_={"synced": stmt.excluded.synced}
            )
        )

    @staticmethod
    def _device_row(d: DeviceRecord) -> dict[str, Any]:
        return {
            "device_id": d.device_id,
            "kind": d.kind,
            "simulated": d.simulated,
            "registered_at": d.registered_at,
            "schema_version": d.schema_version,
            "body": _body(d),
        }

    @staticmethod
    def _object_row(obj: QdtModel) -> dict[str, Any]:
        name = getattr(obj, "stand_id", None) or getattr(obj, "plan_id", None) or obj.name
        return {
            "sha256": obj.content_sha256(),
            "type": type(obj).__name__,
            "schema_version": obj.schema_version,
            "name": name,
            "body": _body(obj),
        }

    @staticmethod
    def _record_row(r: MeasurementRecord, plan_sha256: str) -> dict[str, Any]:
        return {
            "record_id": r.record_id,
            "device_id": r.device_id,
            "stand_id": r.stand_id,
            "stand_sha256": r.stand_sha256,
            "definition_name": r.definition_name,
            "definition_sha256": r.definition_sha256,
            "plan_sha256": plan_sha256,
            "plan_id": r.plan_id,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "outcome": r.outcome,
            "campaign": r.campaign,
            "payload_path": r.payload.path,
            "payload_sha256": r.payload.sha256,
            "schema_version": r.schema_version,
            "body": _body(r),
        }


def _place(source: Path, target: Path, sha256: str) -> bool:
    """Copy `source` to `target` unless an identical file is there; True if copied. Raises ValueError
    if `target` exists with other content (payloads are immutable). Writes via a temp file + rename."""
    if target.exists():
        if file_sha256(target) != sha256:
            raise ValueError(f"{target} exists with different content")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".partial")
    shutil.copyfile(source, tmp)
    if file_sha256(tmp) != sha256:
        tmp.unlink()
        raise ValueError(f"copy of {source} does not match its sha256")
    os.replace(tmp, target)
    return True
