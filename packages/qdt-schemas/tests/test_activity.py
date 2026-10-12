from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from qdt_schemas.activity import SequencerParameter, SequencerProgram, SequencerResult
from qdt_schemas.data import Dataset, DataVariable, Dimension, SourceDescriptor

T0 = datetime(2026, 10, 12, tzinfo=UTC)


def program() -> SequencerProgram:
    return SequencerProgram(
        backend="qua",
        body="# opaque",
        parameters=(
            SequencerParameter(name="n_lines", unit=""),
            SequencerParameter(name="n_points", unit=""),
            SequencerParameter(name="step", unit="V", scale=1e-6),
        ),
        results=(
            SequencerResult(name="data", dims=("n_lines", "n_points"), dtype="int64", unit=""),
        ),
    )


def dataset(n_lines: int, n_points: int, dtype: str = "int64") -> Dataset:
    return Dataset(
        dataset_id="run",
        name="run",
        dims=(Dimension(name="outer", size=n_lines), Dimension(name="inner", size=n_points)),
        data_vars=(DataVariable(name="data", dims=("outer", "inner"), unit="", dtype=dtype),),
        source=SourceDescriptor(kind="simulation"),
        created_at=T0,
    )


def test_round_trip():
    p = program()
    assert SequencerProgram.model_validate_json(p.model_dump_json()) == p


def test_result_axes_must_name_parameters():
    with pytest.raises(ValidationError, match="unknown parameters"):
        SequencerProgram(
            backend="qua",
            body="",
            results=(SequencerResult(name="d", dims=("n",), dtype="int64", unit=""),),
        )


def test_names_unique():
    with pytest.raises(ValidationError, match="unique"):
        SequencerProgram(
            backend="qua",
            body="",
            parameters=(
                SequencerParameter(name="n", unit=""),
                SequencerParameter(name="n", unit=""),
            ),
            results=(SequencerResult(name="d", dims=("n",), dtype="int64", unit=""),),
        )


def test_check_run_accepts_matching_dataset():
    program().check_run({"n_lines": 3, "n_points": 4, "step": 1000}, dataset(3, 4))


@pytest.mark.parametrize(
    ("values", "ds", "match"),
    [
        ({"n_lines": 3, "n_points": 4}, dataset(3, 4), "missing parameters"),
        ({"n_lines": 3, "n_points": 4, "step": 1.0}, dataset(3, 4), "must be an int"),
        ({"n_lines": 3, "n_points": 4, "step": 1, "x": 1}, dataset(3, 4), "unknown parameters"),
        ({"n_lines": 3, "n_points": 4, "step": 1}, dataset(3, 5), "dataset declares"),
        ({"n_lines": 3, "n_points": 4, "step": 1}, dataset(3, 4, "float32"), "is int64"),
        ({"n_lines": 0, "n_points": 4, "step": 1}, dataset(1, 4), "empty axis"),
    ],
)
def test_check_run_rejects(values, ds, match):
    with pytest.raises(ValueError, match=match):
        program().check_run(values, ds)


def test_check_run_needs_a_variable_per_result():
    ds = dataset(3, 4).model_copy(
        update={
            "data_vars": (
                DataVariable(name="other", dims=("outer", "inner"), unit="", dtype="int64"),
            )
        }
    )
    with pytest.raises(ValueError, match="no data variable"):
        program().check_run({"n_lines": 3, "n_points": 4, "step": 1}, ds)
