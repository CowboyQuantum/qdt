"""Simulated waveform terminals."""

import time
from collections.abc import Iterator
from datetime import UTC, datetime

import numpy as np

from qdt_schemas.data import Dataset, DatasetChunk, IndexSlice, LinearCoordinate

from ..stream.frame import Frame


class SimulatedWaveformSource:
    """Accepts 1-D waveforms and remembers what is playing per channel (`playing`)."""

    def __init__(self) -> None:
        self.playing: dict[str, tuple[np.ndarray, float]] = {}

    def play(self, channel: str, samples: np.ndarray, sample_rate: float) -> None:
        a = np.asarray(samples, dtype=np.float64)
        if a.ndim != 1 or a.size == 0:
            raise ValueError(f"waveform must be a non-empty 1-D array, got shape {a.shape}")
        if not sample_rate > 0:
            raise ValueError(f"sample_rate must be positive, got {sample_rate}")
        self.playing[channel] = (a.copy(), float(sample_rate))

    def stop(self, channel: str) -> None:
        self.playing.pop(channel, None)


class SimulatedWaveformSense:
    """Fills records on the declared time grid: a damped ring-down after the start of the record plus
    Gaussian noise, deterministic in (seed, record index). One whole record per frame, exactly on the
    declared `LinearCoordinate` (ADR 0015: alignment is the producer's job). An unbounded record
    dimension yields `max_records` records."""

    def __init__(
        self,
        noise: float = 0.01,
        seed: int = 0,
        max_records: int = 8,
        records_per_second: float | None = None,
    ) -> None:
        self.noise, self.seed = noise, seed
        self.max_records, self.records_per_second = max_records, records_per_second

    def arm(self, channel: str, dataset: Dataset, variable: str) -> "_RecordSource":
        v = next((v for v in dataset.data_vars if v.name == variable), None)
        if v is None:
            raise ValueError(f"dataset has no data variable {variable!r}")
        if len(v.dims) != 2:
            raise ValueError(f"variable {variable!r} must be (record, time); has dims {v.dims}")
        record_dim, time_dim = v.dims
        axis = [c for c in dataset.coords if c.dim == time_dim and isinstance(c, LinearCoordinate)]
        if len(axis) != 1:
            raise ValueError(
                f"variable {variable!r} needs exactly one declared LinearCoordinate on {time_dim!r} "
                "(ADR 0015: records land on the declared grid)"
            )
        n_records = next(d.size for d in dataset.dims if d.name == record_dim) or self.max_records
        times = np.linspace(axis[0].start, axis[0].stop, axis[0].num)
        return _RecordSource(self, dataset, v.name, v.dtype, record_dim, time_dim, n_records, times)


class _RecordSource:
    """The `Source` a `SimulatedWaveformSense.arm` returns."""

    def __init__(
        self,
        sense: SimulatedWaveformSense,
        dataset: Dataset,
        variable: str,
        dtype: str,
        record_dim: str,
        time_dim: str,
        n_records: int,
        times: np.ndarray,
    ) -> None:
        self._sense, self.dataset, self._variable, self._dtype = sense, dataset, variable, dtype
        self._record_dim, self._time_dim, self._n_records = record_dim, time_dim, n_records
        self._times = times

    def record(self, k: int) -> np.ndarray:
        """Record `k`: ring-down from the start of the declared axis, deterministic in (seed, k)."""
        t = self._times - self._times[0]
        span = t[-1] if t[-1] > 0 else 1.0
        clean = np.exp(-t / (span / 4)) * np.cos(2 * np.pi * 8 * t / span)
        rng = np.random.default_rng([self._sense.seed, k])
        return clean + rng.normal(0.0, self._sense.noise, t.size)

    def frames(self) -> Iterator[Frame]:
        t0 = time.perf_counter()
        n = self._times.size
        for k in range(self._n_records):
            if self._sense.records_per_second:
                delay = t0 + (k + 1) / self._sense.records_per_second - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
            yield Frame(
                DatasetChunk(
                    dataset_id=self.dataset.dataset_id,
                    seq=k,
                    region=(
                        IndexSlice(dim=self._record_dim, start=k, stop=k + 1),
                        IndexSlice(dim=self._time_dim, start=0, stop=n),
                    ),
                    variables=(self._variable,),
                    produced_at=datetime.now(UTC),
                    final=k == self._n_records - 1,
                ),
                {self._variable: self.record(k)[None, :].astype(self._dtype)},
            )
