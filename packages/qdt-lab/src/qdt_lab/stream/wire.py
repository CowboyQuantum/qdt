"""Wire encoding (ADR 0010): text messages are JSON, each chunk is one binary Arrow IPC message.

The binary message is an Arrow IPC stream holding one record batch with one row. Each payload array is a
`list<dtype>` column named after its variable / explicit coordinate, flattened row-major; its shape follows
from the envelope via `Dataset.payload_shapes`. The envelope JSON sits in the schema metadata under
`CHUNK_METADATA_KEY`, so a chunk is self-contained and needs no pairing with a separate text message.
"""

import numpy as np
import pyarrow as pa
from pydantic import TypeAdapter

from qdt_schemas.data import (
    CHUNK_METADATA_KEY,
    AnnotationMessage,
    Dataset,
    DatasetChunk,
    DatasetMessage,
    StreamTextMessage,
)

from .frame import Frame

_text = TypeAdapter(StreamTextMessage)


def encode_text(message: DatasetMessage | AnnotationMessage) -> str:
    return message.model_dump_json()


def decode_text(data: str | bytes) -> DatasetMessage | AnnotationMessage:
    return _text.validate_json(data)


def encode_chunk(frame: Frame) -> bytes:
    """Encode a frame as one Arrow IPC stream message. Payload order: variables, then explicit coords."""
    chunk = frame.chunk
    names = chunk.variables + chunk.explicit_coords
    columns = []
    for name in names:
        flat = pa.array(np.ascontiguousarray(frame.arrays[name]).ravel())
        columns.append(pa.ListArray.from_arrays(pa.array([0, len(flat)], pa.int32()), flat))
    schema = pa.schema(
        [pa.field(n, c.type) for n, c in zip(names, columns, strict=True)],
        metadata={CHUNK_METADATA_KEY: chunk.model_dump_json()},
    )
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema) as writer:
        writer.write_batch(pa.record_batch(columns, schema=schema))
    return sink.getvalue().to_pybytes()


def read_chunk_envelope(data: bytes) -> DatasetChunk:
    """Read only the envelope of a binary chunk message (no payload decode)."""
    schema = pa.ipc.open_stream(pa.py_buffer(data)).schema
    return DatasetChunk.model_validate_json(schema.metadata[CHUNK_METADATA_KEY.encode()])


def decode_chunk(data: bytes, dataset: Dataset) -> Frame:
    """Decode a binary chunk message against its (already announced) Dataset; validates the payload."""
    reader = pa.ipc.open_stream(pa.py_buffer(data))
    chunk = DatasetChunk.model_validate_json(reader.schema.metadata[CHUNK_METADATA_KEY.encode()])
    batch = reader.read_next_batch()
    shapes = dataset.payload_shapes(chunk)
    arrays = {}
    for name in batch.schema.names:
        if name not in shapes:
            raise ValueError(f"chunk payload carries unexpected array {name!r}")
        values = batch.column(name).values.to_numpy(zero_copy_only=False)
        arrays[name] = values.reshape(shapes[name])
    frame = Frame(chunk, arrays)
    frame.check(dataset)
    return frame
