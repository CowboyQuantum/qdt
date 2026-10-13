"""Coulomb diamonds (ADR 0031): injection–recovery on a synthetic diamond map and on the simulated
sensor SET, whose model knows E_c, the period, the lever arm and the edge lines."""

from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_analysis import coulomb_diamonds, recovery
from qdt_analysis.recovery import rasterize, score
from qdt_lab.experiment import Executor, SimulatedEmitter, compile_sweep
from qdt_lab.stream import assemble
from qdt_schemas.data import Dataset, DataVariable, Dimension, LinearCoordinate, SourceDescriptor
from qdt_schemas.modeling import ScenarioRef
from qdt_sim.scenarios import DEVICE_ID, resolve

T0 = datetime(2026, 10, 13, tzinfo=UTC)


def synthetic(period=0.1, e_c=1e-3, n_gate=96, n_bias=80, noise=0.01, seed=4):
    """A geometric diamond train: current = clip of the distance outside the nearest diamond; truth
    mask = its edges."""
    gate = np.linspace(-0.25, 0.25, n_gate)
    bias = np.linspace(-1.6e-3, 1.6e-3, n_bias)
    ds = Dataset(
        dataset_id="synthetic-diamonds",
        name="injected diamonds",
        dims=(Dimension(name="gate", size=n_gate), Dimension(name="bias", size=n_bias)),
        coords=(
            LinearCoordinate(name="V_g", dim="gate", unit="V", start=-0.25, stop=0.25, num=n_gate),
            LinearCoordinate(name="V_sd", dim="bias", unit="V", start=-1.6e-3, stop=1.6e-3, num=n_bias),
        ),
        data_vars=(DataVariable(name="I", dims=("gate", "bias"), unit="A", dtype="float64"),),
        source=SourceDescriptor(kind="synthetic"),
        created_at=T0,
    )
    slope = 2 * e_c / period  # symmetric leads: apex at e_c when edges from neighbours meet
    g, b = np.meshgrid(gate, bias, indexing="ij")
    k = np.rint(g / period)
    d = g - k * period  # distance to the nearest degeneracy point
    # outside the diamond when |b| > slope·|d| ... in units of bias; smooth step of width w
    w = 0.03e-3
    excess = np.abs(b) - slope * np.abs(d)
    z = np.sign(b) * 1e-9 / (1 + np.exp(-excess / w))
    rng = np.random.default_rng(seed)
    z = z + noise * 1e-9 * rng.standard_normal(z.shape)
    truth = np.abs(excess) <= 0.5 * (bias[1] - bias[0])
    return ds, {"I": z}, truth, period, e_c


def test_injected_diamonds_are_recovered():
    ds, arrays, truth, period, e_c = synthetic()
    scenario = ScenarioRef(kind="synthetic", name="injected_diamonds", seed=4)
    result = coulomb_diamonds(ds, arrays, scenario, created_at=T0)
    r = recovery(result, ds, arrays, truth, tolerance=1.5)
    assert r.precision > 0.9 and r.recall > 0.85, r
    s = result.summary
    assert s["n_points"] == 5  # -0.2 .. 0.2
    assert s["period_v"] == pytest.approx(period, rel=0.03)
    assert s["charging_energy_ev"] == pytest.approx(e_c, rel=0.05)
    assert s["lever_arm_ev_per_v"] == pytest.approx(e_c / period, rel=0.08)
    assert s["slope_rising"] == pytest.approx(2 * e_c / period, rel=0.08)
    assert s["slope_falling"] == pytest.approx(-2 * e_c / period, rel=0.08)
    kinds = {a.kind for a in result.annotations}
    assert kinds == {"line", "marker", "region"}
    for a in result.annotations:
        ds.check_annotation(a)


def run(ref: ScenarioRef):
    scenario = resolve(ref)
    plan = compile_sweep(scenario.definition, scenario.stand, {"simulated": SimulatedEmitter()})
    xds = assemble(plan.dataset, Executor(plan, {DEVICE_ID: scenario.device}).run().frames())
    arrays = {"I_sensor": xds["I_sensor"].values}
    return plan.dataset, arrays, xds["SG"].values, xds["V_sd"].values, scenario.device.model


def edge_truth(model, sg: np.ndarray, v_sd: np.ndarray) -> np.ndarray:
    """Rasterized `diamond_edges` of every degeneracy point in the window (pixel space)."""
    pitch_g, _pitch_b = sg[1] - sg[0], v_sd[1] - v_sd[0]
    segments = []
    for k in range(-5, 6):
        for phi_k, s in model.diamond_edges(k):
            if not (sg[0] - abs(v_sd).max() / abs(s) <= phi_k <= sg[-1] + abs(v_sd).max() / abs(s)):
                continue
            g0, g1 = phi_k + v_sd[0] / s, phi_k + v_sd[-1] / s
            segments.append(
                [
                    [(g0 - sg[0]) / pitch_g, 0.0],
                    [(g1 - sg[0]) / pitch_g, v_sd.size - 1.0],
                ]
            )
    return rasterize(np.array(segments), (sg.size, v_sd.size)) if segments else np.zeros(
        (sg.size, v_sd.size), bool
    )


@pytest.mark.parametrize("noise", [False, True], ids=["clean", "noisy"])
def test_simulated_sensor_diamonds_recover_the_model(noise):
    ref = ScenarioRef(
        kind="simulation",
        name="diamonds",
        seed=2,
        # a diamond characterisation wants a cold sensor: 10 mV peaks (kT_s ≈ 20 µeV) instead of the
        # stability default of 40 mV, whose thermal tails overlap near the apexes (ADR 0031)
        parameters={"noise": noise, "sample_charge": False, "sensor_width_v": 0.01},
    )
    dataset, arrays, sg, v_sd, model = run(ref)
    result = coulomb_diamonds(dataset, arrays, ref)
    truth = edge_truth(model, sg, v_sd)
    lines = result.model_copy(update={"annotations": tuple(a for a in result.annotations if a.kind == "line")})
    r = recovery(lines, dataset, arrays, truth, tolerance=2.0)
    assert r.precision > 0.9 and r.recall > 0.85, r
    s = result.summary
    assert s["period_v"] == pytest.approx(model.sensor_period_v, rel=0.03)
    assert s["charging_energy_ev"] == pytest.approx(model.sensor_charging_ev, rel=0.05)
    assert s["lever_arm_ev_per_v"] == pytest.approx(model.sensor_lever_arm, rel=0.08)
    assert s["slope_rising"] == pytest.approx(model.diamond_edges(0)[0][1], rel=0.08)
    assert result.scenario == ref and result.measurement.variable == "I_sensor"
    for a in result.annotations:
        dataset.check_annotation(a)
        assert a.coords == ("SG", "V_sd")


def test_score_handles_an_empty_truth():
    assert score(np.zeros((4, 4), bool), np.zeros((4, 4), bool), 1.0)[:2] == (0.0, 0.0)
