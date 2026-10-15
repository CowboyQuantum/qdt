"""Injection–recovery for the single exponential (Step 5 L0; the L2-3 oracle of BENCH.md).

Truth is injected three ways: a synthetic decay after a sharp edge, a synthetic low-pass approach after a
slow onset (the combiner of Probe 03), and the real combiner step record Probe 03 captured on the scope
(`bench/fixtures/probe03/step_qdac.npz`, τ = 7.9 ms by the probe's own 10–90 % fit). The method must
find the edge, recover τ, amplitude and offset within their standard errors, place its markers on the
time axis, refuse a map and a trace with no edge, and tolerate missing samples.
"""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from qdt_analysis.exponential import NAME, detect_edge, fit, fit_exponential
from qdt_lab.simulated import SimulatedWaveformSense
from qdt_lab.stream import assemble
from qdt_schemas.data import Dataset, DataVariable, Dimension, LinearCoordinate, SourceDescriptor
from qdt_schemas.envelope import MeasurementRecord, PayloadRef
from qdt_schemas.payload_hdf5 import Payload

STEP_QDAC = Path(__file__).resolve().parents[3] / "bench/fixtures/probe03/step_qdac.npz"


def record_for(dataset_id: str) -> MeasurementRecord:
    t = datetime(2026, 10, 15, tzinfo=UTC)
    return MeasurementRecord(
        record_id="ab" * 16,
        device_id="dev",
        stand_id="stand",
        stand_sha256="0" * 64,
        definition_name="step",
        definition_sha256="0" * 64,
        plan_id=dataset_id,
        source=SourceDescriptor(kind="synthetic"),
        started_at=t,
        finished_at=t,
        outcome="completed",
        payload=PayloadRef(type="qdt-hdf5-v1", path="x.h5", sha256="0" * 64, size_bytes=0),
    )


def trace_payload(values: np.ndarray, t: tuple[float, float], unit="V", t_unit="s") -> Payload:
    """A (record..., t) trace Dataset, as a `WaveformSense` fills it: leading dims uncoordinated."""
    *lead, n = values.shape
    ds = Dataset(
        dataset_id="trace",
        name="trace",
        dims=(
            *(Dimension(name=f"record{k}", size=m) for k, m in enumerate(lead)),
            Dimension(name="t", size=n),
        ),
        coords=(LinearCoordinate(name="t", dim="t", unit=t_unit, start=t[0], stop=t[1], num=n),),
        data_vars=(
            DataVariable(
                name="voltage",
                dims=(*(f"record{k}" for k in range(len(lead))), "t"),
                unit=unit,
                dtype="float64",
            ),
        ),
        source=SourceDescriptor(kind="synthetic"),
        created_at=datetime(2026, 10, 15, tzinfo=UTC),
    )
    return Payload(ds, {"voltage": values}, (), None, None)


# a decay after a sharp edge at t = 0, in a −1 … 9 µs record
T_DECAY, TAU, A, C = (-1e-6, 9e-6), 2e-6, 0.2, 0.01
# the combiner's low-pass approach (Probe 03): onset at −2.7 ms, τ = 7.9 ms, 0.385 V plateau
T_APPROACH, T0, TAU_RC, PLATEAU = (-0.02, 0.18), -2.7e-3, 7.9e-3, 0.385


def decay(n=1000, noise=1e-3, seed=0):
    t = np.linspace(*T_DECAY, n)
    truth = np.where(t >= 0, C + A * np.exp(-t / TAU), 0.0)
    rng = np.random.default_rng(seed)
    return t, truth, trace_payload(truth + noise * rng.standard_normal(n), T_DECAY)


def approach(n=2000, noise=1.4e-3, seed=1):
    t = np.linspace(*T_APPROACH, n)
    truth = np.where(t >= T0, PLATEAU * (1 - np.exp(-(t - T0) / TAU_RC)), 0.0)
    rng = np.random.default_rng(seed)
    return t, truth, trace_payload(truth + noise * rng.standard_normal(n), T_APPROACH)


