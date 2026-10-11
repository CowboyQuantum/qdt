"""Recordings of the wire stream and the replay source that plays them back (ADR 0010).

A recording (`.qdtrec`) is the magic line `QDTREC1\\n` followed by records of
`kind (1 byte: b"T" text, b"B" binary) | length (uint64 little-endian) | message bytes`,
i.e. exactly what crossed the wire, in order. Replay is therefore byte-faithful to a live stream.
"""

import struct
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

from qdt_schemas.data import Annotation, AnnotationMessage, Dataset, DatasetMessage

from .frame import Frame
from .source import Source
from .wire import decode_chunk, decode_text, encode_chunk, encode_text

MAGIC = b"QDTREC1\n"
_HEADER = struct.Struct("<cQ")


def write_recording(
    path: str | Path, source: Source, annotations: Iterable[Annotation] = ()
) -> Path:
    """Record `source` (unpaced) to `path`: Dataset message, annotations, then every chunk."""
    path = Path(path)
    with path.open("wb") as f:
        f.write(MAGIC)

        def put(kind: bytes, data: bytes) -> None:
            f.write(_HEADER.pack(kind, len(data)))
            f.write(data)

        put(b"T", encode_text(DatasetMessage(dataset=source.dataset)).encode())
        for a in annotations:
            source.dataset.check_annotation(a)
            put(b"T", encode_text(AnnotationMessage(annotation=a)).encode())
        for frame in source.frames():
            put(b"B", encode_chunk(frame))
    return path


def read_recording(path: str | Path) -> Iterator[str | bytes]:
    """Yield the raw wire messages of a recording in order (str for text, bytes for binary)."""
    data = Path(path).read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError(f"{path} is not a qdt recording")
    pos = len(MAGIC)
    while pos < len(data):
        kind, length = _HEADER.unpack_from(data, pos)
        pos += _HEADER.size
        body = data[pos : pos + length]
        if len(body) != length:
            raise ValueError(f"{path} is truncated")
        pos += length
        if kind == b"T":
            yield body.decode()
        elif kind == b"B":
            yield body
        else:
            raise ValueError(f"{path}: unknown record kind {kind!r}")


class ReplaySource:
    """A `Source` over a one-Dataset recording, optionally paced by the recorded `produced_at` times."""

    def __init__(self, path: str | Path, speed: float | None = None) -> None:
        """`speed` scales recorded timing (1.0 = as recorded, 2.0 = twice as fast); None is unpaced."""
        self.path, self.speed = Path(path), speed
        messages = list(read_recording(self.path))
        if not messages or not isinstance(messages[0], str):
            raise ValueError(f"{path}: recording must start with a Dataset message")
        first = decode_text(messages[0])
        if not isinstance(first, DatasetMessage):
            raise ValueError(f"{path}: recording must start with a Dataset message")  # noqa: TRY004
        self.dataset: Dataset = first.dataset
        self.annotations: list[Annotation] = []
        self._chunks: list[bytes] = []
        for m in messages[1:]:
            if isinstance(m, bytes):
                self._chunks.append(m)
                continue
            msg = decode_text(m)
            if not isinstance(msg, AnnotationMessage):
                raise ValueError(f"{path}: recordings hold exactly one Dataset")  # noqa: TRY004
            self.dataset.check_annotation(msg.annotation)
            self.annotations.append(msg.annotation)

    def frames(self) -> Iterator[Frame]:
        t_wall = t_rec = None
        for data in self._chunks:
            frame = decode_chunk(data, self.dataset)
            if self.speed is not None:
                stamp = frame.chunk.produced_at.timestamp()
                if t_wall is None:
                    t_wall, t_rec = time.perf_counter(), stamp
                delay = t_wall + (stamp - t_rec) / self.speed - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
            yield frame
