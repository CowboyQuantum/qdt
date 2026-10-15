"""Step 4b schema slice: control — what the UI asks the server to do, as data (ADR 0032, ADR 0034).

A `Run` is the lifecycle of one execution of a plan: queued, running, then completed (with the record
it produced), aborted or failed. The server keeps runs in memory; the durable thing is the
`MeasurementRecord`. A `MethodSpec` is a catalogue entry for a curated analysis method: its name and
version (the `FitModel` a result will carry), the parameters a form offers, the Dataset shapes it applies
to and the estimates it promises. Users run methods; they do not author them (ADR 0031).

Both are rendered by the UI and never stored in it (`docs/FINISH_LINE.md`). Frozen at schema_version 1
by ADR 0036.
"""

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from ._base import QdtModel
from .data import AttrValue
from .modeling import FitModel

RunState = Literal["queued", "running", "completed", "aborted", "failed"]
ParameterKind = Literal["float", "int", "str", "bool"]
_KINDS: dict[str, type | tuple[type, ...]] = {
    "float": (int, float),
    "int": int,
    "str": str,
    "bool": bool,
}


class ParameterSpec(QdtModel):
    """One parameter a method takes: enough for a form to offer it and the server to validate it."""

    name: str = Field(min_length=1, description="Keyword name the method takes.")
    kind: ParameterKind = Field(description="Scalar type of the value.")
    default: AttrValue = Field(
        description="Value used when the caller gives none; also the example."
    )
    unit: str = Field(default="", description="Unit for display, e.g. 'px', 'deg'; empty if none.")
    minimum: float | None = Field(default=None, description="Lowest admissible value, if bounded.")
    maximum: float | None = Field(default=None, description="Highest admissible value, if bounded.")
    description: str = Field(default="", description="One line for the form's help text.")

    @model_validator(mode="after")
    def _default_fits(self) -> "ParameterSpec":
        self.check(self.default)
        return self

    def check(self, value: AttrValue) -> AttrValue:
        """Return `value` if it is admissible for this parameter; raise ValueError otherwise."""
        kinds = _KINDS[self.kind]
        if isinstance(value, bool) and self.kind != "bool":
            raise ValueError(f"{self.name}: expected {self.kind}, got a bool")
        if not isinstance(value, kinds):
            raise ValueError(  # noqa: TRY004 — pydantic turns ValueError into ValidationError
                f"{self.name}: expected {self.kind}, got {type(value).__name__}"
            )
        if self.kind in ("float", "int"):
            if self.minimum is not None and value < self.minimum:
                raise ValueError(f"{self.name}: {value} is below the minimum {self.minimum}")
            if self.maximum is not None and value > self.maximum:
                raise ValueError(f"{self.name}: {value} is above the maximum {self.maximum}")
        return float(value) if self.kind == "float" else value


class EstimateSpec(QdtModel):
    """An estimate a method promises in its results."""

    name: str = Field(min_length=1, description="`Estimate.name` the method reports.")
    unit: str = Field(
        default="", description="Unit of the estimate; may depend on the data's units."
    )
    description: str = Field(default="", description="One line for display.")


class MethodSpec(QdtModel):
    """A curated analysis method as the UI sees it: what it is called, what it takes, what it gives."""

    name: str = Field(
        min_length=1, description="Dotted method name, equal to the `FitModel.name` of its results."
    )
    version: str = Field(min_length=1, description="Method version, equal to `FitModel.version`.")
    title: str = Field(min_length=1, description="Short display name, e.g. 'Charge transitions'.")
    description: str = Field(default="", description="What the method does, for the UI.")
    applies_to: Literal["map_2d", "trace_1d"] = Field(
        description=(
            "Dataset shape the method accepts; map_2d: a variable over two linear coordinates; "
            "trace_1d: a variable over one linear coordinate (time), any leading dims uncoordinated "
            "(records, shots). trace_1d was added without a version bump (ADR 0046)."
        )
    )
    parameters: tuple[ParameterSpec, ...] = Field(
        default=(), description="Parameters a caller may set; unique names."
    )
    estimates: tuple[EstimateSpec, ...] = Field(
        default=(), description="Estimates an `ok` result carries; unique names."
    )

    @model_validator(mode="after")
    def _unique(self) -> "MethodSpec":
        for what, items in (("parameter", self.parameters), ("estimate", self.estimates)):
            names = [i.name for i in items]
            if len(set(names)) != len(names):
                raise ValueError(f"{what} names must be unique")
        return self

    def parameter(self, name: str) -> ParameterSpec:
        for p in self.parameters:
            if p.name == name:
                return p
        raise KeyError(f"{self.name} has no parameter {name!r}")

    def resolve(self, given: dict[str, AttrValue]) -> dict[str, AttrValue]:
        """Every parameter's value: `given` over the defaults, each checked. Unknown names are an error."""
        unknown = set(given) - {p.name for p in self.parameters}
        if unknown:
            raise ValueError(f"{self.name} has no parameters {sorted(unknown)}")
        return {p.name: p.check(given.get(p.name, p.default)) for p in self.parameters}

    def fit_model(self, given: dict[str, AttrValue]) -> FitModel:
        """The `FitModel` a result of this method with `given` parameters carries."""
        return FitModel(name=self.name, version=self.version, parameters=self.resolve(given))


class Run(QdtModel):
    """The lifecycle of one execution of a plan on the server."""

    run_id: str = Field(
        pattern=r"^[0-9a-f]{32}$", description="Server-minted UUID4 as 32 lowercase hex digits."
    )
    plan_id: str = Field(min_length=1, description="ExecutionPlan.plan_id; also the Dataset id.")
    definition_name: str = Field(min_length=1, description="SweepDefinition.name, for display.")
    definition_sha256: str = Field(
        pattern=r"^[0-9a-f]{64}$", description="content_sha256 of the SweepDefinition."
    )
    stand_id: str = Field(min_length=1, description="Stand it runs on.")
    device_id: str = Field(min_length=1, description="Device it runs against.")
    state: RunState = Field(description="queued → running → completed | aborted | failed.")
    created_at: AwareDatetime = Field(description="When the run was accepted.")
    started_at: AwareDatetime | None = Field(default=None, description="When frames started.")
    finished_at: AwareDatetime | None = Field(default=None, description="When it left `running`.")
    record_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{32}$",
        description="The MeasurementRecord it produced, once ingested (completed or aborted).",
    )
    error: str = Field(default="", description="Why it failed; empty otherwise.")
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict, description="Free-form scalar metadata, e.g. seed, campaign."
    )

    @model_validator(mode="after")
    def _consistent(self) -> "Run":
        if self.state == "failed" and not self.error:
            raise ValueError("a failed run says why")
        if self.state in ("queued", "running") and self.finished_at is not None:
            raise ValueError(f"a {self.state} run has no finished_at")
        if self.state == "queued" and self.started_at is not None:
            raise ValueError("a queued run has no started_at")
        return self
