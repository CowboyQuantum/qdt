"""Injection–recovery for the sensor peak and its wing (ADR 0062).

Truth is injected two ways: a synthetic sech² peak with a neighbour and noise, and the simulated
device's own sensor current against its sensor gate at linear-response bias (Phantom's noise-free
`Device.at`, whose truth gives the peak, its width, its wing and its sensitivity). The method must find
the peak nearest the target, fit
its width within its standard error, place the wing at atanh(1/√3) widths on the side asked, mark both
on the gate coordinate, refuse a map and a flat trace, and tolerate missing samples.
"""

import math
from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_analysis.sensor_peak import (
    NAME,
    SLOPE_FACTOR,
    WING_WIDTHS,
    find_peak,
    fit_peak,
    fit_sensor_peak,
)
from qdt_schemas.data import Dataset, DataVariable, Dimension, LinearCoordinate, SourceDescriptor
from qdt_schemas.envelope import MeasurementRecord, PayloadRef
from qdt_schemas.payload_hdf5 import Payload
from qdt_sim.scenarios import load_device, programmed


def record_for(dataset_id: str) -> MeasurementRecord:
    t = datetime(2026, 10, 16, tzinfo=UTC)
    return MeasurementRecord(
        record_id="cd" * 16,
        device_id="dev",
        stand_id="stand",
        stand_sha256="0" * 64,
        definition_name="sensor peak",
        definition_sha256="0" * 64,
        plan_id=dataset_id,
        source=SourceDescriptor(kind="synthetic"),
        started_at=t,
        finished_at=t,
        outcome="completed",
        payload=PayloadRef(type="qdt-hdf5-v1", path="x.h5", sha256="0" * 64, size_bytes=0),
    )


def trace_payload(values: np.ndarray, v: tuple[float, float], unit="A", v_unit="V") -> Payload:
    *lead, n = values.shape
    ds = Dataset(
        dataset_id="sg",
        name="sensor gate",
        dims=(*(Dimension(name=f"shot{k}", size=m) for k, m in enumerate(lead)), Dimension(name="SG", size=n)),
        coords=(LinearCoordinate(name="SG", dim="SG", unit=v_unit, start=v[0], stop=v[1], num=n),),
        data_vars=(
            DataVariable(
                name="I_sensor", dims=(*(f"shot{k}" for k in range(len(lead))), "SG"), unit=unit, dtype="float64"
            ),
        ),
        source=SourceDescriptor(kind="synthetic"),
        created_at=datetime(2026, 10, 16, tzinfo=UTC),
    )
    return Payload(ds, {"I_sensor": values}, (), None, None)


def sech2(v, peak, width, height, background):
    return background + height / np.cosh((v - peak) / width) ** 2


def test_recovers_a_synthetic_peak_its_width_and_the_wing_on_either_side():
    v = np.linspace(-0.2, 0.2, 401)
    truth = {"peak": -0.06, "width": 0.03, "height": 1e-9, "background": 0.05e-9}
    rng = np.random.default_rng(3)
    y = sech2(v, **truth) + sech2(v, -0.06 + 0.25, 0.03, 1e-9, 0.0) + rng.normal(0, 1e-11, v.size)
    i, window = find_peak(v, y, near=-0.05)
    assert abs(v[i] - truth["peak"]) < 0.003
    assert v[window][0] <= -0.12 and -0.0 < v[window][-1] < 0.12  # a few widths each way; stops before the neighbour
    peak = fit_peak(v[window], y[window], i - window.start)
    assert peak.peak == pytest.approx(truth["peak"], abs=3 * peak.stderr[0] + 1e-4)
    assert peak.width == pytest.approx(truth["width"], rel=0.07)  # the neighbour's tail biases the width a few percent
    assert peak.height == pytest.approx(truth["height"], rel=0.02)
    assert peak.r2 > 0.99
    assert peak.wing("above") == pytest.approx(truth["peak"] + WING_WIDTHS * truth["width"], abs=1e-3)
    assert peak.wing("below") == pytest.approx(truth["peak"] - WING_WIDTHS * truth["width"], abs=1e-3)
    assert peak.sensitivity == pytest.approx(SLOPE_FACTOR * truth["height"] / truth["width"], rel=0.03)
    # the slope at the wing really is the steepest point of the model
    fine = np.linspace(-0.2, 0.2, 40001)
    slope = np.abs(np.gradient(sech2(fine, **truth), fine))
    assert fine[np.argmax(slope)] == pytest.approx(truth["peak"] - WING_WIDTHS * truth["width"], abs=2e-4)


