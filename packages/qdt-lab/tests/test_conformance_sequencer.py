"""Sequencer conformance. Test names are the spec; drivers must pass these unchanged.

The fixture supplies a backend and the flat-index conformance program for it (Probe 01's program on
the OPX): compile once, run with integer parameters, positional results equal the flat loop index.
"""

from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_lab.protocols import CompiledProgram, Sequencer
from qdt_lab.stream import Source, assemble
from qdt_schemas.data import Dataset, DataVariable, Dimension, SourceDescriptor


def run_dataset(n_lines: int, n_points: int) -> Dataset:
    return Dataset(
        dataset_id=f"run-{n_lines}x{n_points}",
        name="conformance run",
        dims=(Dimension(name="outer", size=n_lines), Dimension(name="inner", size=n_points)),
        data_vars=(DataVariable(name="data", dims=("outer", "inner"), unit="", dtype="int64"),),
        source=SourceDescriptor(kind="simulation"),
        created_at=datetime(2026, 10, 12, tzinfo=UTC),
    )


def params(n_lines: int, n_points: int) -> dict[str, int]:
    return {"n_lines": n_lines, "n_points": n_points, "step": 1000}


def test_backend_satisfies_protocol(sequencer_and_program):
    sequencer, program = sequencer_and_program
    assert isinstance(sequencer, Sequencer)
    assert isinstance(sequencer.compile(program), CompiledProgram)


def test_run_returns_a_source_for_the_given_dataset(sequencer_and_program):
    sequencer, program = sequencer_and_program
    ds = run_dataset(3, 4)
    src = sequencer.run(sequencer.compile(program), params(3, 4), ds)
    assert isinstance(src, Source)
    assert src.dataset == ds


def test_results_are_positional_flat_loop_index(sequencer_and_program):
    sequencer, program = sequencer_and_program
    ds = run_dataset(3, 5)
    out = assemble(ds, sequencer.run(sequencer.compile(program), params(3, 5), ds).frames())
    np.testing.assert_array_equal(out["data"].values, np.arange(15).reshape(3, 5))


def test_one_compiled_program_runs_with_different_parameters(sequencer_and_program):
    sequencer, program = sequencer_and_program
    compiled = sequencer.compile(program)
    for n_lines, n_points in ((2, 3), (5, 2)):
        ds = run_dataset(n_lines, n_points)
        out = assemble(ds, sequencer.run(compiled, params(n_lines, n_points), ds).frames())
        assert out["data"].shape == (n_lines, n_points)


def test_last_frame_is_final(sequencer_and_program):
    sequencer, program = sequencer_and_program
    ds = run_dataset(2, 2)
    frames = list(sequencer.run(sequencer.compile(program), params(2, 2), ds).frames())
    assert frames[-1].chunk.final
    assert not any(f.chunk.final for f in frames[:-1])


def test_run_rejects_missing_or_non_int_parameters(sequencer_and_program):
    sequencer, program = sequencer_and_program
    compiled = sequencer.compile(program)
    with pytest.raises(ValueError):
        sequencer.run(compiled, {"n_lines": 2, "n_points": 2}, run_dataset(2, 2))
    with pytest.raises(ValueError):
        sequencer.run(compiled, {**params(2, 2), "step": 1e-3}, run_dataset(2, 2))


def test_run_rejects_a_dataset_that_disagrees_with_parameters(sequencer_and_program):
    sequencer, program = sequencer_and_program
    with pytest.raises(ValueError):
        sequencer.run(sequencer.compile(program), params(2, 3), run_dataset(2, 4))
