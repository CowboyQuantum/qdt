"""Payload spec `qdt-hdf5-v1`: one finished `Dataset` at rest in one HDF5 file (ADR 0001, ADR 0023).
Frozen by ADR 0028: a layout change is a new payload type, never an edit of v1.

Layout (names are the spec; a change is a new payload type, not an edit):

    /                       attrs: qdt_payload_type = "qdt-hdf5-v1"
                                   qdt_dataset      = Dataset, canonical JSON
                                   qdt_annotations  = JSON list of Annotations (may be "[]")
                                   qdt_plan         = ExecutionPlan, canonical JSON   (optional)
                                   qdt_stand        = StandConfig, canonical JSON     (optional)
    /data_vars/<name>       one array per DataVariable, declared dtype, shape over its dims in order;
                            attrs: dims (names), unit
    /coords/<name>          one 1-D array per coordinate, implicit ones materialised for HDF5 tools;
                            attrs: dim, unit, kind

The JSON attributes are authoritative; arrays must agree with them. Objects are read back through
`migrations.load`, so old files stay readable. h5py and numpy are imported lazily: `qdt-schemas[hdf5]`.
"""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from .activity import ExecutionPlan
from .data import Annotation, Dataset, IndexedCoordinate, LinearCoordinate, StreamedCoordinate
from .stand import StandConfig

if TYPE_CHECKING:
    import numpy as np

PAYLOAD_TYPE = "qdt-hdf5-v1"


class Payload(NamedTuple):
    """A payload file read back: the definition, its arrays, and the documents stored with it."""

    dataset: Dataset
    arrays: dict[str, "np.ndarray"]
    """Data variables and streamed coordinates by name."""
    annotations: tuple[Annotation, ...]
    plan: ExecutionPlan | None
    stand: StandConfig | None


def _expected_shapes(dataset: Dataset, arrays: Mapping[str, Any]) -> dict[str, tuple[int, ...]]:
    """Validate `arrays` against `dataset`; return the resolved dim sizes as one tuple per name."""
    sizes: dict[str, int | None] = {d.name: d.size for d in dataset.dims}
    named = {v.name: v.dims for v in dataset.data_vars} | {
        c.name: (c.dim,) for c in dataset.coords if isinstance(c, StreamedCoordinate)
    }
    missing = set(named) - set(arrays)
    if missing:
        raise ValueError(f"payload lacks arrays {sorted(missing)}")
    extra = set(arrays) - set(named)
    if extra:
        raise ValueError(
            f"arrays {sorted(extra)} are neither data variables nor streamed coordinates"
        )
    resolved = dict(sizes)
    for name, dims in named.items():
        shape = arrays[name].shape
        if len(shape) != len(dims):
            raise ValueError(f"{name!r} has {len(shape)} axes; declared over {dims}")
        for d, n in zip(dims, shape, strict=True):
            if resolved[d] is None:
                resolved[d] = n
            elif resolved[d] != n:
                raise ValueError(f"{name!r} has {d}={n}; expected {resolved[d]}")
    return {name: tuple(resolved[d] for d in dims) for name, dims in named.items()}


def write_payload(
    path: str | Path,
    dataset: Dataset,
    arrays: Mapping[str, "np.ndarray"],
    *,
    annotations: Sequence[Annotation] = (),
    plan: ExecutionPlan | None = None,
    stand: StandConfig | None = None,
) -> None:
    """Write a `qdt-hdf5-v1` file. Raises ValueError when arrays disagree with the definition (names,
    rank, sizes, dtype) or an annotation belongs to another Dataset. Overwrites nothing: fails if
    `path` exists, so a written payload is immutable."""
    import h5py
    import numpy as np

    _expected_shapes(dataset, arrays)
    for v in dataset.data_vars:
        if np.dtype(arrays[v.name].dtype) != np.dtype(v.dtype):
            raise ValueError(f"{v.name!r} is {arrays[v.name].dtype}; declared {v.dtype}")
    for a in annotations:
        dataset.check_annotation(a)
    if plan is not None and plan.dataset != dataset:
        raise ValueError("plan declares a different Dataset")
    if plan is not None and stand is not None and plan.stand_id != stand.stand_id:
        raise ValueError(f"plan was compiled for stand {plan.stand_id!r}, not {stand.stand_id!r}")

    with h5py.File(path, "x") as f:
        f.attrs["qdt_payload_type"] = PAYLOAD_TYPE
        f.attrs["qdt_dataset"] = dataset.canonical_json()
        f.attrs["qdt_annotations"] = json.dumps(
            [json.loads(a.canonical_json()) for a in annotations], sort_keys=True
        )
        if plan is not None:
            f.attrs["qdt_plan"] = plan.canonical_json()
        if stand is not None:
            f.attrs["qdt_stand"] = stand.canonical_json()
        group = f.create_group("data_vars")
        for v in dataset.data_vars:
            ds = group.create_dataset(v.name, data=np.asarray(arrays[v.name]))
            ds.attrs["dims"] = list(v.dims)
            ds.attrs["unit"] = v.unit
        group = f.create_group("coords")
        for c in dataset.coords:
            if isinstance(c, LinearCoordinate):
                values = np.linspace(c.start, c.stop, c.num)
            elif isinstance(c, IndexedCoordinate):
                values = np.asarray(c.values, dtype=np.float64)
            else:
                values = np.asarray(arrays[c.name])
            ds = group.create_dataset(c.name, data=values)
            ds.attrs["dim"] = c.dim
            ds.attrs["unit"] = c.unit
            ds.attrs["kind"] = c.kind


def read_payload(path: str | Path) -> Payload:
    """Read a `qdt-hdf5-v1` file, upgrading stored objects to the current schema. Raises ValueError for
    another payload type or arrays that disagree with the stored definition."""
    import h5py
    import numpy as np

    from .migrations import load

    with h5py.File(path, "r") as f:
        kind = f.attrs.get("qdt_payload_type")
        if kind != PAYLOAD_TYPE:
            raise ValueError(f"not a {PAYLOAD_TYPE} payload: {kind!r}")
        dataset = load("Dataset", json.loads(f.attrs["qdt_dataset"]))
        annotations = tuple(load("Annotation", a) for a in json.loads(f.attrs["qdt_annotations"]))
        plan = (
            load("ExecutionPlan", json.loads(f.attrs["qdt_plan"]))
            if "qdt_plan" in f.attrs
            else None
        )
        stand = (
            load("StandConfig", json.loads(f.attrs["qdt_stand"]))
            if "qdt_stand" in f.attrs
            else None
        )
        arrays = {name: np.asarray(ds[()]) for name, ds in f["data_vars"].items()}
        for c in dataset.coords:
            if isinstance(c, StreamedCoordinate):
                arrays[c.name] = np.asarray(f["coords"][c.name][()])
    _expected_shapes(dataset, arrays)
    return Payload(dataset, arrays, annotations, plan, stand)
