"""In-process stream message: envelope + payload arrays."""

from collections.abc import Mapping
from typing import NamedTuple

import numpy as np

from qdt_schemas.data import Dataset, DatasetChunk


class Frame(NamedTuple):
    """One `DatasetChunk` envelope and its payload, keyed by variable / explicit-coordinate name."""

    chunk: DatasetChunk
    arrays: Mapping[str, np.ndarray]

    def check(self, dataset: Dataset) -> None:
        """Raise ValueError unless the payload matches what `dataset` says this chunk carries."""
        expected = dataset.payload_shapes(self.chunk)
        if set(self.arrays) != set(expected):
            raise ValueError(f"payload names {sorted(self.arrays)} != expected {sorted(expected)}")
        dtypes = {v.name: v.dtype for v in dataset.data_vars}
        dtypes |= {c.name: c.dtype for c in dataset.coords if c.kind == "streamed"}
        for name, shape in expected.items():
            a = self.arrays[name]
            if a.shape != shape:
                raise ValueError(f"{name!r} has shape {a.shape}, expected {shape}")
            if a.dtype != np.dtype(dtypes[name]):
                raise ValueError(f"{name!r} has dtype {a.dtype}, expected {dtypes[name]}")
