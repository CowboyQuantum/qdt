"""Injection–recovery for the plane fit (Step 5 L0; the L2-1 oracle of BENCH.md).

Truth is injected two ways: a synthetic plane with chosen coefficients under Gaussian noise, and a plane
produced through the real sweep path, where a simulated sense channel reads a weighted sum of two
simulated level channels (the L0 model of DC + pulse summed through a passive network). The method must
recover the coefficients within their standard errors, draw iso-lines that lie on the plane, refuse a
map with no plane, and tolerate missing points.
"""

import math
from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_analysis.plane import NAME, Plane, fit, fit_plane, isoline
from qdt_lab.experiment import Executor, compile_sweep
from qdt_lab.simulated import SimulatedLevelSense, SimulatedLevelSource
from qdt_lab.stream import assemble
from qdt_schemas.activity import SensedLevel, SweepAxis, SweepDefinition
from qdt_schemas.data import Dataset, DataVariable, Dimension, LinearCoordinate, SourceDescriptor
from qdt_schemas.envelope import MeasurementRecord, PayloadRef
from qdt_schemas.payload_hdf5 import Payload
from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig


def record_for(dataset_id: str) -> MeasurementRecord:
    t = datetime(2026, 10, 14, tzinfo=UTC)
    return MeasurementRecord(
        record_id="ef" * 16,
        device_id="dev",
        stand_id="stand",
        stand_sha256="0" * 64,
        definition_name="plane",
        definition_sha256="0" * 64,
        plan_id=dataset_id,
        source=SourceDescriptor(kind="synthetic"),
        started_at=t,
        finished_at=t,
        outcome="completed",
        payload=PayloadRef(type="qdt-hdf5-v1", path="x.h5", sha256="0" * 64, size_bytes=0),
    )


def map_payload(
    values: np.ndarray, x: tuple[float, float], y: tuple[float, float], dims=("V_dc", "V_p")
) -> Payload:
    *lead, n0, n1 = values.shape
    ds = Dataset(
        dataset_id="map",
        name="map",
        dims=(
            *(Dimension(name=f"lead{k}", size=n) for k, n in enumerate(lead)),
            Dimension(name=dims[0], size=n0),
            Dimension(name=dims[1], size=n1),
        ),
        coords=(
            LinearCoordinate(name=dims[0], dim=dims[0], unit="V", start=x[0], stop=x[1], num=n0),
            LinearCoordinate(name=dims[1], dim=dims[1], unit="V", start=y[0], stop=y[1], num=n1),
        ),
        data_vars=(
            DataVariable(
                name="V_out",
                dims=(*(f"lead{k}" for k in range(len(lead))), *dims),
                unit="V",
                dtype="float64",
            ),
        ),
        source=SourceDescriptor(kind="synthetic"),
        created_at=datetime(2026, 10, 14, tzinfo=UTC),
    )
    return Payload(ds, {"V_out": values}, (), None, None)


X, Y = (-1.0, 1.0), (-0.25, 0.25)
C_DC, C_P, OFFSET = 0.396, 0.81, 3e-3  # Probe 03's combiner: DC division 2.525, pulse side 0.81


def synthetic(n_x=16, n_y=32, noise=1e-3, seed=5):
    x = np.linspace(*X, n_x)
    y = np.linspace(*Y, n_y)
    truth = C_DC * x[:, None] + C_P * y[None, :] + OFFSET
    rng = np.random.default_rng(seed)
    return map_payload(truth + noise * rng.standard_normal(truth.shape), X, Y), truth


def on_plane(x, y):
    return C_DC * x + C_P * y + OFFSET


def test_recovers_an_injected_plane_within_its_standard_errors():
    payload, truth = synthetic()
    result, output = fit_plane(record_for("map"), payload)
    assert result.status == "ok", result.message
    for name, value in [("slope_row", C_DC), ("slope_col", C_P), ("offset", OFFSET)]:
        e = result.estimate(name)
        assert e.stderr is not None and abs(e.value - value) < 4 * e.stderr, (name, e)
    assert result.estimate("isoline_slope").value == pytest.approx(-C_DC / C_P, rel=0.02)
    assert result.estimate("residual_rms").value == pytest.approx(1e-3, rel=0.2)
    assert result.estimate("r2").value > 0.99
    assert result.estimate("slope_row").unit == "V/V" and result.estimate("offset").unit == "V"
    assert result.estimate("isoline_slope").unit == "V/V"
    assert output is not None and output.dataset.source.kind == "analysis"
    np.testing.assert_allclose(output.arrays["fit"], truth, atol=1e-3)
    assert np.nanstd(output.arrays["residual"]) == pytest.approx(1e-3, rel=0.2)
    assert result.record_id == "ef" * 16 and result.method.name == NAME
    assert result.method.parameters == {"variable": "", "n_isolines": 8, "min_r2": 0.5}


