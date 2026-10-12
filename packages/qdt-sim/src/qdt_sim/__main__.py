"""Stream a simulated stability diagram live: `uv run python -m qdt_sim --help`, then
`pnpm dev` in apps/flightdeck and open `?ws=ws://127.0.0.1:8765`.

The sweep is compiled and executed exactly as a real one would be; only the backend is simulated.
`--repeats 0` repeats the scan until stopped (a `repeat` dimension; Flight Deck averages on display).
"""

import argparse
import asyncio

from qdt_lab.experiment import Executor, SimulatedEmitter, compile_sweep
from qdt_lab.stream import StreamServer

from .scenarios import DEVICE_ID, default_device, default_stand, stability


async def main(args: argparse.Namespace) -> None:
    definition = stability(
        args.size,
        args.size,
        shots=args.shots,
        reduce="mean" if args.shots > 1 and not args.keep_shots else None,
        repeats=None if args.repeats == 0 else args.repeats,
    )
    plan = compile_sweep(definition, default_stand(), {"simulated": SimulatedEmitter()})
    device = default_device(
        seed=args.seed, noise=not args.no_noise, points_per_second=args.rate or None
    )
    source = Executor(plan, {DEVICE_ID: device}).run()
    async with StreamServer(args.host, args.port) as server:
        print(f"serving {plan.dataset.name!r} on {server.url}", flush=True)
        if args.wait_for_client:
            await server.wait_for_client()
            print("client connected; streaming", flush=True)
        await server.feed(source)
        print("sweep finished; still serving history (Ctrl+C to stop)", flush=True)
        await asyncio.Future()


def cli() -> None:
    p = argparse.ArgumentParser(prog="python -m qdt_sim", description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--size", type=int, default=128, help="points per axis")
    p.add_argument("--shots", type=int, default=1)
    p.add_argument("--keep-shots", action="store_true", help="stream every shot (adds a shot dim)")
    p.add_argument("--repeats", type=int, default=1, help="whole-scan repeats; 0 = until stopped")
    p.add_argument("--rate", type=float, default=20_000, help="device points/s; 0 = unpaced")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--no-noise", action="store_true")
    p.add_argument("--wait-for-client", action="store_true")
    try:
        asyncio.run(main(p.parse_args()))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