def test_recovers_an_injected_decay_within_its_standard_errors():
    t, truth, payload = decay()
    result, output = fit_exponential(record_for("trace"), payload)
    assert result.status == "ok", result.message
    t_start = result.attrs["t_start"]
    assert 0 <= t_start < 3 * (t[1] - t[0])  # the window starts just after the edge
    for name, value in [("tau", TAU), ("amplitude", A * np.exp(-t_start / TAU)), ("offset", C)]:
        e = result.estimate(name)
        assert e.stderr is not None and abs(e.value - value) < 4 * e.stderr, (name, e)
    assert result.estimate("tau").unit == "s" and result.estimate("amplitude").unit == "V"
    assert result.estimate("residual_rms").value == pytest.approx(1e-3, rel=0.2)
    assert result.estimate("r2").value > 0.99
    assert result.record_id == "ab" * 16 and result.method.name == NAME
    assert result.method.parameters == {"variable": "", "skip": 0.0, "span": 0.0, "min_r2": 0.5}
    assert result.attrs["variable"] == "voltage" and result.attrs["t_stop"] == t[-1]
    # the fitted curve is the output, over the record's time axis, NaN before the window
    assert output is not None and output.dataset.source.kind == "analysis"
    window = t >= t_start
    np.testing.assert_allclose(output.arrays["fit"][window], truth[window], atol=2e-3)
    assert np.isnan(output.arrays["fit"][~window]).all()
    assert np.nanstd(output.arrays["residual"]) == pytest.approx(1e-3, rel=0.2)
    assert [c.name for c in output.dataset.coords] == ["t"]


def test_markers_sit_on_the_time_axis_at_the_edge_and_one_tau_later():
    _t, _truth, payload = decay()
    result, output = fit_exponential(record_for("trace"), payload)
    markers = {a.label.split(" ")[0]: a for a in result.annotations}
    assert set(markers) == {"edge", "τ"} and all(a.kind == "marker" for a in markers.values())
    for a in result.annotations:
        payload.dataset.check_annotation(a)
        assert a.coords == ("t",) and len(a.points) == 1 and len(a.points[0]) == 1
    edge, tau = markers["edge"].points[0][0], markers["τ"].points[0][0]
    assert edge == result.attrs["t_start"]
    assert tau - edge == pytest.approx(result.estimate("tau").value)
    assert markers["τ"].label.endswith(" s")
    assert markers["τ"].attrs["tau"] == pytest.approx(tau - edge)
    assert all(a.dataset_id == output.dataset.dataset_id for a in output.annotations)


def test_recovers_a_low_pass_approach_after_a_slow_onset():
    """Probe 03's combiner: the edge is placed after the onset, never before, and τ comes back."""
    _t, _truth, payload = approach()
    result, _ = fit_exponential(record_for("trace"), payload)
    assert result.status == "ok", result.message
    assert T0 <= result.attrs["t_start"] < T0 + TAU_RC / 2
    assert result.estimate("tau").value == pytest.approx(TAU_RC, rel=0.03)
    assert result.estimate("amplitude").value < 0
    assert result.estimate("offset").value == pytest.approx(PLATEAU, abs=1e-3)


def test_the_first_edge_wins_and_span_clips_the_window():
    """A 30 µs pulse whose plateau droops: the rising edge is the edge even though the falling one is
    as steep, and `span` keeps the falling edge out of the fit."""
    t = np.linspace(-15e-6, 45e-6, 4000)
    on = (t >= 0) & (t < 30e-6)
    truth = np.where(on, 0.12 + 0.04 * np.exp(-t / 5e-6), 0.0)
    payload = trace_payload(
        truth + 1e-4 * np.random.default_rng(2).standard_normal(t.size), (-15e-6, 45e-6)
    )
    whole, _ = fit_exponential(record_for("trace"), payload)
    assert 0 <= whole.attrs["t_start"] < 1e-7
    clipped, output = fit_exponential(record_for("trace"), payload, span=28e-6)
    assert clipped.status == "ok", clipped.message
    assert clipped.attrs["t_stop"] <= 28e-6 + 1e-7
    assert clipped.estimate("tau").value == pytest.approx(5e-6, rel=0.02)
    assert clipped.estimate("offset").value == pytest.approx(0.12, abs=5e-4)
    assert clipped.method.parameters["span"] == 28e-6
    assert np.isnan(output.arrays["fit"][t > 28.1e-6]).all()


