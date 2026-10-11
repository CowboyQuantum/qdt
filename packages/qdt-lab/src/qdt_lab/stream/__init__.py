"""Dataset stream: sources that emit `Frame`s, and assembly back into xarray (Step 1).

A `Frame` is the in-process form of one stream message: the JSON-able `DatasetChunk` envelope plus the
arrays its binary payload carries (ADR 0008). Arrow IPC encoding belongs to the stream server.
"""

from .assemble import assemble
from .frame import Frame
from .synthetic import SyntheticMap, SyntheticRecords

__all__ = ["Frame", "SyntheticMap", "SyntheticRecords", "assemble"]