def test_isolines_lie_on_the_plane_and_span_the_window():
    payload, _truth = synthetic(noise=0.0)
    result, _output = fit_plane(record_for("map"), payload)
    lines = [a for a in result.annotations if a.kind == "line"]
    assert len(lines) == 8 and result.attrs["n_isolines"] == 8
    for a in lines:
        payload.dataset.check_annotation(a)
        assert a.coords == ("V_dc", "V_p")
        level = a.attrs["level"]
        for x, y in a.points:
            assert on_plane(x, y) == pytest.approx(level, abs=1e-9)
            on_edge = x in X or y in Y or math.isclose(x, X[0]) or math.isclose(x, X[1])
            assert on_edge or math.isclose(y, Y[0]) or math.isclose(y, Y[1])
        (x0, y0), (x1, y1) = a.points
        assert (y1 - y0) / (x1 - x0) == pytest.approx(-C_DC / C_P)
        assert a.label.endswith(" V")
    levels = [a.attrs["level"] for a in lines]
    assert levels == sorted(levels)
    assert on_plane(X[0], Y[0]) < levels[0] and levels[-1] < on_plane(X[1], Y[1])


def test_n_isolines_is_honoured_including_none():
    payload, _ = synthetic(noise=0.0)
    assert len(fit_plane(record_for("map"), payload, n_isolines=3).result.annotations) == 3
    result, _ = fit_plane(record_for("map"), payload, n_isolines=0)
    assert result.status == "ok" and result.annotations == ()


def test_isoline_clipping_covers_every_orientation():
    window = ((0.0, 1.0), (0.0, 1.0))
    diagonal = Plane(1.0, 1.0, 0.0, (0, 0, 0), np.zeros((3, 3)), 1.0, 0.0, 4)
    assert isoline(diagonal, 1.0, *window) in [((0.0, 1.0), (1.0, 0.0)), ((1.0, 0.0), (0.0, 1.0))]
    assert isoline(diagonal, 0.5, *window) in [((0.0, 0.5), (0.5, 0.0)), ((0.5, 0.0), (0.0, 0.5))]
    assert isoline(diagonal, 3.0, *window) is None  # misses the window
    assert isoline(diagonal, 0.0, *window) is None  # touches one corner only
    rows_only = Plane(2.0, 0.0, 0.0, (0, 0, 0), np.zeros((3, 3)), 1.0, 0.0, 4)
    assert isoline(rows_only, 1.0, *window) in [((0.5, 0.0), (0.5, 1.0)), ((0.5, 1.0), (0.5, 0.0))]
    cols_only = Plane(0.0, 2.0, 0.0, (0, 0, 0), np.zeros((3, 3)), 1.0, 0.0, 4)
    assert isoline(cols_only, 1.0, *window) in [((0.0, 0.5), (1.0, 0.5)), ((1.0, 0.5), (0.0, 0.5))]
    flat = Plane(0.0, 0.0, 1.0, (0, 0, 0), np.zeros((3, 3)), math.nan, 0.0, 4)
    assert isoline(flat, 1.0, *window) is None


def test_a_plane_along_the_columns_only_has_no_isoline_slope():
    x, y = np.linspace(*X, 8), np.linspace(*Y, 8)
    payload = map_payload(np.broadcast_to(C_P * y[None, :], (8, 8)).copy(), X, Y)
    result, _ = fit_plane(record_for("map"), payload)
    assert result.status == "ok"
    assert result.estimate("slope_col").value == pytest.approx(C_P)
    assert abs(result.estimate("slope_row").value) < 1e-12
    assert result.estimate("isoline_slope").value == pytest.approx(0.0, abs=1e-12)
    payload = map_payload(np.broadcast_to(C_DC * x[:, None], (8, 8)).copy(), X, Y)
    result, _ = fit_plane(record_for("map"), payload)
    assert result.status == "ok" and len(result.annotations) == 8
    with pytest.raises(KeyError):
        result.estimate("isoline_slope")


