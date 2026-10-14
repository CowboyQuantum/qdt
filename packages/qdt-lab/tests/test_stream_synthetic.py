"""Synthetic sources: every frame obeys the contract, chunks tile the Dataset, pacing meets the target."""

import time

import numpy as np
import pytest

from qdt_lab.stream import Frame, SyntheticMap, SyntheticRecords, assemble
from qdt_schemas.data import Dataset, DatasetChunk


def expected_map(src: SyntheticMap) -> np.ndarray:
    return np.stack([src.row(i) for i in range(src.n_outer)])


@pytest.mark.parametrize("ppc", [5, 16, 32, 96], ids=["partial-uneven", "partial", "line", "rows"])
def test_map_chunks_tile_the_map_at_any_granularity(ppc):
    src = SyntheticMap(n_outer=6, n_inner=32, points_per_chunk=ppc, points_per_second=None, seed=3)
    frames = list(src.frames())
    assert [f.chunk.seq for f in frames] == list(range(len(frames)))
    assert [f.chunk.final for f in frames] == [False] * (len(frames) - 1) + [True]
    out = assemble(src.dataset, frames)
    np.testing.assert_array_equal(out["signal"].values, expected_map(src))
    assert out["signal"].dims == ("gate_outer", "gate_inner")
    np.testing.assert_allclose(out["V_inner"].values, np.linspace(-0.5, 0.5, 32))


def test_map_rejects_row_count_that_does_not_divide():
    with pytest.raises(ValueError, match="multiple"):
        SyntheticMap(n_inner=32, points_per_chunk=40)


def test_map_defaults_are_the_design_targets():
    src = SyntheticMap(seed=0)
    assert (src.n_outer, src.n_inner) == (2048, 2048)
    assert src.points_per_second == 1_000_000
    first = next(src.frames())
    first.check(src.dataset)
    assert first.arrays["signal"].shape == (1, 2048)
    assert first.arrays["signal"].dtype == np.float32


def test_map_is_paced_to_points_per_second():
    src = SyntheticMap(
        n_outer=64, n_inner=256, points_per_second=1_000_000
    )  # 16384 points -> ~16 ms
    t0 = time.perf_counter()
    n = sum(f.arrays["signal"].size for f in src.frames())
    elapsed = time.perf_counter() - t0
    assert n / elapsed <= 1_000_000 * 1.05  # never faster than the target
    assert elapsed < 0.5  # and not starved by sleep granularity


def test_unpaced_map_sustains_the_design_rate(wallclock_rate):
    src = SyntheticMap(n_outer=256, points_per_second=None)  # 256 x 2048 = 524288 points
    t0 = time.perf_counter()
    n = sum(f.arrays["signal"].size for f in src.frames())
    wallclock_rate(n / (time.perf_counter() - t0), 1_000_000, "producer")  # not the bottleneck


def test_records_carry_explicit_time_axis():
    src = SyntheticRecords(
        n_samples=500, n_records=4, records_per_second=None, sample_interval=2e-9
    )
    frames = list(src.frames())
    for f in frames:
        f.check(src.dataset)
        assert f.chunk.explicit_coords == ("time",)
    out = assemble(src.dataset, frames)
    assert out["voltage"].shape == (4, 500)  # unbounded dim sized by the frames
    np.testing.assert_allclose(np.diff(out["time"].values), 2e-9)
    np.testing.assert_array_equal(out["voltage"].values[2], src.record(2))


def test_envelopes_are_json_round_trippable():
    src = SyntheticMap(n_outer=2, n_inner=8, points_per_second=None)
    assert Dataset.model_validate_json(src.dataset.model_dump_json()) == src.dataset
    for f in src.frames():
        assert DatasetChunk.model_validate_json(f.chunk.model_dump_json()) == f.chunk


@pytest.mark.parametrize(
    ("arrays", "match"),
    [
        ({"signal": np.zeros((1, 8), np.float64)}, "dtype"),
        ({"signal": np.zeros((2, 8), np.float32)}, "shape"),
        ({}, "payload names"),
    ],
)
def test_frame_check_catches_payload_mismatch(arrays, match):
    src = SyntheticMap(n_outer=2, n_inner=8, points_per_second=None)
    chunk = next(src.frames()).chunk
    with pytest.raises(ValueError, match=match):
        Frame(chunk, arrays).check(src.dataset)


def test_assemble_is_order_independent():
    src = SyntheticMap(n_outer=4, n_inner=8, points_per_chunk=3, points_per_second=None)
    frames = list(src.frames())
    a = assemble(src.dataset, frames)
    b = assemble(src.dataset, reversed(frames))
    np.testing.assert_array_equal(a["signal"].values, b["signal"].values)


@pytest.mark.parametrize("advisory", [False, True])
def test_wallclock_rate_is_strict_locally_and_advisory_on_shared_runners(
    advisory, monkeypatch, request
):
    """ADR 0039: below target fails locally; with QDT_WALLCLOCK_ADVISORY=1 it warns, and only a rate
    below half the target (a broken path, not a slow runner) fails."""
    monkeypatch.setenv("QDT_WALLCLOCK_ADVISORY", "1" if advisory else "0")
    check = request.getfixturevalue("wallclock_rate")
    check(1_000_000, 1_000_000, "on target")
    if advisory:
        with pytest.warns(UserWarning, match="advisory"):
            check(900_000, 1_000_000, "slow runner")
    else:
        with pytest.raises(AssertionError, match="slow runner"):
            check(900_000, 1_000_000, "slow runner")
    with pytest.raises(AssertionError, match="broken"):
        check(400_000, 1_000_000, "broken")
