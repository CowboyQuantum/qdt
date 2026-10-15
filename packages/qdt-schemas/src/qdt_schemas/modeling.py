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

Step 6 (ADR 0048) adds, beside the frozen three: `SimScenario` (a reproducible simulated situation: model
overrides, seed, noise; the truth is derived from the model by `qdt-sim`, never stored here),
`CalibrationNode` (one step of a tune-up as data: the experiment, the method that reads it, the
`DecisionRule` that judges it), `NodeOutcome` (what running a node produced: its record, its result, the
verdict and the decided quantities) and `SimResult` (a committed outcome of a node on a scenario, with the
truth, that CI reproduces). None of the four is persisted yet; outcomes point at records and results, which are.
"""

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from ._base import QdtModel
from .activity import SweepDefinition
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


# --- Step 6: scenarios, calibration nodes, outcomes (ADR 0048) ------------------------------------


class SimScenario(QdtModel):
    """A reproducible simulated situation: which scalar parameters of the simulated device's model are
    overridden, which seed, whether noise is on. `qdt-sim` realizes it into a device and derives the
    truth a method must recover; this package holds the recipe only (rule 1)."""

    scenario_id: str = Field(
        min_length=1, description="Stable name of the scenario, e.g. 'default-occupied-window'."
    )
    description: str = Field(default="", description="What the scenario stands for.")
    model: dict[str, AttrValue] = Field(
        default_factory=dict,
        description=(
            "Scalar overrides of the simulated device's default model, by field name (e.g. "
            "sensor_width_v). Matrix parameters are not overridable through a scenario yet."
        ),
    )
    seed: int = Field(default=0, ge=0, description="Seed of every random draw in the device.")
    noise: bool = Field(default=True, description="Whether the device's noise models are on.")
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict, description="Free-form scalar metadata."
    )


class DecisionRule(QdtModel):
    """A curated decision as data: which rule judges a node's result, with which parameters (the
    `FitModel` of decisions)."""

    name: str = Field(
        min_length=1, description="Dotted rule name, e.g. 'qdt_tuning.decisions.virtual_gates'."
    )
    version: str = Field(
        min_length=1,
        description="Rule version; bump it whenever the same result could be judged differently.",
    )
    parameters: dict[str, AttrValue] = Field(
        default_factory=dict,
        description="Every parameter the rule used, defaults included, so a verdict can be reproduced.",
    )


class InputBinding(QdtModel):
    """Where a node's definition takes a value from an upstream node's accepted outputs (ADR 0049)."""

    node_id: str = Field(min_length=1, description="The upstream node; must be in `depends_on`.")
    output: str = Field(min_length=1, description="The name in that node's `NodeOutcome.outputs`.")
    target: str = Field(
        min_length=1,
        description=(
            "Dotted path into this node's `definition` that takes the value, e.g. "
            "'axes.0.couplings.P2' or 'stage.sequence.body.0.level.scale'."
        ),
    )


class CalibrationNode(QdtModel):
    """One step of a tune-up as data: the experiment to run, the curated method that reads its record,
    the rule that turns the estimates into a verdict and the quantities the next node needs. `inputs`
    name the places in `definition` an upstream node's outputs fill before the node runs."""

    node_id: str = Field(
        min_length=1, description="Stable name of the node, e.g. 'charge-lattice'."
    )
    description: str = Field(default="", description="What the node establishes.")
    definition: SweepDefinition = Field(
        description="The experiment, in the stand's logical channel names."
    )
    method: FitModel = Field(
        description="The curated method that reads the record, with every parameter."
    )
    decision: DecisionRule = Field(description="The rule that judges the method's result.")
    depends_on: tuple[str, ...] = Field(
        default=(), description="Node ids whose accepted outcomes this node needs; unique."
    )
    inputs: tuple[InputBinding, ...] = Field(
        default=(),
        description="Values of `definition` filled from upstream outputs before the node runs; unique targets.",
    )
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict, description="Free-form scalar metadata."
    )

    @model_validator(mode="after")
    def _consistent(self) -> "CalibrationNode":
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("depends_on names each node once")
        if self.node_id in self.depends_on:
            raise ValueError("a node does not depend on itself")
        targets = [b.target for b in self.inputs]
        if len(set(targets)) != len(targets):
            raise ValueError("each input target is bound once")
        unknown = {b.node_id for b in self.inputs} - set(self.depends_on)
        if unknown:
            raise ValueError(f"inputs come from {sorted(unknown)}, which are not in depends_on")
        return self


NodeStatus = Literal["accepted", "rejected", "failed"]


class NodeOutcome(QdtModel):
    """What running a node produced: the record and result it made (durable, in the registry), the
    rule's verdict and the quantities it decided. The lifecycle state Flight Deck renders and never stores."""

    outcome_id: str = Field(
        pattern=r"^[0-9a-f]{32}$", description="Client-minted UUID4 as 32 lowercase hex digits."
    )
    node_id: str = Field(min_length=1, description="The CalibrationNode that ran.")
    scenario_id: str | None = Field(
        default=None, description="The SimScenario it ran on; None on a real device."
    )
    record_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{32}$",
        description="MeasurementRecord the experiment produced; None when it failed before recording.",
    )
    result_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{32}$",
        description="AnalysisResult the method produced; None when it failed before analysing.",
    )
    status: NodeStatus = Field(
        description=(
            "accepted: the rule took the result and `outputs` hold the decided quantities. rejected: the "
            "result was read but the rule declined it; see `message`. failed: the experiment or the "
            "method did not complete."
        )
    )
    message: str = Field(default="", description="Human-readable note, e.g. why it was rejected.")
    outputs: dict[str, float] = Field(
        default_factory=dict,
        description="The decided quantities by name, e.g. a virtual-gate matrix's entries; empty unless accepted.",
    )
    created_at: AwareDatetime = Field(description="When the decision was made.")
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict,
        description="Free-form scalar metadata, e.g. figures the rule checked.",
    )

    @model_validator(mode="after")
    def _consistent(self) -> "NodeOutcome":
        if self.status == "accepted" and (self.record_id is None or self.result_id is None):
            raise ValueError("an accepted outcome names its record and result")
        if self.status != "accepted" and self.outputs:
            raise ValueError("only an accepted outcome carries outputs")
        return self


class SimResult(QdtModel):
    """A committed outcome of a node on a scenario, with the truth the model gives for the decided
    quantities: the fixture CI reproduces (within tolerance) whenever the node, the method or the
    simulator changes."""

    scenario: SimScenario = Field(description="The scenario the node ran on.")
    node_id: str = Field(min_length=1, description="The node that ran.")
    outcome: NodeOutcome = Field(description="What it produced.")
    estimates: tuple[Estimate, ...] = Field(
        default=(), description="The method's estimates the rule judged."
    )
    truth: dict[str, float] = Field(
        default_factory=dict,
        description="The model's values for the decided quantities, by the same names as `outputs`.",
    )
    created_at: AwareDatetime = Field(description="When the fixture was made.")
