from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from qdt_schemas.data import (
    Annotation,
    Dataset,
    DatasetChunk,
    DataVariable,
    Dimension,
    IndexedCoordinate,
    IndexSlice,
    LinearCoordinate,
    SourceDescriptor,
    StreamedCoordinate,
)

T0 = datetime(2026, 10, 11, tzinfo=UTC)


def stability_map(n_outer: int = 4, n_inner: int = 8) -> Dataset:
    """Implicit addressing: OPX-like 2D sweep, coordinates follow from the definition."""
    return Dataset(
        dataset_id="map",
        name="stability map",
        dims=(Dimension(name="gate_R", size=n_outer), Dimension(name="gate_L", size=n_inner)),
        coords=(
            LinearCoordinate(name="V_R", dim="gate_R", unit="V", start=-0.5, stop=0.5, num=n_outer),
            LinearCoordinate(name="V_L", dim="gate_L", unit="V", start=-1.0, stop=0.0, num=n_inner),
        ),
        data_vars=(
            DataVariable(name="I_sens", dims=("gate_R", "gate_L"), unit="A", dtype="float32"),
        ),
        source=SourceDescriptor(kind="synthetic"),
        created_at=T0,
    )


def scope_records(n_samples: int = 1000) -> Dataset:
    """Explicit addressing: scope-like records, time axis arrives in-band; record count unbounded."""
    return Dataset(
        dataset_id="trace",
        name="scope records",
        dims=(Dimension(name="record"), Dimension(name="t", size=n_samples)),
        coords=(StreamedCoordinate(name="time", dim="t", unit="s"),),
        data_vars=(DataVariable(name="V_in", dims=("record", "t"), unit="V", dtype="float64"),),
        source=SourceDescriptor(kind="live"),
        created_at=T0,
    )


def chunk(
    dataset_id: str, region: dict[str, tuple[int, int]], variables=("I_sens",), **kw
) -> DatasetChunk:
    return DatasetChunk(
        dataset_id=dataset_id,
        seq=kw.pop("seq", 0),
        region=tuple(IndexSlice(dim=d, start=a, stop=b) for d, (a, b) in region.items()),
        variables=variables,
        produced_at=T0,
        **kw,
    )


@pytest.mark.parametrize("make", [stability_map, scope_records])
def test_dataset_round_trips_json(make):
    ds = make()
    assert Dataset.model_validate_json(ds.model_dump_json()) == ds


def test_chunk_and_annotation_round_trip_json():
    c = chunk("map", {"gate_R": (1, 2), "gate_L": (0, 8)}, final=True)
    assert DatasetChunk.model_validate_json(c.model_dump_json()) == c
    a = Annotation(
        annotation_id="a",
        dataset_id="map",
        kind="line",
        coords=("V_L", "V_R"),
        points=((0, 0), (1, 1)),
    )
    assert Annotation.model_validate_json(a.model_dump_json()) == a


def test_implicit_line_chunk_shape_follows_variable_dim_order():
    ds = stability_map()
    # region listed inner-first on purpose: payload shape follows the variable's dims, not the region order
    c = chunk("map", {"gate_L": (0, 8), "gate_R": (2, 3)})
    assert ds.payload_shapes(c) == {"I_sens": (1, 8)}


def test_partial_line_chunk_is_addressable():
    ds = stability_map()
    assert ds.payload_shapes(chunk("map", {"gate_R": (3, 4), "gate_L": (5, 6)})) == {
        "I_sens": (1, 1)
    }


def test_explicit_chunk_carries_streamed_coordinate():
    ds = scope_records(1000)
    c = chunk(
        "trace",
        {"record": (41, 42), "t": (0, 1000)},
        variables=("V_in",),
        explicit_coords=("time",),
    )
    assert ds.payload_shapes(c) == {"V_in": (1, 1000), "time": (1000,)}


def test_streamed_coordinate_may_not_be_omitted_or_invented():
    ds = scope_records(1000)
    with pytest.raises(ValueError, match="streamed coordinates"):
        ds.payload_shapes(chunk("trace", {"record": (0, 1), "t": (0, 1000)}, variables=("V_in",)))
    with pytest.raises(ValueError, match="streamed coordinates"):
        stability_map().payload_shapes(
            chunk("map", {"gate_R": (0, 1), "gate_L": (0, 8)}, explicit_coords=("V_L",))
        )


