"""`python -m qdt_server`: the control path on one machine, against the simulated backend (Step 4b).

    uv run python -m qdt_server [--root ~/.qdt/registry] [--host 127.0.0.1] [--port 8700] [--stream-port 8765]
                                [--ui apps/flightdeck/dist] [--stand stand.json --device-id <id>]

Then Flight Deck (`corepack pnpm dev` in apps/flightdeck, or the built one served at / with --ui)
connects to the stream, and the API is at http://127.0.0.1:8700 (interactive docs at /docs).
`scripts/demo_control_path.py` does all of it in one command.

On the bench (Step 5), `--stand stand.json --device-id <id>` runs on the real instruments instead of
the simulator: the stand file is a `StandConfig` whose instruments name a driver backend ('qdac2',
'keithley2400', 'infiniivision', 'qua') with settings["address"]. Keep it out of the repo: it holds
addresses (`*.stand.json` is gitignored, rule 7).
"""

import argparse
import dataclasses
import pathlib
from datetime import UTC, datetime

import uvicorn

from qdt_schemas.identity import DeviceRecord
from qdt_schemas.stand import StandConfig

from .app import Settings, create_app, stand_backends

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
    p.add_argument("--stand", type=pathlib.Path, default=None, help="real stand (StandConfig JSON)")
    p.add_argument("--device-id", default=None, help="device under test (with --stand)")
    a = p.parse_args()
    settings = Settings(root=a.root, stream_host=a.host, stream_port=a.stream_port, ui=a.ui)
    if a.stand is not None:
        if not a.device_id:
            p.error("--stand needs --device-id (the device the records are about)")
        stand = StandConfig.model_validate_json(a.stand.read_text(encoding="utf-8"))
        settings = dataclasses.replace(
            settings,
            stand=stand,
            device=DeviceRecord(
                device_id=a.device_id,
                kind="device",
                simulated=False,
                registered_at=datetime.now(UTC),
            ),
            backends=stand_backends(stand),
        )
    app = create_app(settings)
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    cli()