def test_skip_moves_the_window_start_and_amplitude_is_referenced_there():
    t, _truth, payload = decay(noise=1e-4)
    result, _ = fit_exponential(record_for("trace"), payload, skip=TAU)
    assert result.status == "ok", result.message
    assert result.attrs["t_start"] == pytest.approx(TAU, abs=2 * (t[1] - t[0]))
    assert result.estimate("amplitude").value == pytest.approx(A / np.e, rel=0.02)
    assert result.estimate("tau").value == pytest.approx(TAU, rel=0.02)
    assert result.method.parameters["skip"] == TAU


def test_records_are_averaged_and_missing_samples_skipped():
    _t, _truth, payload = decay(noise=2e-3)
    stacked = np.stack([payload.arrays["voltage"] + k * 1e-3 for k in range(4)])
    stacked[0, 500] = np.nan  # missing in one record: the others' mean stands
    stacked[:, 600:603] = np.nan  # missing in every record: skipped
    result, output = fit_exponential(record_for("trace"), trace_payload(stacked, T_DECAY))
    assert result.status == "ok", result.message
    assert result.estimate("offset").value == pytest.approx(C + 1.5e-3, abs=1e-3)
    window = np.isfinite(output.arrays["fit"])
    assert result.attrs["n_points"] == int(window.sum()) - 3
    assert (
        np.isnan(output.arrays["residual"][600:603]).all()
        and np.isfinite(output.arrays["fit"][600:603]).all()
    )


@pytest.mark.skipif(not STEP_QDAC.exists(), reason="Probe 03 fixture not checked out")
def test_the_real_combiner_step_recovers_probe_03s_time_constant():
    """The scope record of a 0 → 1 V QDAC step through the combiner board (Probe 03, 2026-10-14):
    τ = 7.9 ms by the probe's 10–90 % log-linear fit, division 2.589 into the scope's 1 MΩ."""
    d = np.load(STEP_QDAC)
    t, y = d["t"], d["y"]
    result, _ = fit_exponential(record_for("trace"), trace_payload(y, (float(t[0]), float(t[-1]))))
    assert result.status == "ok", result.message
    assert result.estimate("tau").value == pytest.approx(7.9e-3, rel=0.05)
    assert result.estimate("tau").stderr < 0.05e-3
    assert result.estimate("offset").value == pytest.approx(1 / 2.589 - 2.1e-3, abs=3e-3)
    assert result.estimate("amplitude").value < 0
    assert result.estimate("r2").value > 0.99
    assert result.estimate("residual_rms").value < 2e-3  # the scope's noise floor on that range


def test_a_waveform_sense_record_is_a_trace():
    """What a `WaveformSense` fills, (record, t) through `assemble`, is what the method takes; the
    simulated ring-down is not an exponential, so the verdict may be either, but it is a verdict."""
    dataset = Dataset(
        dataset_id="scope",
        name="scope",
        dims=(Dimension(name="record", size=4), Dimension(name="t", size=256)),
        coords=(LinearCoordinate(name="t", dim="t", unit="s", start=0.0, stop=1e-6, num=256),),
        data_vars=(DataVariable(name="voltage", dims=("record", "t"), unit="V", dtype="float64"),),
        source=SourceDescriptor(kind="simulation"),
        created_at=datetime(2026, 10, 15, tzinfo=UTC),
    )
    source = SimulatedWaveformSense(noise=0.0).arm("ch1", dataset, "voltage")
    data = assemble(dataset, source.frames())
    payload = Payload(dataset, {"voltage": data["voltage"].values}, (), None, None)
    result, _ = fit_exponential(record_for("scope"), payload)
    assert result.status in ("ok", "failed") and result.attrs["variable"] == "voltage"
    for a in result.annotations:
        dataset.check_annotation(a)


