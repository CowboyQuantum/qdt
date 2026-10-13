"""`python -m qdt_registry`: query, sync, and serve records to Flight Deck.

    python -m qdt_registry find [--device D] [--stand S] [--definition NAME] [--remote]
    python -m qdt_registry sync                      # needs QDT_REGISTRY_DSN and QDT_PAYLOAD_STORE
    python -m qdt_registry serve RECORD_ID           # with stored analysis overlays; then Flight Deck
    python -m qdt_registry serve --output RESULT_ID  # a result's own Dataset, e.g. its detection map

The client root defaults to ~/.qdt/registry (`--root`). `serve` needs the `[serve]` extra (qdt-lab's
stream server); the record's payload must be in this client's store.
"""

import argparse
import asyncio
import pathlib

from . import Registry

DEFAULT_ROOT = pathlib.Path.home() / ".qdt" / "registry"


def _find(reg: Registry, a: argparse.Namespace) -> None:
    rows = reg.find(
        device_id=a.device, stand_id=a.stand, definition_name=a.definition, remote=a.remote
    )
    for r in rows:
        print(
            f"{r.record_id}  {r.started_at:%Y-%m-%d %H:%M}  {r.outcome:9}  {r.device_id}  "
            f"{r.stand_id}  {r.definition_name}"
        )
    print(f"{len(rows)} record(s)")


async def _serve(reg: Registry, a: argparse.Namespace) -> None:
    from qdt_lab.stream import PayloadSource, StreamServer

    if a.output:  # a result's own Dataset, e.g. the map it detected on (ADR 0031)
        source = PayloadSource(reg.output(a.output), registry_ref=a.output)
        async with StreamServer(a.host, a.port) as server:
            print(f"serving output of result {a.output} ({source.dataset.name!r}) on {server.url}")
            await server.feed(source)
            print("sent; still serving history (Ctrl+C to stop)", flush=True)
            await asyncio.Future()
        return
    overlays = [
        ann
        for r in reg.results(record_id=a.record_id, status="ok")
        if not a.no_analysis
        for ann in r.annotations
    ]
    source = PayloadSource(reg.payload(a.record_id), registry_ref=a.record_id, annotations=overlays)
    async with StreamServer(a.host, a.port) as server:
        print(f"serving record {a.record_id} ({source.dataset.name!r}) on {server.url}", flush=True)
        await server.feed(source)
        print("sent; still serving history (Ctrl+C to stop)", flush=True)
        await asyncio.Future()


def cli() -> None:
    p = argparse.ArgumentParser(
        prog="python -m qdt_registry",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--root", type=pathlib.Path, default=DEFAULT_ROOT, help="client cache + payload store"
    )
    sub = p.add_subparsers(dest="command", required=True)
    f = sub.add_parser("find", help="list records matching every given filter")
    f.add_argument("--device")
    f.add_argument("--stand", help="stand_id")
    f.add_argument("--definition", help="definition name")
    f.add_argument("--remote", action="store_true", help="ask the server, not the cache")
    sub.add_parser("sync", help="upload unsynced rows and payloads to the server")
    s = sub.add_parser("serve", help="stream one record's payload (or a result's output) for Flight Deck")
    s.add_argument("record_id", nargs="?")
    s.add_argument("--output", metavar="RESULT_ID", help="serve this result's output Dataset instead")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument(
        "--no-analysis", action="store_true", help="omit overlays from stored analysis results"
    )
    a = p.parse_args()
    reg = Registry.from_env(a.root)
    if a.command == "find":
        _find(reg, a)
    elif a.command == "sync":
        print(reg.sync())
    else:
        if not a.record_id and not a.output:
            p.error("serve needs a RECORD_ID or --output RESULT_ID")
        try:
            asyncio.run(_serve(reg, a))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    cli()
