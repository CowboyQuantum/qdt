"""The registry's tables (ADR 0026): one SQLAlchemy Core metadata for the local cache (SQLite) and the
server (Postgres), so a row means the same thing on both sides of a sync (ADR 0024).

Every table is append-only: rows are inserted once and never updated, except the cache-local `synced`
flags, which exist only in the cache. Bodies are the schema object's canonical JSON, so a row can always
be re-validated through `qdt_schemas.migrations.load`. Columns beside the body are indexes, never a
second source of truth.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

DDL_VERSION = 4
"""Bumps with every table change; a change is an ADR plus an additive migration, never a DROP."""

ADDITIVE_UPGRADES: dict[int, str] = {
    1: "adds analysis_results (Step 4, ADR 0029)",
    2: "adds tuning_outcomes (Step 6, ADR 0050)",
    3: "adds stand_states (Step 6c, ADR 0075, 0085)",
}
"""From-version → what the next version adds, for upgrades that only create new tables. A client may
upgrade a server across these with `create_all`; any other change needs a real migration (ADR 0026)."""

Body = JSON().with_variant(JSONB(), "postgresql")
Timestamp = DateTime(timezone=True)

metadata = MetaData()

registry_meta = Table(
    "registry_meta",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("value", Text, nullable=False),
    comment="Registry-level facts, e.g. ddl_version.",
)

devices = Table(
    "devices",
    metadata,
    Column("device_id", String(255), primary_key=True),
    Column("kind", String(255), nullable=False),
    Column("simulated", Boolean, nullable=False),
    Column("registered_at", Timestamp, nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("body", Body, nullable=False, comment="DeviceRecord, canonical JSON."),
    comment="DeviceRecord rows.",
)

objects = Table(
    "objects",
    metadata,
    Column("sha256", String(64), primary_key=True, comment="QdtModel.content_sha256 of the body."),
    Column("type", String(64), nullable=False, comment="migrations.PERSISTED type name."),
    Column("schema_version", Integer, nullable=False),
    Column("name", String(255), nullable=True, comment="stand_id, definition name or plan_id."),
    Column("body", Body, nullable=False, comment="The object, canonical JSON."),
    Index("ix_objects_type_name", "type", "name"),
    comment="Content-addressed StandConfig, SweepDefinition and ExecutionPlan bodies (ADR 0025).",
)

records = Table(
    "records",
    metadata,
    Column("record_id", String(32), primary_key=True),
    Column("device_id", String(255), ForeignKey("devices.device_id"), nullable=False),
    Column("stand_id", String(255), nullable=False),
    Column("stand_sha256", String(64), ForeignKey("objects.sha256"), nullable=False),
    Column("definition_name", String(255), nullable=False),
    Column("definition_sha256", String(64), ForeignKey("objects.sha256"), nullable=False),
    Column("plan_sha256", String(64), ForeignKey("objects.sha256"), nullable=False),
    Column("plan_id", String(255), nullable=False),
    Column("started_at", Timestamp, nullable=False),
    Column("finished_at", Timestamp, nullable=False),
    Column("outcome", String(16), nullable=False),
    Column("campaign", String(255), nullable=True),
    Column("payload_path", Text, nullable=False),
    Column("payload_sha256", String(64), nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("body", Body, nullable=False, comment="MeasurementRecord, canonical JSON."),
    CheckConstraint("outcome in ('completed', 'aborted')", name="ck_records_outcome"),
    Index("ix_records_device", "device_id", "started_at"),
    Index("ix_records_stand", "stand_sha256"),
    Index("ix_records_definition", "definition_sha256"),
    Index("ix_records_stand_id", "stand_id"),
    Index("ix_records_campaign", "campaign"),
    comment="MeasurementRecord envelopes; the Step 3 exit query runs here.",
)

analysis_results = Table(
    "analysis_results",
    metadata,
    Column("result_id", String(32), primary_key=True),
    Column("record_id", String(32), ForeignKey("records.record_id"), nullable=False),
    Column("method_name", String(255), nullable=False),
    Column("method_sha256", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("created_at", Timestamp, nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("body", Body, nullable=False, comment="AnalysisResult, canonical JSON."),
    CheckConstraint("status in ('ok', 'failed')", name="ck_analysis_results_status"),
    Index("ix_analysis_results_record", "record_id", "created_at"),
    Index("ix_analysis_results_method", "method_sha256"),
    comment="AnalysisResult rows: estimates and overlays with dual provenance (Step 4, ADR 0029).",
)

tuning_outcomes = Table(
    "tuning_outcomes",
    metadata,
    Column("outcome_id", String(32), primary_key=True),
    Column("tuneup_id", String(32), nullable=True),
    Column("node_id", String(255), nullable=False),
    Column("record_id", String(32), ForeignKey("records.record_id"), nullable=True),
    Column("result_id", String(32), ForeignKey("analysis_results.result_id"), nullable=True),
    Column("status", String(16), nullable=False),
    Column("created_at", Timestamp, nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("body", Body, nullable=False, comment="NodeOutcome, canonical JSON."),
    CheckConstraint(
        "status in ('accepted', 'rejected', 'failed')", name="ck_tuning_outcomes_status"
    ),
    Index("ix_tuning_outcomes_tuneup", "tuneup_id", "created_at"),
    Index("ix_tuning_outcomes_node", "node_id", "created_at"),
    comment="NodeOutcome rows: a calibration node's verdict and decided quantities, pointing at its record and result (Step 6, ADR 0050).",
)

stand_states = Table(
    "stand_states",
    metadata,
    Column("stand_id", String(255), primary_key=True),
    Column("version", Integer, primary_key=True),
    Column("set_by", String(255), nullable=False),
    Column("set_at", Timestamp, nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("body", Body, nullable=False, comment="StandState, canonical JSON."),
    CheckConstraint("version >= 1", name="ck_stand_states_version"),
    comment=(
        "StandState versions: a stand's limits, couplings and held operating point; the highest "
        "version of a stand is in force (Step 6c, ADR 0075, 0085)."
    ),
)

cache_metadata = MetaData()

sync_state = Table(
    "sync_state",
    cache_metadata,
    Column("table_name", String(32), primary_key=True),
    Column("key", String(255), primary_key=True),
    Column("synced", Boolean, nullable=False, default=False),
    comment="Cache only: which rows (and record payloads) the server has confirmed.",
)
