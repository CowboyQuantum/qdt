"""Injection–recovery for Coulomb diamonds (Step 4 L0, ADR 0030).

Truth is injected two ways: a synthetic diamond train with a chosen period and charging energy, and the
simulated sensor SET through the real sweep path, whose model knows E_c, the period, the lever arm and
the edge lines (`DoubleDotModel.diamond_edges`). The estimator must recover each within stated
tolerances, must refuse a map with no diamonds, and its edges must lie on the true ones.
"""

import dataclasses
from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_analysis.diamonds import NAME, detect_diamonds
from qdt_analysis.recovery import rasterize, recovery, score
from qdt_lab.experiment import Executor, SimulatedEmitter, compile_sweep
from qdt_lab.stream import assemble
from qdt_schemas.data import Dataset, DataVariable, Dimension, LinearCoordinate, SourceDescriptor
from qdt_schemas.envelope import MeasurementRecord, PayloadRef
from qdt_schemas.payload_hdf5 import Payload
from qdt_sim.scenarios import DEVICE_ID, default_device, default_model, default_stand, diamonds

COLD_SENSOR = {"sensor_width_v": 0.01}
"""A diamond characterisation wants a cold sensor (kT_s ≈ 20 µeV); at the stability default (40 mV) the
thermal tails of neighbouring edges overlap near the apexes (ADR 0030)."""


def record_for(dataset_id: str) -> MeasurementRecord:
    t = datetime(2026, 10, 13, tzinfo=UTC)
    return MeasurementRecord(
        record_id="cd" * 16,
        device_id="dev",
        stand_id="stand",
        stand_sha256="0" * 64,
        definition_name="diamonds",
        definition_sha256="0" * 64,
        plan_id=dataset_id,
        source=SourceDescriptor(kind="synthetic"),
        started_at=t,
        finished_at=t,
        outcome="completed",
        payload=PayloadRef(type="qdt-hdf5-v1", path="x.h5", sha256="0" * 64, size_bytes=0),
    )


