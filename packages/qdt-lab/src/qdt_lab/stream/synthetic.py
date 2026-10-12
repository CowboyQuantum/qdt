"""Synthetic sources emulating the Analysis 0001 envelope (docs/analysis/0001-stream-budget.md).

`SyntheticMap` is OPX-shaped: a 2D sweep, positional results, implicit coordinates, paced in points/s.
`SyntheticRecords` is scope-shaped: whole records pulled at a few Hz with an explicit (streamed) time axis.
Probe 01 confirmed the chunk semantics (ADR 0015); the defaults are the design ceiling, which the OPX path
sustains (10⁶ points/s with no loss; unpaced bursts ≈ 3×10⁶).
Content is a pure function of (seed, index), so the assembled result does not depend on chunking.
"""

import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import numpy as np

from qdt_schemas.data import (
    Dataset,
    DatasetChunk,
    DataVariable,
    Dimension,
    IndexSlice,
    LinearCoordinate,
    SourceDescriptor,
    StreamedCoordinate,
)

from .frame import Frame

MAP_SIZE = 2048  # FINISH_LINE.md design target: largest 2D map
POINTS_PER_SECOND = 1_000_000  # FINISH_LINE.md design target: sustained stream rate


class _Pacer:
    """Sleeps until `units` units of work are due at `rate` units/s since the first call."""

    def __init__(self, rate: float | None) -> None:
        self._rate = rate
        self._t0: float | None = None

    def wait(self, units: float) -> None:
        if self._rate is None:
            return
        now = time.perf_counter()
        if self._t0 is None:
            self._t0 = now
        delay = self._t0 + units / self._rate - now
        if delay > 0:
            time.sleep(delay)


class SyntheticMap:
    """Charge-stability-like 2D map streamed row-major, outer gate slow, inner gate fast.

    `points_per_chunk` sets delivery granularity: below the row length gives partial lines, the row
    length (default) gives one line per chunk, a multiple of it gives several rows per chunk.
    """

    def __init__(
        self,
        n_outer: int = MAP_SIZE,
        n_inner: int = MAP_SIZE,
        points_per_chunk: int | None = None,
        points_per_second: float | None = POINTS_PER_SECOND,
        noise: float = 0.02,
        seed: int = 0,
        dataset_id: str | None = None,
    ) -> None:
        ppc = points_per_chunk or n_inner
        if ppc > n_inner and ppc % n_inner:
            raise ValueError("points_per_chunk above the row length must be a multiple of it")
        self.n_outer, self.n_inner, self.points_per_chunk = n_outer, n_inner, ppc
        self.points_per_second, self.noise, self.seed = points_per_second, noise, seed
        self.v_outer = np.linspace(-0.5, 0.5, n_outer)
        self.v_inner = np.linspace(-0.5, 0.5, n_inner)
        self.dataset = Dataset(
            dataset_id=dataset_id or uuid.uuid4().hex,
            name="synthetic stability map",
            dims=(
                Dimension(name="gate_outer", size=n_outer),
                Dimension(name="gate_inner", size=n_inner),
            ),
            coords=(
                LinearCoordinate(
                    name="V_outer", dim="gate_outer", unit="V", start=-0.5, stop=0.5, num=n_outer
                ),
                LinearCoordinate(
                    name="V_inner", dim="gate_inner", unit="V", start=-0.5, stop=0.5, num=n_inner
                ),
            ),
            data_vars=(
                DataVariable(
                    name="signal", dims=("gate_outer", "gate_inner"), unit="", dtype="float32"
                ),
            ),
            attrs={"provisional": True, "seed": seed},
            source=SourceDescriptor(kind="synthetic", label="synthetic stability map"),
            created_at=datetime.now(UTC),
        )

    def row(self, i: int) -> np.ndarray:
        """Row `i` of the map, deterministic in (seed, i)."""
        u1 = 6.0 * self.v_inner + 2.0 * self.v_outer[i]
        u2 = 2.0 * self.v_inner + 6.0 * self.v_outer[i]
        peaks = np.exp(-((((u1 % 1.0) - 0.5) / 0.04) ** 2)) + np.exp(
            -((((u2 % 1.0) - 0.5) / 0.04) ** 2)
        )
        noise = np.random.default_rng([self.seed, i]).normal(0.0, self.noise, self.n_inner)
        return (0.1 + peaks + noise).astype(np.float32)

    def frames(self) -> Iterator[Frame]:
        """Yield frames in seq order, paced to `points_per_second` (unpaced if None)."""
        pacer = _Pacer(self.points_per_second)
        ppc, n = self.points_per_chunk, self.n_inner
        if ppc >= n:
            rows = ppc // n
            regions = [
                ((i, min(i + rows, self.n_outer)), (0, n)) for i in range(0, self.n_outer, rows)
            ]
        else:
            regions = [
                ((i, i + 1), (j, min(j + ppc, n)))
                for i in range(self.n_outer)
                for j in range(0, n, ppc)
            ]
        done = 0
        for seq, ((i0, i1), (j0, j1)) in enumerate(regions):
            block = np.stack([self.row(i)[j0:j1] for i in range(i0, i1)])
            done += block.size
            pacer.wait(done)
            yield Frame(
                DatasetChunk(
                    dataset_id=self.dataset.dataset_id,
                    seq=seq,
                    region=(
                        IndexSlice(dim="gate_outer", start=i0, stop=i1),
                        IndexSlice(dim="gate_inner", start=j0, stop=j1),
                    ),
                    variables=("signal",),
                    produced_at=datetime.now(UTC),
                    final=seq == len(regions) - 1,
                ),
                {"signal": block},
            )


