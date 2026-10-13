"""Step 4 schema slice: modeling — what an analysis ran on, what it found, and what generated the data
(ADR 0029).

An `AnalysisResult` carries dual provenance. `MeasurementRef` says which Dataset (and, once stored, which
registry record) it was computed from. `ScenarioRef` says which reproducible generator made that data:
for simulated and synthetic data this is a scenario name and a seed, enough to regenerate the truth
behind the measurement and compare (injection–recovery). Findings travel as `Annotation`s in the
originating Dataset's coordinate system, so Flight Deck draws them with no analysis-specific code, plus
scalar summaries. Arrays never live here; a result that needs arrays writes a payload.

Step 6 adds `SimScenario`, `SimResult` and `CalibrationNode` to this module (plan §4.1).
"""

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from ._base import QdtModel
from .data import Annotation, AttrValue

HEX32 = r"^[0-9a-f]{32}$"


class FitModel(QdtModel):
    """The model or detector an analysis ran, with the parameters it ran with."""

    name: str = Field(
        min_length=1,
        description="Model or detector name, e.g. 'charge_transition_lines'; stable across versions.",
    )
    version: str = Field(
        min_length=1,
        description="Implementation version that produced the result, e.g. qdt_analysis.__version__.",
    )
    parameters: dict[str, AttrValue] = Field(
        default_factory=dict,
        description="Hyperparameters as run (thresholds, smoothing, ...); enough to repeat the analysis.",
    )


class MeasurementRef(QdtModel):
    """Which measurement an analysis ran on: a Dataset, one of its variables, and its record if stored."""

    dataset_id: str = Field(
        min_length=1, description="Dataset analysed; for a recorded sweep this is the plan_id."
    )
    variable: str = Field(min_length=1, description="Data variable of the Dataset that was analysed.")
    record_id: str | None = Field(
        default=None,
        pattern=HEX32,
        description=(
            "MeasurementRecord.record_id when the Dataset is in the registry; None for data that was "
            "never recorded (a synthetic map in a test). The registry refuses to store a result without it."
        ),
    )


class ScenarioRef(QdtModel):
    """The reproducible generator behind a measurement: name + seed regenerate the data and its truth."""

    kind: Literal["simulation", "synthetic"] = Field(
        description=(
            "simulation: a qdt_sim scenario (physics model + noise + sweep). synthetic: a generator with "
            "known injected features and no physics. Live data gets its own kind by ADR in Step 5."
        )
    )
    name: str = Field(
        min_length=1,
        description="Scenario name, e.g. 'stability' (a qdt_sim.scenarios sweep) or a test generator's name.",
    )
    seed: int = Field(ge=0, description="Random seed the scenario ran with; fixes every draw.")
    parameters: dict[str, AttrValue] = Field(
        default_factory=dict,
        description="Scenario arguments beyond the defaults (grid size, ranges, noise on/off), scalar only.",
    )


class AnalysisResult(QdtModel):
    """What an analysis found on one measurement, with the measurement and the scenario it came from."""

    analysis_id: str = Field(
        pattern=HEX32, description="Client-minted UUID4 as 32 lowercase hex digits (ADR 0024)."
    )
    model: FitModel = Field(description="What ran, and with which parameters.")
    measurement: MeasurementRef = Field(description="What it ran on. Mandatory.")
    scenario: ScenarioRef = Field(description="What generated the data it ran on. Mandatory.")
    annotations: tuple[Annotation, ...] = Field(
        default=(),
        description=(
            "Findings as overlays on the measurement's Dataset (lines, markers, regions, curves); every "
            "one carries `measurement.dataset_id` and unique ids within the result."
        ),
    )
    summary: dict[str, AttrValue] = Field(
        default_factory=dict,
        description="Scalar outcomes: counts, fitted values, quality figures. Per-feature values go on the annotations.",
    )
    created_at: AwareDatetime = Field(description="When the analysis ran.")
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict, description="Free-form scalar metadata."
    )

    @model_validator(mode="after")
    def _annotations_belong_here(self) -> "AnalysisResult":
        ids = [a.annotation_id for a in self.annotations]
        if len(set(ids)) != len(ids):
            raise ValueError("annotation ids must be unique within a result")
        for a in self.annotations:
            if a.dataset_id != self.measurement.dataset_id:
                raise ValueError(
                    f"annotation {a.annotation_id!r} decorates {a.dataset_id!r}, "
                    f"not the measured Dataset {self.measurement.dataset_id!r}"
                )
        return self
