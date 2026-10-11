"""Reference Python client for the stream: decodes wire messages back into schema objects and frames.

This is the "live-mock" consumer used by the source-equivalence tests; Flight Deck implements the same
decoding in TypeScript.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from websockets.asyncio.client import connect

from qdt_schemas.data import Annotation, AnnotationMessage, Dataset, DatasetMessage

from .frame import Frame
from .wire import decode_chunk, decode_text, read_chunk_envelope


async def subscribe(url: str) -> AsyncIterator[Dataset | Annotation | Frame]:
    """Yield Datasets, Annotations and Frames in wire order until the server closes."""
    datasets: dict[str, Dataset] = {}
    async with connect(url, max_size=None, compression=None) as ws:
        async for message in ws:
            if isinstance(message, str):
                msg = decode_text(message)
                if isinstance(msg, DatasetMessage):
                    datasets[msg.dataset.dataset_id] = msg.dataset
                    yield msg.dataset
                elif isinstance(msg, AnnotationMessage):
                    yield msg.annotation
            else:
                dataset_id = read_chunk_envelope(message).dataset_id
                if dataset_id not in datasets:
                    raise ValueError(f"chunk for unannounced dataset {dataset_id!r}")
                yield decode_chunk(message, datasets[dataset_id])


@dataclass
class Received:
    """Everything received for one Dataset."""

    dataset: Dataset
    frames: list[Frame] = field(default_factory=list)
    annotations: list[Annotation] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return bool(self.frames) and self.frames[-1].chunk.final


async def collect(url: str, n_datasets: int = 1, timeout: float = 30.0) -> dict[str, Received]:
    """Subscribe until `n_datasets` Datasets have each received their final chunk."""
    received: dict[str, Received] = {}

    async def run() -> None:
        async for item in subscribe(url):
            if isinstance(item, Dataset):
                received[item.dataset_id] = Received(item)
            elif isinstance(item, Annotation):
                received[item.dataset_id].annotations.append(item)
            else:
                received[item.chunk.dataset_id].frames.append(item)
            if len(received) >= n_datasets and all(r.complete for r in received.values()):
                return

    await asyncio.wait_for(run(), timeout)
    return received
