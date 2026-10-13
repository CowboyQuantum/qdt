"""Step 4 schema slice: modeling — how data was analysed and what came out (ADR 0029).

FROZEN (ADR 0033): `FitModel`, `Estimate`, `AnalysisResult` at `schema_version` 1. Any change bumps the
version, adds a migration and keeps the old fixture, and carries an ADR (`packages/qdt-schemas/CLAUDE.md`).
Step 6 adds `SimScenario`, `SimResult`, `CalibrationNode` beside them.

An `AnalysisResult` has dual provenance, and both halves are mandatory: *what data* (the
`MeasurementRecord` it read, plus the Dataset it decorates) and *how* (the `FitModel`: method name,
version and parameters, content-addressed). The same record analysed by the same method with the same
parameters gives results with the same `method_sha256`. Overlays are ordinary `Annotation`s on the
originating Dataset, so Flight Deck draws them with no analysis-specific code.

A method may also produce arrays (a fitted map, a residual, the image it detected on, a derived graph).
Those never live in the result: they are a `Dataset` of their own, with `source.kind = "analysis"`,
written as a `qdt-hdf5-v1` payload and referenced by `AnalysisResult.output` (ADR 0031), so Flight
Deck draws them like any measurement and the registry stores them like any payload.

Simulated ground truth (`SimScenario`) is a Step 6 family. Until then, injection-recovery truth lives in
the tests, not in results.
"""

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from ._base import QdtModel
from .data import Annotation, AttrValue
from .envelope import PayloadRef

SHA256 = r"^[0-9a-f]{64}$"


class FitModel(QdtModel):
    """An analysis method as data: which function, which version, which parameters."""

    name: str = Field(
        min_length=1,
        description="Dotted method name, e.g. 'qdt_analysis.transitions.detect_transitions'.",
    )
    version: str = Field(
        min_length=1,
        description="Method version; bump it whenever the same inputs could give a different result.",
    )
    parameters: dict[str, AttrValue] = Field(
        default_factory=dict,
        description="Every parameter the method used, defaults included, so a result can be reproduced.",
    )


class Estimate(QdtModel):
    """One estimated quantity, with its uncertainty when the method provides one."""

    name: str = Field(
        min_length=1, description="Quantity name, unique within the result, e.g. 'slope_steep'."
    )
    value: float = Field(description="Estimated value in `unit`.")
    stderr: float | None = Field(
        default=None, ge=0, description="Standard error in `unit`; None when the method gives none."
    )
    unit: str = Field(description="Physical unit, e.g. 'V/V'; empty for dimensionless.")


class AnalysisResult(QdtModel):
    """The output of one method on one measurement: estimates plus overlays, with dual provenance."""

    result_id: str = Field(
        pattern=r"^[0-9a-f]{32}$",
        description="Client-minted UUID4 as 32 lowercase hex digits (ADR 0024).",
    )
    record_id: str = Field(
        pattern=r"^[0-9a-f]{32}$",
        description="MeasurementRecord.record_id analysed: the data half of the provenance.",
    )
    dataset_id: str = Field(
        min_length=1, description="Dataset the overlays decorate (the record's plan_id)."
    )
    method: FitModel = Field(
        description="How the data was analysed: the method half of the provenance."
    )
    method_sha256: str = Field(
        pattern=SHA256, description="content_sha256 of `method`; checked on validation."
    )
    status: Literal["ok", "failed"] = Field(
        description="ok: estimates are meaningful. failed: the method ran but found nothing usable; see `message`."
    )
    message: str = Field(default="", description="Human-readable note, e.g. why it failed.")
    estimates: tuple[Estimate, ...] = Field(default=(), description="Estimated quantities.")
    annotations: tuple[Annotation, ...] = Field(
        default=(), description="Overlays on the originating Dataset, in its coordinate system."
    )
    output: PayloadRef | None = Field(
        default=None,
        description=(
            "Arrays the method produced, as a qdt-hdf5-v1 payload holding a Dataset of its own "
            "(`source.kind = 'analysis'`) with named variables and coordinates (ADR 0031). None when the "
            "method produced only estimates and overlays. Set by the registry when it stores the output."
        ),
    )
    created_at: AwareDatetime = Field(description="When the analysis ran.")
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict, description="Free-form scalar metadata, e.g. figures of merit."
    )

    @model_validator(mode="after")
    def _consistent(self) -> "AnalysisResult":
        if self.method_sha256 != self.method.content_sha256():
            raise ValueError("method_sha256 does not match method")
        names = [e.name for e in self.estimates]
        if len(set(names)) != len(names):
            raise ValueError("estimate names must be unique")
        for a in self.annotations:
            if a.dataset_id != self.dataset_id:
                raise ValueError(f"annotation {a.annotation_id!r} decorates another dataset")
        ids = [a.annotation_id for a in self.annotations]
        if len(set(ids)) != len(ids):
            raise ValueError("annotation ids must be unique")
        if self.status == "ok" and not (self.estimates or self.annotations):
            raise ValueError("an ok result carries estimates or annotations")
        return self

    def estimate(self, name: str) -> Estimate:
        for e in self.estimates:
            if e.name == name:
                return e
        raise KeyError(f"no estimate {name!r}")
