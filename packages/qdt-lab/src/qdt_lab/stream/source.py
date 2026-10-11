"""The producer-side `Source` protocol: anything with a Dataset definition and an ordered frame iterator."""

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from qdt_schemas.data import Dataset

from .frame import Frame


@runtime_checkable
class Source(Protocol):
    """A producer of one Dataset. `frames()` yields in seq order and may block to pace itself."""

    dataset: Dataset

    def frames(self) -> Iterator[Frame]: ...
