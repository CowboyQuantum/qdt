"""Replay a stored `qdt-hdf5-v1` payload as a stream (Step 3): how registry records reach Flight Deck.

The Dataset is re-announced with `source.kind = "registry"` and `source.registry_ref` set, which is the
only change: same id, dims, coordinates and annotations. Each data variable is sent in slabs along its
first dimension (about `max_points` values per frame), carrying the streamed coordinates its region
covers. The last frame is `final`. No database is touched here (rule 4): the caller hands over a
`Payload`, e.g. from `Registry.payload(record_id)`.
"""

import math
from collections.abc import Iterator
from datetime import UTC, datetime

from qdt_schemas.data import DatasetChunk, IndexSlice, SourceDescriptor, StreamedCoordinate
from qdt_schemas.payload_hdf5 import Payload

from .frame import Frame


class PayloadSource:
    """A `Source` over a finished payload; `annotations` are announced before the frames."""

    def __init__(self, payload: Payload, registry_ref: str, max_points: int = 1 << 20) -> None:
        d = payload.dataset
        self.dataset = d.model_copy(
            update={
                "source": SourceDescriptor(
                    kind="registry", label=d.source.label or d.name, registry_ref=registry_ref
                )
            }
        )
        self.annotations = payload.annotations
        self._arrays = payload.arrays
        self._max_points = max_points

    def frames(self) -> Iterator[Frame]:
        d = self.dataset
        streamed = {c.dim: c.name for c in d.coords if isinstance(c, StreamedCoordinate)}
        plan: list[tuple[str, int, int]] = []
        for v in d.data_vars:
            a = self._arrays[v.name]
            row = math.prod(a.shape[1:]) or 1
            step = max(1, self._max_points // row)
            plan += [(v.name, i, min(i + step, a.shape[0])) for i in range(0, a.shape[0], step)]
        dims = {v.name: v.dims for v in d.data_vars}
        for seq, (name, start, stop) in enumerate(plan):
            a = self._arrays[name]
            region = tuple(
                IndexSlice(dim=dim, start=start, stop=stop)
                if k == 0
                else IndexSlice(dim=dim, start=0, stop=a.shape[k])
                for k, dim in enumerate(dims[name])
            )
            coords = {
                streamed[s.dim]: self._arrays[streamed[s.dim]][s.start : s.stop]
                for s in region
                if s.dim in streamed
            }
            yield Frame(
                DatasetChunk(
                    dataset_id=d.dataset_id,
                    seq=seq,
                    region=region,
                    variables=(name,),
                    explicit_coords=tuple(coords),
                    produced_at=datetime.now(UTC),
                    final=seq == len(plan) - 1,
                ),
                {name: a[start:stop], **coords},
            )
