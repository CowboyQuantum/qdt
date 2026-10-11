"""Serve a synthetic or replayed Dataset stream: `uv run python -m qdt_lab.stream --help`.

The server stays up after the source finishes, so late clients still get the full history.
"""

import argparse
import asyncio

from .replay import ReplaySource
from .server import StreamServer
from .synthetic import MAP_SIZE, POINTS_PER_SECOND, SyntheticMap


async def main(args: argparse.Namespace) -> None:
    if args.replay:
        source = ReplaySource(args.replay, speed=args.speed or None)
    else:
        source = SyntheticMap(
            n_outer=args.size,
            n_inner=args.size,
            points_per_chunk=args.points_per_chunk,
            points_per_second=args.rate or None,
        )
    async with StreamServer(args.host, args.port) as server:
        print(f"serving {source.dataset.name!r} on {server.url}", flush=True)
        await server.feed(source)
        print("source finished; still serving history (Ctrl+C to stop)", flush=True)
        await asyncio.Future()


def cli() -> None:
    p = argparse.ArgumentParser(prog="python -m qdt_lab.stream", description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--size", type=int, default=MAP_SIZE, help="synthetic map edge length")
    p.add_argument("--rate", type=float, default=POINTS_PER_SECOND, help="points/s; 0 = unpaced")
    p.add_argument("--points-per-chunk", type=int, default=None, help="default: one line")
    p.add_argument("--replay", help="serve a .qdtrec recording instead of the synthetic map")
    p.add_argument("--speed", type=float, default=1.0, help="replay speed factor; 0 = unpaced")
    try:
        asyncio.run(main(p.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
