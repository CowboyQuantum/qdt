"""Injection–recovery on a synthetic map (Step 4 L0): lines put in come back out, with provenance."""

import math
from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_analysis import DEFAULTS, MODEL_NAME, charge_transitions, detect, recovery
from qdt_analysis.recovery import rasterize, score
from qdt_schemas.data import Dataset, DataVariable, Dimension, LinearCoordinate, SourceDescriptor
from qdt_schemas.modeling import ScenarioRef

T0 = datetime(2026, 10, 13, tzinfo=UTC)
SCENARIO = ScenarioRef(kind="synthetic", name="injected_lines", seed=5, parameters={"n": 96})

# Two families of straight steps: a·x + b·y = c_k, like the addition lines of two dots.
FAMILIES = ((0.3, 1.0, (-0.3, -0.1, 0.1, 0.3)), (1.0, 0.25, (-0.25, 0.0, 0.25)))


def synthetic(n_rows: int = 96, n_cols: int = 128, noise: float = 0.01, seed: int = 5):
    """(Dataset, arrays, truth mask) with the FAMILIES lines injected as sigmoid steps."""
    ds = Dataset(
        dataset_id="synthetic-lines",
        name="injected lines",
        dims=(Dimension(name="gate_R", size=n_rows), Dimension(name="gate_L", size=n_cols)),
        coords=(
            LinearCoordinate(name="V_R", dim="gate_R", unit="V", start=-0.5, stop=0.5, num=n_rows),
            LinearCoordinate(name="V_L", dim="gate_L", unit="V", start=-0.5, stop=0.5, num=n_cols),
        ),
        data_vars=(DataVariable(name="I", dims=("gate_R", "gate_L"), unit="A", dtype="float64"),),
        source=SourceDescriptor(kind="synthetic"),
        created_at=T0,
    )
    y = np.linspace(-0.5, 0.5, n_rows)[:, None]
    x = np.linspace(-0.5, 0.5, n_cols)[None, :]
    z = np.zeros((n_rows, n_cols))
    truth = np.zeros((n_rows, n_cols), dtype=bool)
    width = 0.004
    for a, b, cs in FAMILIES:
        for c in cs:
            d = (a * x + b * y - c) / math.hypot(a, b)  # signed perpendicular distance
            z += 0.1 / (1 + np.exp(-d / width))
            px = 1 / n_cols  # pixel pitch in data units
            truth |= np.abs(d) <= 0.5 * px
    rng = np.random.default_rng(seed)
    z = z + noise * rng.standard_normal(z.shape)
    return ds, {"I": z}, truth


def test_injected_lines_are_recovered():
    ds, arrays, truth = synthetic()
    result = charge_transitions(ds, arrays, SCENARIO, created_at=T0)
    r = recovery(result, ds, arrays, truth, tolerance=1.5)
    assert r.precision > 0.95 and r.recall > 0.95, r
    assert result.summary["n_families"] == 2
    assert result.summary["n_lines"] == sum(len(cs) for _, _, cs in FAMILIES)


def test_family_orientations_match_the_injected_normals():
    ds, arrays, _ = synthetic()
    result = charge_transitions(ds, arrays, SCENARIO)
    got = sorted(
        result.summary[f"family_{k}_orientation_deg"] for k in range(result.summary["n_families"])
    )
    # gradient orientation of a·x + b·y = c in (col, row) pixel space, with the map's aspect ratio
    want = sorted(math.degrees(math.atan2(b * 128 / 96, a)) % 180 for a, b, _ in FAMILIES)
    assert np.allclose(got, want, atol=3), (got, want)


def test_result_carries_dual_provenance_and_annotations_on_the_dataset():
    ds, arrays, _ = synthetic()
    result = charge_transitions(ds, arrays, SCENARIO, sigma=1.5, created_at=T0)
    assert result.measurement.dataset_id == ds.dataset_id
    assert result.measurement.variable == "I"
    assert result.measurement.record_id is None
    assert result.scenario == SCENARIO
    assert result.model.name == MODEL_NAME
    assert result.model.parameters == {**DEFAULTS, "sigma": 1.5}
    assert result.created_at == T0
    for a in result.annotations:
        ds.check_annotation(a)  # coordinates named V_R / V_L exist on the Dataset
        assert a.kind == "line" and a.coords == ("V_R", "V_L")
        assert all(-0.5 <= v <= 0.5 for p in a.points for v in p)
        assert {"family", "angle_deg", "strength", "n_pixels"} <= set(a.attrs)
    assert len({a.annotation_id for a in result.annotations}) == len(result.annotations)


def test_unknown_parameter_is_refused():
    ds, arrays, _ = synthetic()
    with pytest.raises(TypeError, match="unknown detector parameters"):
        charge_transitions(ds, arrays, SCENARIO, smoothing=2)


def test_noise_alone_gives_no_lines():
    ds, arrays, _ = synthetic(noise=0.0)
    rng = np.random.default_rng(1)
    flat = {"I": 0.01 * rng.standard_normal(arrays["I"].shape)}
    result = charge_transitions(ds, flat, SCENARIO)
    assert result.summary["n_lines"] == 0


def test_repeated_maps_are_averaged_over_the_leading_dimension():
    ds, arrays, truth = synthetic(noise=0.03)
    stacked = Dataset.model_validate(
        ds.model_dump()
        | {
            "dims": [*ds.model_dump()["dims"], {"name": "repeat", "size": 4}],
            "data_vars": [{"name": "I", "dims": ("repeat", "gate_R", "gate_L"), "unit": "A", "dtype": "float64"}],
        }
    )
    rng = np.random.default_rng(2)
    stack = arrays["I"][None] + 0.03 * rng.standard_normal((4, *arrays["I"].shape))
    result = charge_transitions(stacked, {"I": stack}, SCENARIO)
    r = recovery(result, stacked, {"I": stack}, truth)
    assert r.precision > 0.9 and r.recall > 0.9, r


def test_nan_cells_do_not_break_detection():
    ds, arrays, truth = synthetic()
    z = arrays["I"].copy()
    z[-10:, :] = np.nan  # an aborted run leaves the last rows unwritten
    result = charge_transitions(ds, {"I": z}, SCENARIO)
    truth[-10:] = False
    r = recovery(result, ds, {"I": z}, truth)
    assert r.recall > 0.85 and r.precision > 0.85, r


def test_detect_validates_its_input():
    with pytest.raises(ValueError, match="2-D"):
        detect(np.zeros(5))
    with pytest.raises(ValueError, match="finite"):
        detect(np.full((4, 4), np.nan))


def test_score_is_symmetric_in_the_obvious_cases():
    a = rasterize(np.array([[[0.0, 0.0], [9.0, 9.0]]]), (10, 10))
    assert score(a, a, 0.0) == (1.0, 1.0, int(a.sum()), int(a.sum()))
    empty = np.zeros((10, 10), dtype=bool)
    assert score(empty, a, 1.0)[:2] == (0.0, 0.0)
    assert score(a, empty, 1.0)[:2] == (0.0, 0.0)
