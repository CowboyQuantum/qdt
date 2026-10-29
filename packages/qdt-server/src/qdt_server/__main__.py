"""`python -m qdt_server`: the control path on one machine, against the simulated backend (Step 4b).

    uv run python -m qdt_server [--root ~/.qdt/registry] [--host 127.0.0.1] [--port 8700] [--stream-port 8765]
                                [--ui apps/flightdeck/dist] [--stand stand.json --device-id <id>] [--read-only]
                                [--tokens <file>]
    uv run python -m qdt_server [--root …] [--tokens <file>] --add-token "<desk or person>"

Then Flight Deck (`corepack pnpm dev` in apps/flightdeck, or the built one served at / with --ui)
connects to the stream, and the API is at http://127.0.0.1:8700 (interactive docs at /docs).
`scripts/demo_control_path.py` does all of it in one command.

With `QDT_REGISTRY_DSN` and `QDT_PAYLOAD_STORE` set, a stand server uploads every record to the registry
server after it is ingested, and once at start (ADR 0080); unreachable, the record waits in the cache.
`--read-only` is the other kind of server (ADR 0074): on the database PC, no stand and no command,
serving records, results, outcomes, payload bytes and replay from the registry server to Flight Deck
and to any application over HTTP; it answers when the measurement PC is off.

Commands from another computer need a token (ADR 0074, 0082). A stand server reachable from the network
(`--host 0.0.0.0`) refuses every `POST`/`DELETE` that does not carry `Authorization: Bearer <token>`
with a token from its token file (`--tokens`, default `<root>/tokens`; one token per line, a label after
it, `#` comments; delete a line to revoke). From this computer nothing changes. `--add-token "<label>"`
appends a token and prints it once; give it to that desk as `?token=<token>` on Flight Deck's address,
which keeps it in the browser and drops it from the address.

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
from .auth import new_token

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
    p.add_argument(
        "--read-only",
        action="store_true",
        help="a read server (ADR 0074): no stand, no commands; records, results, payloads and "
        "replay from QDT_REGISTRY_DSN / QDT_PAYLOAD_STORE",
    )
    p.add_argument(
        "--tokens",
        type=pathlib.Path,
        default=None,
        help="the command token file (ADR 0074): one token per line; default <root>/tokens",
    )
    p.add_argument(
        "--add-token",
        metavar="LABEL",
        default=None,
        help="append a fresh token labelled LABEL (a desk or person) to the token file, print it "
        "once and exit",
    )
    a = p.parse_args()
    tokens = a.tokens if a.tokens is not None else a.root / "tokens"
    if a.add_token is not None:
        print(new_token(tokens, a.add_token))
        return
    if a.read_only and (a.stand is not None or a.device_id):
        p.error("--read-only drives no stand: drop --stand/--device-id")
    settings = Settings(
        root=a.root,
        stream_host=a.host,
        stream_port=a.stream_port,
        ui=a.ui,
        read_only=a.read_only,
        tokens=tokens,
    )
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
            nodes={},
            layout=None,
        )
    app = create_app(settings)
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    cli()
