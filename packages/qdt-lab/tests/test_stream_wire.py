"""Wire encoding (ADR 0010): text messages and binary Arrow chunks round-trip exactly."""

import json

import numpy as np
import pyarrow as pa
import pytest

from qdt_lab.stream import (
    Frame,
    SyntheticMap,
    SyntheticRecords,
    decode_chunk,
    decode_text,
    encode_chunk,
    encode_text,
)
from qdt_schemas.data import CHUNK_METADATA_KEY, Annotation, AnnotationMessage, DatasetMessage


@pytest.mark.parametrize("ppc", [5, 32, 96], ids=["partial", "line", "rows"])
def test_map_chunk_round_trips_exactly(ppc):
    src = SyntheticMap(n_outer=6, n_inner=32, points_per_chunk=ppc, points_per_second=None)
    for frame in src.frames():
        back = decode_chunk(encode_chunk(frame), src.dataset)
        assert back.chunk == frame.chunk
        assert back.arrays.keys() == frame.arrays.keys()
        for name, a in frame.arrays.items():
            assert back.arrays[name].dtype == a.dtype
            np.testing.assert_array_equal(back.arrays[name], a)


def test_explicit_coordinate_rides_in_the_same_binary_message():
    src = SyntheticRecords(n_samples=100, n_records=1, records_per_second=None)
    frame = next(src.frames())
    back = decode_chunk(encode_chunk(frame), src.dataset)
    np.testing.assert_array_equal(back.arrays["time"], src.time)
    assert back.arrays["voltage"].shape == (1, 100)


def test_binary_message_is_plain_arrow_ipc_with_json_envelope():
    """What a non-Python consumer (Flight Deck) sees: one batch, one row, list columns, JSON metadata."""
    src = SyntheticMap(n_outer=2, n_inner=8, points_per_second=None)
    frame = next(src.frames())
    reader = pa.ipc.open_stream(encode_chunk(frame))
    envelope = json.loads(reader.schema.metadata[CHUNK_METADATA_KEY.encode()])
    assert envelope["seq"] == 0 and envelope["variables"] == ["signal"]
    batch = reader.read_all()
    assert batch.num_rows == 1
    assert batch.schema.field("signal").type == pa.list_(pa.float32())
    assert (
        batch.column("signal")[0].values.to_numpy().tolist()
        == frame.arrays["signal"].ravel().tolist()
    )


def test_decode_rejects_payload_that_disagrees_with_the_definition():
    src = SyntheticMap(n_outer=2, n_inner=8, points_per_second=None)
    chunk = next(src.frames()).chunk
    bad = Frame(
        chunk, {"signal": np.zeros((1, 8), np.float64)}
    )  # wrong dtype, bypassing Frame.check
    with pytest.raises(ValueError, match="dtype"):
        decode_chunk(encode_chunk(bad), src.dataset)


def test_text_messages_round_trip_through_the_union():
    src = SyntheticMap(n_outer=2, n_inner=8, points_per_second=None)
    d = DatasetMessage(dataset=src.dataset)
    assert decode_text(encode_text(d)) == d
    a = AnnotationMessage(
        annotation=Annotation(
            annotation_id="x",
            dataset_id=src.dataset.dataset_id,
            kind="marker",
            coords=("V_inner", "V_outer"),
            points=((0.0, 0.0),),
        )
    )
    assert decode_text(encode_text(a)) == a
    assert json.loads(encode_text(a))["type"] == "annotation"
