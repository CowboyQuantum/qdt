"""Modeling slice (ADR 0029): an AnalysisResult needs both provenance legs and owns its annotations."""

import json
import pathlib

import pytest
from pydantic import ValidationError

from qdt_schemas.modeling import AnalysisResult, FitModel, MeasurementRef, ScenarioRef

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def fixture() -> dict:
    return json.loads((FIXTURES / "AnalysisResult" / "v1.json").read_text())


def result(**update) -> AnalysisResult:
    return AnalysisResult.model_validate(fixture() | update)


def test_result_round_trips_through_json():
    r = result()
    assert AnalysisResult.model_validate_json(r.model_dump_json()) == r
    assert r.content_sha256() == result().content_sha256()


@pytest.mark.parametrize("leg", ["measurement", "scenario"])
def test_missing_provenance_leg_fails_validation(leg):
    data = fixture()
    del data[leg]
    with pytest.raises(ValidationError, match=leg):
        AnalysisResult.model_validate(data)


def test_measurement_ref_needs_dataset_and_variable_but_not_a_record():
    ref = MeasurementRef(dataset_id="d", variable="I")
    assert ref.record_id is None
    with pytest.raises(ValidationError):
        MeasurementRef(dataset_id="d", variable="I", record_id="not-hex")
    with pytest.raises(ValidationError):
        MeasurementRef(dataset_id="", variable="I")


def test_scenario_ref_is_name_plus_seed():
    ref = ScenarioRef(kind="simulation", name="stability", seed=3)
    assert ref.parameters == {}
    with pytest.raises(ValidationError):
        ScenarioRef(kind="live", name="stability", seed=3)  # Step 5 decides what live data refers to
    with pytest.raises(ValidationError):
        ScenarioRef(kind="simulation", name="stability", seed=-1)


def test_annotations_must_decorate_the_measured_dataset():
    data = fixture()
    data["annotations"][0]["dataset_id"] = "other"
    with pytest.raises(ValidationError, match="not the measured Dataset"):
        AnalysisResult.model_validate(data)


def test_annotation_ids_are_unique_within_a_result():
    data = fixture()
    data["annotations"] = [data["annotations"][0], data["annotations"][0]]
    with pytest.raises(ValidationError, match="unique"):
        AnalysisResult.model_validate(data)


def test_fit_model_parameters_are_scalar():
    with pytest.raises(ValidationError):
        FitModel(name="m", version="1", parameters={"sigma": [1, 2]})


def test_analysis_id_is_32_hex():
    with pytest.raises(ValidationError):
        result(analysis_id="x")