def stand() -> StandConfig:
    return StandConfig(
        stand_id="sum",
        instruments=(
            InstrumentConfig(id="dac", backend="simulated", capabilities=("level_source",)),
            InstrumentConfig(id="meter", backend="simulated", capabilities=("level_sense",)),
        ),
        channels=(
            ChannelMap(logical="V_dc", instrument="dac", channel="dc", quantity="voltage"),
            ChannelMap(logical="V_p", instrument="dac", channel="p", quantity="voltage"),
            ChannelMap(logical="V_out", instrument="meter", channel="out", quantity="voltage"),
        ),
    )


def test_recovers_the_plane_of_two_summed_levels_through_a_sweep():
    """The L0 model of L2-1: a DC level stepped outside, a second level stepped inside, their weighted
    sum sensed at every point, through compile → execute → assemble."""
    definition = SweepDefinition(
        name="dc + pulse plane",
        axes=(
            SweepAxis(name="V_dc", channel="V_dc", start=X[0], stop=X[1], num=16),
            SweepAxis(name="V_p", channel="V_p", start=Y[0], stop=Y[1], num=32),
        ),
        sensed=(SensedLevel(name="V_out", channel="V_out"),),
    )
    dac = SimulatedLevelSource()
    meter = SimulatedLevelSense(
        follow=dac, load=lambda _channel, _base: on_plane(dac.get("dc"), dac.get("p")), noise=1e-3
    )
    plan = compile_sweep(definition, stand())
    data = assemble(plan.dataset, Executor(plan, {"dac": dac, "meter": meter}).run().frames())
    payload = Payload(plan.dataset, {"V_out": data["V_out"].values}, (), plan, None)
    result, output = fit_plane(record_for(plan.dataset.dataset_id), payload)
    assert result.status == "ok", result.message
    assert result.estimate("slope_row").value == pytest.approx(C_DC, abs=2e-3)
    assert result.estimate("slope_col").value == pytest.approx(C_P, abs=5e-3)
    assert result.estimate("offset").value == pytest.approx(OFFSET, abs=1e-3)
    assert all(a.coords == ("V_dc", "V_p") for a in result.annotations)
    assert output is not None and output.arrays["fit"].shape == (16, 32)
    for a in result.annotations:
        plan.dataset.check_annotation(a)


def test_leading_dims_are_averaged_and_missing_points_skipped():
    payload, _truth = synthetic(noise=2e-3)
    stacked = np.stack([payload.arrays["V_out"], payload.arrays["V_out"] + 1e-3])
    stacked[0, 3, 5] = np.nan
    stacked[:, 10, :4] = np.nan
    result, output = fit_plane(record_for("map"), map_payload(stacked, X, Y))
    assert result.status == "ok", result.message
    assert result.estimate("offset").value == pytest.approx(OFFSET + 0.5e-3, abs=1e-3)
    # a point missing in one repeat keeps the other's value; a point missing in both is skipped
    assert result.attrs["n_points"] == 16 * 32 - 4
    assert np.isnan(output.arrays["residual"]).sum() == 4
    assert np.isfinite(output.arrays["fit"]).all()


def test_a_noise_map_fails_instead_of_inventing_a_plane():
    rng = np.random.default_rng(1)
    result, output = fit_plane(record_for("map"), map_payload(rng.normal(0, 1, (16, 32)), X, Y))
    assert result.status == "failed" and not result.estimates and not result.annotations
    assert "explains" in result.message and result.attrs["r2"] < 0.1
    assert output is not None  # the residual map is still worth looking at


def test_a_constant_map_fails():
    result, output = fit_plane(record_for("map"), map_payload(np.full((8, 8), 0.3), X, Y))
    assert result.status == "failed" and "constant" in result.message and output is None


def test_too_small_or_too_sparse_maps_fail():
    result, _ = fit_plane(record_for("map"), map_payload(np.zeros((1, 8)), X, Y))
    assert result.status == "failed" and "smaller" in result.message
    sparse = np.full((8, 8), np.nan)
    sparse[0, 0] = sparse[7, 7] = sparse[0, 7] = sparse[7, 0] = 1.0
    result, _ = fit_plane(record_for("map"), map_payload(sparse, X, Y))
    assert result.status == "failed" and "finite" in result.message


def test_fit_rejects_a_degenerate_design():
    x, y = np.linspace(*X, 8), np.linspace(*Y, 8)
    with pytest.raises(ValueError, match="four"):
        fit(np.full((8, 8), np.nan), x, y)
    with pytest.raises(ValueError, match="span"):
        fit(np.zeros((1, 8)), x[:1], y)


def test_refuses_a_payload_from_another_record():
    with pytest.raises(ValueError, match="payload for"):
        fit_plane(record_for("other"), map_payload(np.zeros((8, 8)), X, Y))
