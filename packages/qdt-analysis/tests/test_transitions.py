"""Injection–recovery for charge-transition detection (Step 4 L0, ADR 0029).

Truth is injected two ways: a synthetic charge lattice with an arbitrary matrix, and the gate
capacitances of `SimulatedDevice`'s dot model, measured through the real sweep path. The estimator
must recover each within stated tolerances, and must refuse a map with no transitions.
"""

from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_analysis.transitions import NAME, detect_transitions
from qdt_lab.experiment import Executor, SimulatedEmitter, compile_sweep
from qdt_lab.stream import assemble
from qdt_schemas.data import Dataset, DataVariable, Dimension, LinearCoordinate, SourceDescriptor
from qdt_schemas.envelope import MeasurementRecord, PayloadRef
from qdt_schemas.payload_hdf5 import Payload
from qdt_sim.scenarios import DEVICE_ID, default_device, default_model, default_stand, stability

OCCUPIED = (0.03, 0.18)  # both dots hold electrons everywhere: the honeycomb is periodic


def record_for(dataset_id: str) -> MeasurementRecord:
    t = datetime(2026, 10, 13, tzinfo=UTC)
    return MeasurementRecord(
        record_id="ab" * 16,
        device_id="dev",
        stand_id="stand",
        stand_sha256="0" * 64,
        definition_name="map",
        definition_sha256="0" * 64,
        plan_id=dataset_id,
        source=SourceDescriptor(kind="synthetic"),
        started_at=t,
        finished_at=t,
        outcome="completed",
        payload=PayloadRef(type="qdt-hdf5-v1", path="x.h5", sha256="0" * 64, size_bytes=0),
    )


def map_payload(values: np.ndarray, x: tuple[float, float], y: tuple[float, float]) -> Payload:
    n0, n1 = values.shape
    ds = Dataset(
        dataset_id="map",
        name="map",
        dims=(Dimension(name="P1", size=n0), Dimension(name="P2", size=n1)),
        coords=(
            LinearCoordinate(name="P1", dim="P1", unit="V", start=x[0], stop=x[1], num=n0),
            LinearCoordinate(name="P2", dim="P2", unit="V", start=y[0], stop=y[1], num=n1),
        ),
        data_vars=(DataVariable(name="I", dims=("P1", "P2"), unit="A", dtype="float64"),),
        source=SourceDescriptor(kind="synthetic"),
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    return Payload(ds, {"I": values}, (), None, None)


def estimates(result) -> np.ndarray:
    return np.array(
        [
            [result.estimate("a_per_volt_row").value, result.estimate("a_per_volt_col").value],
            [result.estimate("b_per_volt_row").value, result.estimate("b_per_volt_col").value],
        ]
    )


@pytest.mark.parametrize(
    "truth",
    [
        np.array([[60.0, 14.0], [12.0, 55.0]]),
        np.array([[80.0, -10.0], [8.0, 70.0]]),  # negative cross term
    ],
    ids=["positive-cross", "negative-cross"],
)
def test_recovers_an_injected_synthetic_lattice(truth):
    rng = np.random.default_rng(0)
    n, span = (96, 96), (0.0, 0.15)
    x = np.linspace(*span, n[0])
    v = np.stack(np.meshgrid(x, np.linspace(*span, n[1]), indexing="ij"), axis=-1)
    occupation = np.floor(v @ truth.T)  # electrons on each dot: steps at every lattice plane
    current = occupation @ np.array([1.0, 0.7]) + rng.normal(0, 0.1, n)
    result = detect_transitions(record_for("map"), map_payload(current, span, span))
    assert result.status == "ok", result.message
    np.testing.assert_allclose(estimates(result), truth, atol=0.02 * truth.max())


@pytest.mark.parametrize("seed", [1, 2])
def test_recovers_the_dot_models_gate_capacitances_through_a_noisy_sweep(seed):
    plan = compile_sweep(
        stability(96, 96, p1=OCCUPIED, p2=OCCUPIED),
        default_stand(),
        {"simulated": SimulatedEmitter()},
    )
    frames = Executor(plan, {DEVICE_ID: default_device(seed=seed, noise=True)}).run().frames()
    data = assemble(plan.dataset, frames)
    payload = Payload(plan.dataset, {"I_sensor": data["I_sensor"].values}, (), plan, None)
    result = detect_transitions(record_for(plan.dataset.dataset_id), payload)

    truth = default_model().charge_lattice("P1", "P2")  # electrons per volt: rows of C_gate / e
    est = estimates(result)
    assert result.status == "ok", result.message
    np.testing.assert_allclose(np.diag(est), np.diag(truth), rtol=0.02)
    assert abs(result.estimate("cross_ratio_a").value - truth[0, 1] / truth[0, 0]) < 0.02
    assert abs(result.estimate("cross_ratio_b").value - truth[1, 0] / truth[1, 1]) < 0.02
    assert result.annotations, "transition segments are overlaid"
    assert {a.attrs["family"] for a in result.annotations} == {"steep", "shallow"}
    assert all(
        a.coords == ("P1", "P2") and a.dataset_id == plan.dataset.dataset_id
        for a in result.annotations
    )


def test_a_map_without_transitions_fails_instead_of_inventing_lines():
    rng = np.random.default_rng(3)
    span = (0.0, 0.1)
    result = detect_transitions(
        record_for("map"), map_payload(rng.normal(0, 1, (64, 64)), span, span)
    )
    assert result.status == "failed" and not result.annotations and not result.estimates


def test_dual_provenance_names_the_record_and_the_method():
    span = (0.0, 0.15)
    x = np.linspace(*span, 64)
    v = np.stack(np.meshgrid(x, x, indexing="ij"), axis=-1)
    current = np.floor(v @ np.array([[60.0, 14.0], [12.0, 55.0]]).T).sum(-1)
    result = detect_transitions(record_for("map"), map_payload(current, span, span), smooth_px=1.2)
    assert result.record_id == "ab" * 16
    assert result.method.name == NAME and result.method.parameters["smooth_px"] == 1.2
    assert result.method_sha256 == result.method.content_sha256()


def test_refuses_a_payload_from_another_record():
    with pytest.raises(ValueError, match="payload for"):
        detect_transitions(record_for("other"), map_payload(np.zeros((32, 32)), (0, 1), (0, 1)))
