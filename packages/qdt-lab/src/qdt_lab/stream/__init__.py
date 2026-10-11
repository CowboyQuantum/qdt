"""Dataset stream: sources, wire encoding, recordings, server and reference client (Step 1).

A `Frame` is the in-process form of one chunk: the JSON-able `DatasetChunk` envelope plus its arrays.
On the wire (ADR 0008, ADR 0010) text messages carry `Dataset`/`Annotation` JSON and each chunk is one
binary Arrow IPC message with the envelope in its schema metadata.
"""

from .assemble import assemble
from .client import Received, collect, subscribe
from .frame import Frame
from .replay import ReplaySource, read_recording, write_recording
from .server import StreamServer
from .source import Source
from .synthetic import SyntheticMap, SyntheticRecords
from .wire import decode_chunk, decode_text, encode_chunk, encode_text

__all__ = [
    "Frame",
    "Received",
    "ReplaySource",
    "Source",
    "StreamServer",
    "SyntheticMap",
    "SyntheticRecords",
    "assemble",
    "collect",
    "decode_chunk",
    "decode_text",
    "encode_chunk",
    "encode_text",
    "read_recording",
    "subscribe",
    "write_recording",
]
