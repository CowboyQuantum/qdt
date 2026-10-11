"""Rebuild an `xarray.Dataset` from a definition and its frames — the reference consumer."""

from collections.abc import Iterable

import numpy as np
import xarray as xr

from qdt_schemas.data import Dataset, IndexedCoordinate, LinearCoordinate

from .frame import Frame


def assemble(dataset: Dataset, frames: Iterable[Frame]) -> xr.Dataset:
    """Apply frames in seq order into dense arrays. Unwritten cells stay NaN (or 0 for integer dtypes).

    Unbounded dimensions are sized by the largest index the frames reach.
    """
    frames = sorted(frames, key=lambda f: f.chunk.seq)
    for f in frames:
        f.check(dataset)
    sizes = {d.name: d.size or 0 for d in dataset.dims}
    unbounded = {d.name for d in dataset.dims if d.size is None}
    for f in frames:
        for s in f.chunk.region:
            if s.dim in unbounded:
                sizes[s.dim] = max(sizes[s.dim], s.stop)

    data = {}
    for v in dataset.data_vars:
        dt = np.dtype(v.dtype)
        fill = np.nan if dt.kind == "f" else 0
        data[v.name] = np.full([sizes[d] for d in v.dims], fill, dtype=dt)
    streamed = {}
    for c in dataset.coords:
        if c.kind == "streamed":
            dt = np.dtype(c.dtype)
            streamed[c.name] = (
                c.dim,
                np.full(sizes[c.dim], np.nan if dt.kind == "f" else 0, dtype=dt),
            )

    for f in frames:
        index = {s.dim: slice(s.start, s.stop) for s in f.chunk.region}
        for name in f.chunk.variables:
            dims = next(v.dims for v in dataset.data_vars if v.name == name)
            data[name][tuple(index[d] for d in dims)] = f.arrays[name]
        for name in f.chunk.explicit_coords:
            dim, values = streamed[name]
            values[index[dim]] = f.arrays[name]

    coords = {}
    for c in dataset.coords:
        if isinstance(c, LinearCoordinate):
            values = np.linspace(c.start, c.stop, c.num)
        elif isinstance(c, IndexedCoordinate):
            values = np.asarray(c.values)
        else:
            values = streamed[c.name][1]
        coords[c.name] = xr.Variable(c.dim, values, attrs={"units": c.unit})
    variables = {
        v.name: xr.Variable(v.dims, data[v.name], attrs={"units": v.unit})
        for v in dataset.data_vars
    }
    attrs = dict(dataset.attrs) | {"dataset_id": dataset.dataset_id, "name": dataset.name}
    return xr.Dataset(variables, coords=coords, attrs=attrs)