def map_payload(values: np.ndarray, gate: tuple[float, float], bias: tuple[float, float]) -> Payload:
    n0, n1 = values.shape
    ds = Dataset(
        dataset_id="map",
        name="map",
        dims=(Dimension(name="SG", size=n0), Dimension(name="V_sd", size=n1)),
        coords=(
            LinearCoordinate(name="SG", dim="SG", unit="V", start=gate[0], stop=gate[1], num=n0),
            LinearCoordinate(name="V_sd", dim="V_sd", unit="V", start=bias[0], stop=bias[1], num=n1),
        ),
        data_vars=(DataVariable(name="I", dims=("SG", "V_sd"), unit="A", dtype="float64"),),
        source=SourceDescriptor(kind="synthetic"),
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    return Payload(ds, {"I": values}, (), None, None)


def synthetic(period=0.1, e_c=1e-3, n_gate=96, n_bias=80, noise=0.01, seed=4):
    """A geometric diamond train (current steps on outside the nearest diamond) and its edge mask."""
    gate_span, bias_span = (-0.25, 0.25), (-1.6e-3, 1.6e-3)
    gate = np.linspace(*gate_span, n_gate)
    bias = np.linspace(*bias_span, n_bias)
    slope = 2 * e_c / period  # symmetric leads: neighbouring edges meet at bias e_c
    g, b = np.meshgrid(gate, bias, indexing="ij")
    d = g - np.rint(g / period) * period  # distance to the nearest degeneracy point
    excess = np.abs(b) - slope * np.abs(d)
    z = np.sign(b) * 1e-9 / (1 + np.exp(-excess / 0.03e-3))
    rng = np.random.default_rng(seed)
    z = z + noise * 1e-9 * rng.standard_normal(z.shape)
    truth = np.abs(excess) <= 0.5 * (bias[1] - bias[0])
    return map_payload(z, gate_span, bias_span), truth, period, e_c


def test_recovers_injected_diamonds():
    payload, truth, period, e_c = synthetic()
    result, _output = detect_diamonds(record_for("map"), payload)
    assert result.status == "ok", result.message
    r = recovery(result, payload.dataset, truth, tolerance=1.5)
    assert r.precision > 0.9 and r.recall > 0.85, r
    assert result.attrs["n_points"] == 5  # -0.2 .. 0.2
    assert result.estimate("period").value == pytest.approx(period, rel=0.03)
    assert result.estimate("charging_energy").value == pytest.approx(e_c, rel=0.05)
    assert result.estimate("lever_arm").value == pytest.approx(e_c / period, rel=0.08)
    assert result.estimate("slope_rising").value == pytest.approx(2 * e_c / period, rel=0.08)
    assert result.estimate("slope_falling").value == pytest.approx(-2 * e_c / period, rel=0.08)
    assert {a.kind for a in result.annotations} == {"line", "marker", "region"}
    for a in result.annotations:
        payload.dataset.check_annotation(a)
    assert result.estimate("charging_energy").unit == "eV"
    assert result.estimate("lever_arm").unit == "eV/V"


def sweep(seed: int, noise: bool):
    """The simulated sensor's diamonds through the real sweep path, with a cold sensor."""
    model = dataclasses.replace(default_model(), **COLD_SENSOR)
    stand = default_stand()
    plan = compile_sweep(diamonds(64, 64), stand, {"simulated": SimulatedEmitter()})
    device = default_device(seed=seed, noise=noise, model=model, sample_charge=False)
    data = assemble(plan.dataset, Executor(plan, {DEVICE_ID: device}).run().frames())
    payload = Payload(plan.dataset, {"I_sensor": data["I_sensor"].values}, (), plan, None)
    return payload, data["SG"].values, data["V_sd"].values, model


def edge_truth(model, sg: np.ndarray, v_sd: np.ndarray) -> np.ndarray:
    """Rasterized `diamond_edges` of every degeneracy point whose edges enter the window."""
    pitch_g = sg[1] - sg[0]
    segments = []
    for k in range(-5, 6):
        for phi_k, s in model.diamond_edges(k):
            reach = abs(v_sd).max() / abs(s)
            if not (sg[0] - reach <= phi_k <= sg[-1] + reach):
                continue
            g0, g1 = phi_k + v_sd[0] / s, phi_k + v_sd[-1] / s
            segments.append([[(g0 - sg[0]) / pitch_g, 0.0], [(g1 - sg[0]) / pitch_g, v_sd.size - 1.0]])
    return rasterize(np.array(segments), (sg.size, v_sd.size))


@pytest.mark.parametrize("noise", [False, True], ids=["clean", "noisy"])
def test_recovers_the_sensor_models_diamonds_through_a_sweep(noise):
    payload, sg, v_sd, model = sweep(seed=2, noise=noise)
    result, output = detect_diamonds(record_for(payload.dataset.dataset_id), payload)
    assert result.status == "ok", result.message
    r = recovery(result, payload.dataset, edge_truth(model, sg, v_sd), tolerance=2.0)
    assert r.precision > 0.9 and r.recall > 0.85, r
    assert result.estimate("period").value == pytest.approx(model.sensor_period_v, rel=0.03)
    assert result.estimate("charging_energy").value == pytest.approx(
        model.sensor_charging_ev, rel=0.05
    )
    assert result.estimate("lever_arm").value == pytest.approx(model.sensor_lever_arm, rel=0.08)
    assert result.estimate("slope_rising").value == pytest.approx(
        model.diamond_edges(0)[0][1], rel=0.08
    )
    assert all(a.coords == ("SG", "V_sd") for a in result.annotations)
    assert output is not None and output.dataset.source.kind == "analysis"
    assert output.arrays["gradient"].shape == (64, 64)
    assert result.record_id == "cd" * 16 and result.method.name == NAME


def test_a_map_without_diamonds_fails_instead_of_inventing_them():
    rng = np.random.default_rng(3)
    payload = map_payload(rng.normal(0, 1, (64, 64)), (0.0, 0.1), (-1e-3, 1e-3))
    result, _output = detect_diamonds(record_for("map"), payload)
    assert result.status == "failed" and not result.estimates


def test_refuses_a_payload_from_another_record():
    payload = map_payload(np.zeros((32, 32)), (0.0, 1.0), (0.0, 1.0))
    with pytest.raises(ValueError, match="payload for"):
        detect_diamonds(record_for("other"), payload)


def test_score_is_exact_on_identical_masks_and_zero_on_empty_ones():
    a = rasterize(np.array([[[0.0, 0.0], [9.0, 9.0]]]), (10, 10))
    assert score(a, a, 0.0) == (1.0, 1.0, int(a.sum()), int(a.sum()))
    empty = np.zeros((10, 10), dtype=bool)
    assert score(empty, a, 1.0)[:2] == (0.0, 0.0) and score(a, empty, 1.0)[:2] == (0.0, 0.0)