def test_a_noise_trace_fails_instead_of_inventing_an_exponential():
    rng = np.random.default_rng(3)
    result, output = fit_exponential(
        record_for("trace"), trace_payload(rng.normal(0, 1, 1000), T_DECAY)
    )
    assert result.status == "failed" and not result.estimates and not result.annotations
    assert "explains" in result.message and result.attrs["r2"] < 0.5
    assert output is not None  # the residual is still worth looking at


def test_a_flat_trace_or_a_late_edge_fails():
    result, output = fit_exponential(record_for("trace"), trace_payload(np.full(100, 0.3), T_DECAY))
    assert result.status == "failed" and "slope" in result.message and output is None
    late = np.zeros(100)
    late[-2:] = 1.0
    result, output = fit_exponential(record_for("trace"), trace_payload(late, T_DECAY))
    assert result.status == "failed" and "four points" in result.message and output is None
    assert result.attrs["t_edge"] == pytest.approx(np.linspace(*T_DECAY, 100)[-3], abs=1e-7)


def test_low_min_r2_admits_what_the_default_refuses():
    t = np.linspace(*T_DECAY, 1000)
    rng = np.random.default_rng(4)
    weak = np.where(t >= 0, 0.02 * np.exp(-t / TAU), 0.0) + 0.02 * rng.standard_normal(t.size)
    strict, _ = fit_exponential(record_for("trace"), trace_payload(weak, T_DECAY))
    lenient, _ = fit_exponential(record_for("trace"), trace_payload(weak, T_DECAY), min_r2=0.0)
    assert strict.status == "failed" and lenient.status == "ok"
    assert lenient.method.parameters["min_r2"] == 0.0


def test_refuses_a_map_another_record_and_negative_windows():
    t_coord = LinearCoordinate(name="t", dim="t", unit="s", start=0.0, stop=1.0, num=8)
    g_coord = LinearCoordinate(name="g", dim="g", unit="V", start=0.0, stop=1.0, num=8)
    ds = Dataset(
        dataset_id="map",
        name="map",
        dims=(Dimension(name="g", size=8), Dimension(name="t", size=8)),
        coords=(g_coord, t_coord),
        data_vars=(DataVariable(name="voltage", dims=("g", "t"), unit="V", dtype="float64"),),
        source=SourceDescriptor(kind="synthetic"),
        created_at=datetime(2026, 10, 15, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="trace"):
        fit_exponential(
            record_for("map"), Payload(ds, {"voltage": np.zeros((8, 8))}, (), None, None)
        )
    _t, _truth, payload = decay()
    with pytest.raises(ValueError, match="payload for"):
        fit_exponential(record_for("other"), payload)
    with pytest.raises(ValueError, match="no data variable 'current'"):
        fit_exponential(record_for("trace"), payload, variable="current")
    with pytest.raises(ValueError, match="negative"):
        fit_exponential(record_for("trace"), payload, skip=-1.0)


def test_detect_edge_and_fit_directly():
    t, truth, _ = decay(noise=0.0)
    assert detect_edge(truth) == int(np.argmax(t >= 0))
    with pytest.raises(ValueError, match="slope"):
        detect_edge(np.ones(50))
    with pytest.raises(ValueError, match="finite"):
        detect_edge(np.full(50, np.nan))
    with pytest.raises(ValueError, match="four"):
        fit(t[:3], truth[:3])
    with pytest.raises(ValueError, match="constant"):
        fit(t[:10], np.ones(10))
    e = fit(t[t >= 0], truth[t >= 0])
    assert e.tau == pytest.approx(TAU, rel=1e-6) and e.offset == pytest.approx(C, abs=1e-9)
    assert e.r2 == pytest.approx(1.0) and e.n_points == int((t >= 0).sum())
