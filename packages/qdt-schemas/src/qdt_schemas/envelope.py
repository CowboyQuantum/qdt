"""Step 3 schema slice: the `MeasurementRecord` envelope (ADR 0001, ADR 0025).

A record is a small provenance envelope: which device, on which stand, from which definition, when, and
where the payload is. It holds references and content hashes, never arrays or whole configurations. The
stand, plan and data travel in the payload (first spec `qdt-hdf5-v1`, `payload_hdf5.py`), and the
registry indexes them by `content_sha256`. Record ids are minted by the client as UUIDs so that a record
written offline and synced later never conflicts (ADR 0024).
"""

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from ._base import QdtModel
from .data import AttrValue, SourceDescriptor

PayloadType = Literal["qdt-hdf5-v1"]
SHA256 = r"^[0-9a-f]{64}$"


class PayloadRef(QdtModel):
    """Where a record's payload is and how to verify it."""

    type: PayloadType = Field(description="Payload spec the file follows; selects the validator.")
    path: str = Field(
        min_length=1,
        pattern=r"^[^/\\][^\\]*$",
        description=(
            "Path relative to the payload store root, '/'-separated, e.g. '2026/10/<record_id>.h5'. "
            "Never absolute: the store root differs per client and server."
        ),
    )
    sha256: str = Field(pattern=SHA256, description="Hex SHA-256 of the payload file's bytes.")
    size_bytes: int = Field(ge=0, description="Size of the payload file in bytes.")


class MeasurementRecord(QdtModel):
    """One run's provenance envelope: answerable by device, stand and definition (Step 3 exit query)."""

    record_id: str = Field(
        pattern=r"^[0-9a-f]{32}$",
        description="Client-minted UUID4 as 32 lowercase hex digits; never a database sequence (ADR 0024).",
    )
    device_id: str = Field(min_length=1, description="DeviceRecord.device_id measured.")
    stand_id: str = Field(min_length=1, description="StandConfig.stand_id it ran on.")
    stand_sha256: str = Field(
        pattern=SHA256,
        description="content_sha256 of the StandConfig as run; the stand itself is in the payload.",
    )
    definition_name: str = Field(
        min_length=1, description="SweepDefinition.name, for display and search."
    )
    definition_sha256: str = Field(
        pattern=SHA256,
        description="content_sha256 of the SweepDefinition; equal hashes mean the same experiment.",
    )
    plan_id: str = Field(min_length=1, description="ExecutionPlan.plan_id; also the Dataset id.")
    source: SourceDescriptor = Field(
        description="Kind of source that produced the data ('simulation' or 'live' for a sweep)."
    )
    started_at: AwareDatetime = Field(description="When the run started.")
    finished_at: AwareDatetime = Field(description="When the run ended, completed or not.")
    outcome: Literal["completed", "aborted"] = Field(
        description="completed: every declared point was written. aborted: stopped early; unwritten cells are NaN or 0."
    )
    campaign: str | None = Field(
        default=None,
        description="Optional grouping label for related runs, e.g. a cooldown or a study.",
    )
    payload: PayloadRef = Field(description="The payload file this envelope describes.")
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict, description="Free-form scalar metadata."
    )

    @model_validator(mode="after")
    def _ordered(self) -> "MeasurementRecord":
        if self.finished_at < self.started_at:
            raise ValueError("finished_at precedes started_at")
        return self