@pytest.mark.parametrize(
    ("region", "variables", "match"),
    [
        ({"gate_R": (0, 1), "gate_L": (0, 9)}, ("I_sens",), "exceeds size"),
        ({"gate_R": (0, 1)}, ("I_sens",), "spans"),
        ({"gate_R": (0, 1), "gate_L": (0, 8)}, ("nope",), "unknown variable"),
        ({"gate_R": (0, 1), "other": (0, 1)}, ("I_sens",), "unknown dimension"),
    ],
)
def test_chunk_rejected_against_definition(region, variables, match):
    with pytest.raises(ValueError, match=match):
        stability_map().payload_shapes(chunk("map", region, variables=variables))


def test_chunk_for_other_dataset_rejected():
    with pytest.raises(ValueError, match="belongs to"):
        stability_map().payload_shapes(chunk("trace", {"gate_R": (0, 1), "gate_L": (0, 8)}))


def test_unbounded_dimension_accepts_any_index():
    ds = scope_records(10)
    c = chunk(
        "trace",
        {"record": (10**6, 10**6 + 1), "t": (0, 10)},
        variables=("V_in",),
        explicit_coords=("time",),
    )
    assert ds.payload_shapes(c)["V_in"] == (1, 10)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (
            {"dims": (Dimension(name="gate_R", size=4), Dimension(name="gate_R", size=8))},
            "dimension names",
        ),
        (
            {
                "coords": (
                    LinearCoordinate(name="V_R", dim="gate_R", unit="V", start=0, stop=1, num=5),
                )
            },
            "has 5 values",
        ),
        (
            {"coords": (IndexedCoordinate(name="V_R", dim="x", unit="V", values=(0.0,)),)},
            "unknown dimension",
        ),
        (
            {
                "coords": (
                    LinearCoordinate(name="I_sens", dim="gate_R", unit="V", start=0, stop=1, num=4),
                )
            },
            "unique together",
        ),
        (
            {
                "data_vars": (
                    DataVariable(name="I", dims=("gate_R", "gate_R"), unit="A", dtype="float32"),
                )
            },
            "repeats",
        ),
        (
            {"data_vars": (DataVariable(name="I", dims=("x",), unit="A", dtype="float32"),)},
            "unknown dimensions",
        ),
    ],
)
def test_inconsistent_definition_rejected(change, match):
    with pytest.raises(ValidationError, match=match):
        Dataset(**{**stability_map().model_dump(), **change})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"region": (IndexSlice(dim="a", start=0, stop=1), IndexSlice(dim="a", start=1, stop=2))},
        {"variables": ("I", "I")},
        {"seq": -1},
    ],
)
def test_malformed_chunk_rejected(kwargs):
    base = {
        "dataset_id": "map",
        "seq": 0,
        "region": (IndexSlice(dim="a", start=0, stop=1),),
        "variables": ("I",),
        "produced_at": T0,
    }
    with pytest.raises(ValidationError):
        DatasetChunk(**{**base, **kwargs})


def test_empty_slice_rejected():
    with pytest.raises(ValidationError, match="empty slice"):
        IndexSlice(dim="a", start=3, stop=3)


@pytest.mark.parametrize(
    ("kind", "points"),
    [
        ("marker", ((0, 0), (1, 1))),
        ("line", ((0, 0),)),
        ("region", ((0, 0), (1, 1))),
        ("polyline", ((0,),)),
    ],
)
def test_annotation_geometry_enforced(kind, points):
    with pytest.raises(ValidationError):
        Annotation(
            annotation_id="a", dataset_id="map", kind=kind, coords=("V_L", "V_R"), points=points
        )


def test_annotation_checked_against_dataset_coordinates():
    ds = stability_map()
    ok = Annotation(
        annotation_id="a", dataset_id="map", kind="marker", coords=("V_L", "V_R"), points=((0, 0),)
    )
    ds.check_annotation(ok)
    with pytest.raises(ValueError, match="unknown coordinates"):
        ds.check_annotation(ok.model_copy(update={"coords": ("V_L", "gate_R")}))


def test_source_descriptor_has_no_instrument_field():
    # rule 8: consumers learn the source kind, never the producing instrument
    assert set(SourceDescriptor.model_fields) == {"schema_version", "kind", "label", "registry_ref"}
    with pytest.raises(ValidationError):
        SourceDescriptor(kind="live", instrument="x")  # type: ignore[call-arg]
