"""`qdt-hdf5-v1` (ADR 0023): round trip, validation on write, immutability, lazy h5py."""

import json
import pathlib
import subprocess
import sys
from datetime import UTC, datetime

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("h5py")

from qdt_schemas.activity import ExecutionPlan
from qdt_schemas.data import (
    Annotation,
    Dataset,
    DataVariable,
    Dimension,
    LinearCoordinate,
    SourceDescriptor,
    StreamedCoordinate,
)
from qdt_schemas.payload_hdf5 import read_payload, write_payload
from qdt_schemas.stand import StandConfig

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def fixture(name, cls):
    return cls.model_validate(json.loads((FIXTURES / name / "v1.json").read_text()))


def records_dataset() -> Dataset:
    """Unbounded record dim, linear gate axis, streamed time axis: every coordinate kind but indexed."""
    return Dataset(
        dataset_id="rec",
        name="records",
        dims=(Dimension(name="record"), Dimension(name="t", size=4)),
        coords=(
            StreamedCoordinate(name="time", dim="t", unit="s"),
            LinearCoordinate(name="t_index", dim="t", unit="", start=0, stop=3, num=4),
        ),
        data_vars=(DataVariable(name="v", dims=("record", "t"), unit="V", dtype="float32"),),
        source=SourceDescriptor(kind="synthetic"),
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
    )


def test_round_trip_with_plan_stand_and_annotations(tmp_path):
    plan = fixture("ExecutionPlan", ExecutionPlan)
    stand = fixture("StandConfig", StandConfig)
    ann = fixture("Annotation", Annotation)
    arrays = {"I_sensor": np.arange(20, dtype=np.float64).reshape(4, 5)}
    path = tmp_path / "p.h5"
    write_payload(path, plan.dataset, arrays, annotations=[ann], plan=plan, stand=stand)
    out = read_payload(path)
    assert out.dataset == plan.dataset and out.plan == plan and out.stand == stand
    assert out.annotations == (ann,)
    np.testing.assert_array_equal(out.arrays["I_sensor"], arrays["I_sensor"])


def test_unbounded_dimension_and_streamed_coordinate(tmp_path):
    ds = records_dataset()
    arrays = {
        "v": np.ones((3, 4), dtype=np.float32),
        "time": np.array([0.0, 1e-9, 2e-9, 3e-9]),
    }
    write_payload(tmp_path / "r.h5", ds, arrays)
    out = read_payload(tmp_path / "r.h5")
    assert out.arrays["v"].shape == (3, 4) and out.arrays["v"].dtype == np.float32
    np.testing.assert_array_equal(out.arrays["time"], arrays["time"])
    assert out.plan is None and out.stand is None and out.annotations == ()


@pytest.mark.parametrize(
    ("arrays", "match"),
    [
        ({"time": np.zeros(4)}, "lacks"),
        ({"v": np.ones((3, 4), np.float32), "time": np.zeros(4), "x": np.zeros(1)}, "neither"),
        ({"v": np.ones((3, 5), np.float32), "time": np.zeros(4)}, "t=5"),
        ({"v": np.ones(4, np.float32), "time": np.zeros(4)}, "axes"),
        ({"v": np.ones((3, 4), np.float64), "time": np.zeros(4)}, "declared float32"),
    ],
)
def test_write_refuses_arrays_that_disagree_with_the_definition(tmp_path, arrays, match):
    with pytest.raises(ValueError, match=match):
        write_payload(tmp_path / "bad.h5", records_dataset(), arrays)
    assert not (tmp_path / "bad.h5").exists()


def test_a_written_payload_is_never_overwritten(tmp_path):
    ds = records_dataset()
    arrays = {"v": np.ones((1, 4), np.float32), "time": np.zeros(4)}
    write_payload(tmp_path / "p.h5", ds, arrays)
    with pytest.raises(FileExistsError):
        write_payload(tmp_path / "p.h5", ds, arrays)


def test_plan_must_declare_the_same_dataset(tmp_path):
    plan = fixture("ExecutionPlan", ExecutionPlan)
    with pytest.raises(ValueError, match="different Dataset"):
        write_payload(
            tmp_path / "p.h5",
            records_dataset(),
            {"v": np.ones((1, 4), np.float32), "time": np.zeros(4)},
            plan=plan,
        )


def test_other_files_are_not_payloads(tmp_path):
    import h5py

    with h5py.File(tmp_path / "x.h5", "w") as f:
        f.attrs["qdt_payload_type"] = "something-else"
    with pytest.raises(ValueError, match="not a qdt-hdf5-v1"):
        read_payload(tmp_path / "x.h5")


def test_qdt_schemas_imports_without_h5py_or_numpy():
    code = (
        "import sys; sys.modules['h5py'] = None; sys.modules['numpy'] = None\n"
        "import importlib, pkgutil, qdt_schemas\n"
        "for m in pkgutil.walk_packages(qdt_schemas.__path__, 'qdt_schemas.'):\n"
        "    importlib.import_module(m.name)\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