def test_the_method_marks_peak_and_wing_and_takes_the_peak_nearest_the_target():
    v = np.linspace(-0.3, 0.3, 601)
    y = sech2(v, -0.06, 0.04, 1e-9, 0.05e-9) + sech2(v, 0.19, 0.04, 0.9e-9, 0.0)
    y = np.stack([y, y * 1.01])  # two shots, averaged
    payload = trace_payload(y, (-0.3, 0.3))
    result, output = fit_sensor_peak(record_for("sg"), payload, near_v=0.1, near_centre=False)
    assert result.status == "ok", result.message
    assert result.estimate("peak_v").value == pytest.approx(0.19, abs=2e-3)  # nearest 0.1 V
    assert {a.label for a in result.annotations} == {"peak", "wing"}
    wing = next(a for a in result.annotations if a.label == "wing")
    assert wing.coords == ("SG",) and wing.points[0][0] == pytest.approx(0.19 + WING_WIDTHS * 0.04, abs=2e-3)
    assert result.estimate("wing_v").stderr is not None
    assert output is not None and set(output.arrays) == {"fit", "residual"}
    assert np.isfinite(output.arrays["fit"]).sum() < v.size  # NaN outside the window
    # the centre by default, and the lower wing on request
    below, _ = fit_sensor_peak(record_for("sg"), payload, side="below")
    assert below.estimate("peak_v").value == pytest.approx(-0.06, abs=2e-3)
    assert below.estimate("wing_v").value == pytest.approx(-0.06 - WING_WIDTHS * 0.04, abs=2e-3)
    assert result.method.name == NAME and result.method.parameters["side"] == "above"


def test_the_simulated_sensors_peak_has_the_devices_width_and_wing():
    """The default device's sensor at 10 µV, the other gates programmed, the gate stepped between the
    neighbouring peaks (no dot changes charge there): its truth's peak, width, height and wing.
    Positions within 1.5 % of the 0.16 V width, as 1 mV was of qdt-sim's 40 mV one."""
    device = load_device()
    truth = device.truth(near_v=programmed()["SG"], v_sd=10e-6).sensor
    lo, hi = truth.peak_v - truth.period_v / 2, truth.peak_v + truth.period_v / 2
    v = np.broadcast_to(np.array(device.programmed_point_v), (281, len(device.gate_names))).copy()
    v[:, device.gate_names.index("SG")] = np.linspace(lo, hi, 281)
    y = device.at(v, v_sd=10e-6).sensor_current_a
    result, _ = fit_sensor_peak(record_for("sg"), trace_payload(y, (lo, hi)))
    assert result.status == "ok", result.message
    near = 0.015 * truth.width_v
    height = truth.sensitivity_a_per_v * truth.width_v / SLOPE_FACTOR
    assert result.estimate("peak_v").value == pytest.approx(truth.peak_v, abs=near)
    assert result.estimate("width_v").value == pytest.approx(truth.width_v, rel=0.03)
    assert result.estimate("height_a").value == pytest.approx(height, rel=0.03)
    assert result.estimate("wing_v").value == pytest.approx(truth.wing_v, abs=near)
    sensitivity = result.estimate("sensitivity_a_per_v").value
    assert sensitivity == pytest.approx(truth.sensitivity_a_per_v, rel=0.03)


def test_refuses_a_map_a_flat_trace_and_a_bad_side_and_tolerates_missing_samples():
    v = np.linspace(-0.2, 0.2, 201)
    flat = trace_payload(np.full(v.size, 1e-10), (-0.2, 0.2))
    failed, _ = fit_sensor_peak(record_for("sg"), flat)
    assert failed.status == "failed" and "flat" in failed.message
    y = sech2(v, -0.06, 0.03, 1e-9, 0.05e-9)
    y[90:100] = np.nan
    ok, _ = fit_sensor_peak(record_for("sg"), trace_payload(y, (-0.2, 0.2)))
    assert ok.status == "ok" and ok.estimate("peak_v").value == pytest.approx(-0.06, abs=2e-3)
    with pytest.raises(ValueError, match="side"):
        fit_sensor_peak(record_for("sg"), trace_payload(y, (-0.2, 0.2)), side="left")
    ds = Dataset(
        dataset_id="map",
        name="map",
        dims=(Dimension(name="a", size=4), Dimension(name="b", size=4)),
        coords=(
            LinearCoordinate(name="a", dim="a", unit="V", start=0, stop=1, num=4),
            LinearCoordinate(name="b", dim="b", unit="V", start=0, stop=1, num=4),
        ),
        data_vars=(DataVariable(name="z", dims=("a", "b"), unit="A", dtype="float64"),),
        source=SourceDescriptor(kind="synthetic"),
        created_at=datetime(2026, 10, 16, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="trace"):
        fit_sensor_peak(record_for("map"), Payload(ds, {"z": np.zeros((4, 4))}, (), None, None))
    assert math.isclose(WING_WIDTHS, 0.6585, abs_tol=1e-4)
