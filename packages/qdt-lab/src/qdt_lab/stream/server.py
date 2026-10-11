"""WebSocket stream server (ADR 0008, ADR 0010).

Publishes Datasets, chunks and annotations to every connected client. Every message is kept in an
in-memory history, so a client that connects late first receives everything published so far and then
follows live. Each client sends at its own pace from the shared history; a slow client lags, it does not
slow the producer or other clients. Incoming client messages are ignored until the "up" edge (Step 6).
"""

import asyncio
import threading
from typing import Self

from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from qdt_schemas.data import Annotation, AnnotationMessage, Dataset, DatasetMessage

from .frame import Frame
from .source import Source
from .wire import encode_chunk, encode_text


class StreamServer:
    """Use as `async with StreamServer(port=0) as server: ...`; `server.url` is the bound address."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host, self.port = host, port
        self._history: list[str | bytes] = []
        self._datasets: dict[str, Dataset] = {}
        self._changed = asyncio.Event()
        self._server: Server | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    async def __aenter__(self) -> Self:
        self._loop = asyncio.get_running_loop()
        # permessage-deflate off: float payloads barely compress and deflate costs ~ms per MB (ADR 0010)
        self._server = await serve(self._handle, self.host, self.port, compression=None)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    # -- publishing (call on the event loop thread) -------------------------------------------------

    def publish_dataset(self, dataset: Dataset) -> None:
        if dataset.dataset_id in self._datasets:
            raise ValueError(f"dataset {dataset.dataset_id!r} already announced")
        self._datasets[dataset.dataset_id] = dataset
        self._append(encode_text(DatasetMessage(dataset=dataset)))

    def publish_annotation(self, annotation: Annotation) -> None:
        self._dataset(annotation.dataset_id).check_annotation(annotation)
        self._append(encode_text(AnnotationMessage(annotation=annotation)))

    def publish_frame(self, frame: Frame) -> None:
        frame.check(self._dataset(frame.chunk.dataset_id))
        self._append(encode_chunk(frame))

    async def feed(self, source: Source) -> None:
        """Announce `source.dataset` and any `source.annotations`, then publish its frames as they come.

        `frames()` may block to pace itself, so it runs in a worker thread, which also does the encoding;
        only the append to the history happens on the event loop.
        """
        self.publish_dataset(source.dataset)
        for annotation in getattr(source, "annotations", ()):
            self.publish_annotation(annotation)
        loop = asyncio.get_running_loop()
        done = asyncio.Event()
        error: list[BaseException] = []

        def work() -> None:
            try:
                for frame in source.frames():
                    frame.check(source.dataset)
                    data = encode_chunk(frame)
                    loop.call_soon_threadsafe(self._append, data)
            except BaseException as e:  # noqa: BLE001 — re-raised in the awaiting caller below
                error.append(e)
            finally:
                loop.call_soon_threadsafe(done.set)

        threading.Thread(target=work, name=f"feed-{source.dataset.dataset_id}", daemon=True).start()
        await done.wait()
        if error:
            raise error[0]

    # -- internals ----------------------------------------------------------------------------------

    def _dataset(self, dataset_id: str) -> Dataset:
        try:
            return self._datasets[dataset_id]
        except KeyError:
            raise ValueError(f"dataset {dataset_id!r} not announced") from None

    def _append(self, message: str | bytes) -> None:
        self._history.append(message)
        changed, self._changed = self._changed, asyncio.Event()
        changed.set()

    async def _handle(self, ws: ServerConnection) -> None:
        sent = 0
        closed = asyncio.ensure_future(ws.wait_closed())
        try:
            while True:
                while sent < len(self._history):
                    await ws.send(self._history[sent])
                    sent += 1
                changed = asyncio.ensure_future(self._changed.wait())
                await asyncio.wait({changed, closed}, return_when=asyncio.FIRST_COMPLETED)
                if closed.done():
                    changed.cancel()
                    return
        except ConnectionClosed:
            pass
        finally:
            closed.cancel()
