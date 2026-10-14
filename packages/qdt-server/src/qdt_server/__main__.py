"""`python -m qdt_server`: the control path on one machine, against the simulated backend (Step 4b).

    uv run python -m qdt_server [--root ~/.qdt/registry] [--host 127.0.0.1] [--port 8700] [--stream-port 8765]
                                [--ui apps/flightdeck/dist]

Then Flight Deck (`corepack pnpm dev` in apps/flightdeck, or the built one served at / with --ui)
connects to the stream, and the API is at http://127.0.0.1:8700 (interactive docs at /docs).
`scripts/demo_control_path.py` does all of it in one command.
"""

import argparse
import pathlib

import uvicorn

from .app import Settings, create_app

DEFAULT_ROOT = pathlib.Path.home() / ".qdt" / "registry"


def cli() -> None:
    p = argparse.ArgumentParser(
        prog="python -m qdt_server",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT, help="registry root")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8700, help="HTTP API port")
    p.add_argument("--stream-port", type=int, default=8765, help="Dataset stream (WebSocket) port")
    p.add_argument("--ui", type=pathlib.Path, default=None, help="built Flight Deck to serve at /")
    a = p.parse_args()
    app = create_app(Settings(root=a.root, stream_host=a.host, stream_port=a.stream_port, ui=a.ui))
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    cli()
