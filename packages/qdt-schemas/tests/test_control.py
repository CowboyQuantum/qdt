"""Control slice (ADR 0032): runs have a consistent lifecycle; method specs validate parameters."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from qdt_schemas.control import EstimateSpec, MethodSpec, ParameterSpec, Run

T0 = datetime(2026, 10, 13, tzinfo=UTC)


def spec() -> MethodSpec:
    return MethodSpec(
        name="qdt_analysis.transitions.detect_transitions",
        version="1",
        title="Charge transitions",
        applies_to="map_2d",
        parameters=(
            ParameterSpec(name="smooth_px", kind="float", default=1.0, unit="px", minimum=0.0),
            ParameterSpec(name="min_segment_px", kind="int", default=6, minimum=2),
            ParameterSpec(name="variable", kind="str", default=""),
            ParameterSpec(name="verbose", kind="bool", default=False),
        ),
        estimates=(EstimateSpec(name="a_per_volt_row", unit="1/V"),),
    )


def test_resolve_fills_defaults_and_checks_values():
    s = spec()
    assert s.resolve({}) == {
        "smooth_px": 1.0,
        "min_segment_px": 6,
        "variable": "",
        "verbose": False,
    }
    assert s.resolve({"smooth_px": 2})["smooth_px"] == 2.0  # an int is a fine float
    fm = s.fit_model({"min_segment_px": 8})
    assert fm.name == s.name and fm.version == "1" and fm.parameters["min_segment_px"] == 8


@pytest.mark.parametrize(
    ("given", "match"),
    [
        ({"smooth_px": -1}, "below the minimum"),
        ({"min_segment_px": 1}, "below the minimum"),
        ({"min_segment_px": 2.5}, "expected int"),
        ({"smooth_px": True}, "got a bool"),
        ({"variable": 3}, "expected str"),
        ({"nope": 1}, "no parameters"),
    ],
)
def test_resolve_rejects_bad_values(given, match):
    with pytest.raises(ValueError, match=match):
        spec().resolve(given)


def test_default_must_fit_its_own_spec():
    with pytest.raises(ValidationError, match="below the minimum"):
        ParameterSpec(name="x", kind="int", default=0, minimum=1)
    with pytest.raises(ValidationError, match="expected int"):
        ParameterSpec(name="x", kind="int", default=1.5)


def test_names_are_unique():
    p = ParameterSpec(name="x", kind="int", default=1)
    with pytest.raises(ValidationError, match="unique"):
        MethodSpec(name="m", version="1", title="M", applies_to="map_2d", parameters=(p, p))


def run(**update) -> Run:
    base = {
        "run_id": "ab" * 16,
        "plan_id": "plan",
        "definition_name": "stability",
        "definition_sha256": "0" * 64,
        "stand_id": "stand",
        "device_id": "dot",
        "state": "queued",
        "created_at": T0,
    }
    return Run.model_validate(base | update)


def test_run_lifecycle_is_consistent():
    assert run().state == "queued"
    r = run(state="completed", started_at=T0, finished_at=T0, record_id="cd" * 16)
    assert Run.model_validate_json(r.model_dump_json()) == r
    with pytest.raises(ValidationError, match="says why"):
        run(state="failed", started_at=T0, finished_at=T0)
    with pytest.raises(ValidationError, match="no finished_at"):
        run(state="running", started_at=T0, finished_at=T0)
    with pytest.raises(ValidationError, match="no started_at"):
        run(started_at=T0)


# Frozen at schema_version 1 by ADR 0036. Neither type is persisted (runs live in the server's memory,
# specs in its catalogue), so instead of migration fixtures these v1 wire examples pin the shape: a
# renamed, removed or newly required field fails here, and needs an ADR, a version bump and the UI's
# regenerated types in the same commit.
RUN_V1 = {
    "schema_version": 1,
    "run_id": "ab" * 16,
    "plan_id": "plan-1",
    "definition_name": "stability",
    "definition_sha256": "0" * 64,
    "stand_id": "simulated-double-dot",
    "device_id": "dev-1",
    "state": "aborted",
    "created_at": "2026-10-13T00:00:00Z",
    "started_at": "2026-10-13T00:00:01Z",
    "finished_at": "2026-10-13T00:00:02Z",
    "record_id": "cd" * 16,
    "error": "",
    "attrs": {"seed": 1, "campaign": "demo"},
}
METHOD_SPEC_V1 = {
    "schema_version": 1,
    "name": "qdt_analysis.transitions.detect_transitions",
    "version": "1",
    "title": "Charge transitions",
    "description": "",
    "applies_to": "map_2d",
    "parameters": [
        {
            "schema_version": 1,
            "name": "smooth_px",
            "kind": "float",
            "default": 1.0,
            "unit": "px",
            "minimum": 0.0,
            "maximum": None,
            "description": "",
        }
    ],
    "estimates": [
        {"schema_version": 1, "name": "a_per_volt_row", "unit": "1/V", "description": ""}
    ],
}


@pytest.mark.parametrize(("model", "wire"), [(Run, RUN_V1), (MethodSpec, METHOD_SPEC_V1)])
def test_v1_wire_shape_is_frozen(model, wire):
    obj = model.model_validate(wire)
    assert obj.schema_version == 1
    assert obj.model_dump(mode="json") == wire
