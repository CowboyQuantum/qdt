"""Modeling slice (ADR 0029): an AnalysisResult always carries both halves of its provenance."""

import json
import pathlib

import pytest
from pydantic import ValidationError

from qdt_schemas.modeling import AnalysisResult

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "AnalysisResult" / "v1.json"


def data() -> dict:
    return json.loads(FIXTURE.read_text())


@pytest.mark.parametrize("missing", ["record_id", "method", "method_sha256"])
def test_missing_either_half_of_the_provenance_fails(missing):
    d = data()
    del d[missing]
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(d)


def test_method_hash_must_match_the_method():
    d = data()
    d["method"]["parameters"]["smooth_px"] = 2.0
    with pytest.raises(ValidationError, match="method_sha256"):
        AnalysisResult.model_validate(d)


def test_overlays_decorate_the_analysed_dataset_only():
    d = data()
    d["annotations"][0]["dataset_id"] = "elsewhere"
    with pytest.raises(ValidationError, match="another dataset"):
        AnalysisResult.model_validate(d)


def test_an_ok_result_says_something():
    d = data() | {"estimates": [], "annotations": []}
    with pytest.raises(ValidationError, match="ok result"):
        AnalysisResult.model_validate(d)
    AnalysisResult.model_validate(d | {"status": "failed", "message": "no transitions"})


def test_estimate_names_are_unique():
    d = data()
    d["estimates"] = d["estimates"] * 2
    with pytest.raises(ValidationError, match="unique"):
        AnalysisResult.model_validate(d)