class SyntheticRecords:
    """Scope-like whole-record captures; the time axis travels in-band as a streamed coordinate.

    Provisional: the time axis is identical for every record (one 1-D coordinate over `t`). Whether real
    captures need a per-record axis is a Probe 01 question for the contract freeze.
    """

    def __init__(
        self,
        n_samples: int = 10_000,
        n_records: int = 10,
        records_per_second: float | None = 5.0,
        sample_interval: float = 1e-9,
        noise: float = 0.01,
        seed: int = 0,
        dataset_id: str | None = None,
    ) -> None:
        self.n_samples, self.n_records = n_samples, n_records
        self.records_per_second, self.noise, self.seed = records_per_second, noise, seed
        self.time = (np.arange(n_samples) - n_samples // 10) * sample_interval
        self.dataset = Dataset(
            dataset_id=dataset_id or uuid.uuid4().hex,
            name="synthetic scope records",
            dims=(Dimension(name="record"), Dimension(name="t", size=n_samples)),
            coords=(StreamedCoordinate(name="time", dim="t", unit="s", dtype="float64"),),
            data_vars=(
                DataVariable(name="voltage", dims=("record", "t"), unit="V", dtype="float64"),
            ),
            attrs={"provisional": True, "seed": seed},
            source=SourceDescriptor(kind="synthetic", label="synthetic scope records"),
            created_at=datetime.now(UTC),
        )

    def record(self, k: int) -> np.ndarray:
        """Record `k`: a damped ring-down after the trigger, deterministic in (seed, k)."""
        tau = self.time[-1] / 4
        after = self.time >= 0
        clean = np.where(after, np.exp(-np.clip(self.time, 0, None) / tau), 0.0)
        clean = clean * np.cos(2 * np.pi * 8 / self.time[-1] * self.time)
        return clean + np.random.default_rng([self.seed, k]).normal(0.0, self.noise, self.n_samples)

    def frames(self) -> Iterator[Frame]:
        """Yield one frame per record, paced to `records_per_second` (unpaced if None)."""
        pacer = _Pacer(self.records_per_second)
        for k in range(self.n_records):
            pacer.wait(k + 1)
            yield Frame(
                DatasetChunk(
                    dataset_id=self.dataset.dataset_id,
                    seq=k,
                    region=(
                        IndexSlice(dim="record", start=k, stop=k + 1),
                        IndexSlice(dim="t", start=0, stop=self.n_samples),
                    ),
                    variables=("voltage",),
                    explicit_coords=("time",),
                    produced_at=datetime.now(UTC),
                    final=k == self.n_records - 1,
                ),
                {"voltage": self.record(k)[None, :], "time": self.time.copy()},
            )
