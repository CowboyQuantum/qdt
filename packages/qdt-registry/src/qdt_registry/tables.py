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

DDL_VERSION = 1
"""Bumps with every table change; a change is an ADR plus an additive migration, never a DROP."""

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

cache_metadata = MetaData()

sync_state = Table(
    "sync_state",
    cache_metadata,
    Column("table_name", String(32), primary_key=True),
    Column("key", String(255), primary_key=True),
    Column("synced", Boolean, nullable=False, default=False),
    comment="Cache only: which rows (and record payloads) the server has confirmed.",
)
