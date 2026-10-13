"""Step 1 schema slice: the `Dataset` stream contract (plan §4.2, ADR 0005, ADR 0008).

FROZEN (ADR 0015, against Probe 01 `docs/probes/01-stream-semantics.md`). Any change bumps `schema_version`,
adds a migration and a fixture at the old version, and carries an ADR (`packages/qdt-schemas/CLAUDE.md`).
History: `Dataset` v2 (ADR 0031) admits `source.kind = "analysis"` for a Dataset an analysis produced.

A stream is one `Dataset` (the definition), then ordered `DatasetChunk` envelopes and `Annotation`s.
Array payloads never live in these models: each chunk envelope travels as JSON next to a binary frame
(Arrow IPC) holding one array per name in `DatasetChunk.variables` and `DatasetChunk.explicit_coords`.
Wire framing (ADR 0010): `Dataset` and `Annotation` go as text messages (`StreamTextMessage`); each chunk
goes as one binary Arrow IPC message whose schema metadata holds the envelope under `CHUNK_METADATA_KEY`.

Coordinates are addressed two ways (Analysis 0001 §6.2):
- implicit — values follow from the definition (`linear`, `indexed`); a chunk carries only its index region;
- explicit — `streamed` coordinates whose values arrive in-band, in the payload of every chunk that covers them.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ._base import QdtModel

DType = Literal["float32", "float64", "int16", "int32", "int64", "uint16", "uint32"]
AttrValue = str | int | float | bool


class Dimension(QdtModel):
    """A named array axis."""

    name: str = Field(
        min_length=1, description="Dimension name, unique within the Dataset, e.g. 'gate_L'."
    )
    size: int | None = Field(
        default=None,
        ge=1,
        description="Length along this axis; None means unbounded (append-only, e.g. a free-running time series).",
    )


class LinearCoordinate(QdtModel):
    """Implicit coordinate: evenly spaced values from start to stop inclusive, one per index of its dimension."""

    kind: Literal["linear"] = Field(
        default="linear", description="Discriminator: implicit, evenly spaced."
    )
    name: str = Field(
        min_length=1, description="Coordinate name, unique among coordinates and data variables."
    )
    dim: str = Field(description="Name of the Dimension this coordinate labels.")
    unit: str = Field(
        description="Physical unit, e.g. 'V', 's', 'Hz'. Empty string for dimensionless."
    )
    start: float = Field(description="Value at index 0.")
    stop: float = Field(description="Value at the last index (inclusive).")
    num: int = Field(ge=1, description="Number of values; must equal the dimension size.")


class IndexedCoordinate(QdtModel):
    """Implicit coordinate: arbitrary values listed in the definition, one per index of its dimension."""

    kind: Literal["indexed"] = Field(
        default="indexed", description="Discriminator: implicit, listed values."
    )
    name: str = Field(
        min_length=1, description="Coordinate name, unique among coordinates and data variables."
    )
    dim: str = Field(description="Name of the Dimension this coordinate labels.")
    unit: str = Field(
        description="Physical unit, e.g. 'V', 's', 'Hz'. Empty string for dimensionless."
    )
    values: tuple[float, ...] = Field(
        min_length=1, description="Coordinate values; length must equal the dimension size."
    )


class StreamedCoordinate(QdtModel):
    """Explicit coordinate: values are not known up front and arrive in-band with each chunk (e.g. a scope time axis)."""

    kind: Literal["streamed"] = Field(
        default="streamed", description="Discriminator: explicit, values in the payload."
    )
    name: str = Field(
        min_length=1, description="Coordinate name, unique among coordinates and data variables."
    )
    dim: str = Field(description="Name of the Dimension this coordinate labels.")
    unit: str = Field(
        description="Physical unit, e.g. 'V', 's', 'Hz'. Empty string for dimensionless."
    )
    dtype: DType = Field(
        default="float64", description="Element type of the in-band coordinate array."
    )


Coordinate = Annotated[
    LinearCoordinate | IndexedCoordinate | StreamedCoordinate,
    Field(discriminator="kind"),
]


class DataVariable(QdtModel):
    """A named measured quantity laid out over one or more dimensions."""

    name: str = Field(
        min_length=1, description="Variable name, unique among coordinates and data variables."
    )
    dims: tuple[str, ...] = Field(
        min_length=1, description="Dimension names in array (row-major) order."
    )
    unit: str = Field(
        description="Physical unit, e.g. 'A', 'V'. Empty string for dimensionless or arbitrary units."
    )
    dtype: DType = Field(description="Element type of the payload array.")


class SourceDescriptor(QdtModel):
    """What kind of source produced a Dataset. Never identifies an instrument (rule 8)."""

    kind: Literal["live", "replay", "synthetic", "simulation", "registry", "analysis"] = Field(
        description=(
            "Source category. Consumers may branch on this; they may not learn the producing instrument. "
            "analysis: produced by an analysis method from other data (ADR 0031)."
        )
    )
    label: str = Field(
        default="", description="Human-readable label for display, e.g. 'synthetic stability map'."
    )
    registry_ref: str | None = Field(
        default=None,
        description="Registry reference when the Dataset is addressable in the registry (Step 3); None otherwise.",
    )


class Dataset(QdtModel):
    """xarray-shaped definition of a stream: dimensions, coordinates, variables, attributes, source."""

    schema_version: int = Field(
        default=2,
        description=(
            "Per-object-type schema version; bumps only on breaking changes. Readers upgrade on load via "
            "migrations.py. 2: `source.kind` admits 'analysis' (ADR 0031)."
        ),
    )
    dataset_id: str = Field(
        min_length=1, description="Unique id; every chunk and annotation refers to it."
    )
    name: str = Field(description="Human-readable name.")
    dims: tuple[Dimension, ...] = Field(
        min_length=1, description="Dimensions, in no particular order."
    )
    coords: tuple[Coordinate, ...] = Field(
        default=(), description="Coordinates labelling the dimensions."
    )
    data_vars: tuple[DataVariable, ...] = Field(min_length=1, description="Measured variables.")
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict, description="Free-form scalar metadata."
    )
    source: SourceDescriptor = Field(description="What kind of source produced this Dataset.")
    created_at: datetime = Field(
        description="When the producer created the definition (timezone-aware)."
    )

    @model_validator(mode="after")
    def _consistent(self) -> "Dataset":
        sizes = {d.name: d.size for d in self.dims}
        if len(sizes) != len(self.dims):
            raise ValueError("dimension names must be unique")
        names = [c.name for c in self.coords] + [v.name for v in self.data_vars]
        if len(set(names)) != len(names):
            raise ValueError("coordinate and data variable names must be unique together")
        for c in self.coords:
            if c.dim not in sizes:
                raise ValueError(f"coordinate {c.name!r} labels unknown dimension {c.dim!r}")
            n = (
                c.num
                if isinstance(c, LinearCoordinate)
                else len(c.values)
                if isinstance(c, IndexedCoordinate)
                else None
            )
            if n is not None and n != sizes[c.dim]:
                raise ValueError(
                    f"coordinate {c.name!r} has {n} values but dimension {c.dim!r} has size {sizes[c.dim]}"
                )
        for v in self.data_vars:
            if len(set(v.dims)) != len(v.dims):
                raise ValueError(f"variable {v.name!r} repeats a dimension")
            unknown = set(v.dims) - set(sizes)
            if unknown:
                raise ValueError(f"variable {v.name!r} uses unknown dimensions {sorted(unknown)}")
        return self

    def payload_shapes(self, chunk: "DatasetChunk") -> dict[str, tuple[int, ...]]:
        """Validate `chunk` against this definition; return the expected array shape per payload name."""
        if chunk.dataset_id != self.dataset_id:
            raise ValueError(f"chunk belongs to {chunk.dataset_id!r}, not {self.dataset_id!r}")
        sizes = {d.name: d.size for d in self.dims}
        extent = {}
        for s in chunk.region:
            if s.dim not in sizes:
                raise ValueError(f"region uses unknown dimension {s.dim!r}")
            if sizes[s.dim] is not None and s.stop > sizes[s.dim]:
                raise ValueError(f"region {s.dim}[{s.start}:{s.stop}] exceeds size {sizes[s.dim]}")
            extent[s.dim] = s.stop - s.start
        variables = {v.name: v for v in self.data_vars}
        shapes = {}
        for name in chunk.variables:
            if name not in variables:
                raise ValueError(f"chunk carries unknown variable {name!r}")
            if set(variables[name].dims) != set(extent):
                raise ValueError(
                    f"variable {name!r} spans {variables[name].dims}; region spans {tuple(extent)}"
                )
            shapes[name] = tuple(extent[d] for d in variables[name].dims)
        streamed = {
            c.name: c for c in self.coords if isinstance(c, StreamedCoordinate) and c.dim in extent
        }
        if set(chunk.explicit_coords) != set(streamed):
            raise ValueError(
                f"chunk must carry exactly the streamed coordinates of its region {sorted(streamed)}, "
                f"got {sorted(chunk.explicit_coords)}"
            )
        for name in chunk.explicit_coords:
            shapes[name] = (extent[streamed[name].dim],)
        return shapes

    def check_annotation(self, annotation: "Annotation") -> None:
        """Raise ValueError unless `annotation` decorates this Dataset in its coordinate system."""
        if annotation.dataset_id != self.dataset_id:
            raise ValueError(
                f"annotation belongs to {annotation.dataset_id!r}, not {self.dataset_id!r}"
            )
        unknown = set(annotation.coords) - {c.name for c in self.coords}
        if unknown:
            raise ValueError(f"annotation uses unknown coordinates {sorted(unknown)}")


class IndexSlice(QdtModel):
    """Half-open index range [start, stop) along one dimension."""

    dim: str = Field(description="Dimension name.")
    start: int = Field(ge=0, description="First index covered.")
    stop: int = Field(description="One past the last index covered; must exceed start.")

    @model_validator(mode="after")
    def _nonempty(self) -> "IndexSlice":
        if self.stop <= self.start:
            raise ValueError(f"empty slice {self.dim}[{self.start}:{self.stop}]")
        return self


class DatasetChunk(QdtModel):
    """Envelope for one partial update: which hyperrectangle of the Dataset the accompanying binary payload fills."""

    dataset_id: str = Field(description="The Dataset this chunk belongs to.")
    seq: int = Field(
        ge=0,
        description="Position in the stream, from 0, contiguous; consumers apply chunks in seq order.",
    )
    region: tuple[IndexSlice, ...] = Field(
        min_length=1,
        description="Index hyperrectangle filled by this chunk, one slice per dimension of its variables.",
    )
    variables: tuple[str, ...] = Field(
        min_length=1,
        description="Data variables in the payload; each array has the region's shape in the variable's dim order.",
    )
    explicit_coords: tuple[str, ...] = Field(
        default=(),
        description="Streamed coordinates in the payload; each is 1-D over its dimension's slice. Empty when all are implicit.",
    )
    produced_at: datetime = Field(
        description="When the producer emitted the chunk (timezone-aware); used for latency."
    )
    final: bool = Field(
        default=False,
        description="True on the last chunk of the Dataset; the stream is then complete.",
    )

    @model_validator(mode="after")
    def _unique(self) -> "DatasetChunk":
        dims = [s.dim for s in self.region]
        if len(set(dims)) != len(dims):
            raise ValueError("region repeats a dimension")
        names = self.variables + self.explicit_coords
        if len(set(names)) != len(names):
            raise ValueError("payload names must be unique")
        return self


class Annotation(QdtModel):
    """An overlay (marker, line, region, fitted curve) in the coordinate system of the Dataset it decorates."""

    annotation_id: str = Field(
        min_length=1, description="Unique id; re-sending an id replaces that annotation."
    )
    dataset_id: str = Field(description="The Dataset this annotation decorates.")
    kind: Literal["marker", "line", "polyline", "region", "curve"] = Field(
        description="Geometry: marker = one point, line = two, polyline/curve = many, region = closed polygon."
    )
    coords: tuple[str, ...] = Field(
        min_length=1,
        description="Coordinate names giving the meaning of each component of every point.",
    )
    points: tuple[tuple[float, ...], ...] = Field(
        min_length=1,
        description="Vertices in data coordinates; each has one value per entry in `coords`.",
    )
    label: str = Field(default="", description="Display label.")
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict, description="Free-form scalar metadata, e.g. fit parameters."
    )

    @model_validator(mode="after")
    def _geometry(self) -> "Annotation":
        if any(len(p) != len(self.coords) for p in self.points):
            raise ValueError("every point needs one value per coordinate")
        need = {"marker": 1, "line": 2}.get(self.kind)
        if need is not None and len(self.points) != need:
            raise ValueError(f"{self.kind} needs exactly {need} point(s)")
        if self.kind == "region" and len(self.points) < 3:
            raise ValueError("region needs at least 3 points")
        return self


class DatasetMessage(QdtModel):
    """Wire text message announcing a Dataset; precedes every chunk and annotation for it (ADR 0010)."""

    type: Literal["dataset"] = Field(default="dataset", description="Discriminator.")
    dataset: Dataset = Field(description="The definition being announced.")


class AnnotationMessage(QdtModel):
    """Wire text message carrying an Annotation for an already-announced Dataset (ADR 0010)."""

    type: Literal["annotation"] = Field(default="annotation", description="Discriminator.")
    annotation: Annotation = Field(description="The annotation being added or replaced.")


StreamTextMessage = Annotated[DatasetMessage | AnnotationMessage, Field(discriminator="type")]

CHUNK_METADATA_KEY = "qdt.chunk"
"""Arrow schema-metadata key holding the `DatasetChunk` JSON in a binary wire message (ADR 0010)."""
