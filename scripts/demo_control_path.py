"""The Step 4b demo: the whole simulated loop from a browser, with one process running.

    uv run python scripts/demo_control_path.py [--root ~/.qdt/registry] [--port 8700] [--stream-port 8765]
                                               [--rebuild] [--no-browser]

Builds Flight Deck if `apps/flightdeck/dist` is missing (or with --rebuild; needs Node and corepack),
then starts `qdt-server` against the simulator with that build served at `/`, and opens the browser.
Everything after that happens in the panel on the right; the walkthrough is printed on start.
"""

import argparse
import pathlib
import shutil
import subprocess
import threading
import webbrowser

import uvicorn

from qdt_server import Settings, create_app

REPO = pathlib.Path(__file__).resolve().parents[1]
APP = REPO / "apps" / "flightdeck"

# ASCII only: a Windows console (or a redirect) may not encode arrows and minus signs
WALKTHROUGH = """\
Flight Deck at {url}
The stand is Phantom's simulated device (ADR 0088): eight gates programmed at their working point
(P1, P2 and SG at 0.6 V), the sensor, its bias, and a simulated scope. docs/guides/simulated-stand.md
walks through all of this with pictures.

Stability diagram (stage sweep; the inner axis pulsed by the sequencer):
  1. Sweep: kind "stage", outer P1 0.45..0.75, inner P2_pulse -0.15..0.15 (a pulse adds to P2's DC
     level), 48 x 48, options {{"seed": 1, "noise": false}} -> Run. The map draws live. With noise on,
     raise the measure's duration in the Pulse widget to 1000000 ns (1 ms) or more.
  2. Pulse: edit the rows (step / ramp / wait / drive / measure); a value is a number or a symbol, and
     each symbol is bound below to an axis or a number. "reset to template" returns to
     step(P2_pulse, v_P2) ; measure(sensor).
  3. History -> "analyse" on the new record -> method "Charge transitions" -> "run analysis" ->
     "show overlays" (segments on the honeycomb) and "show output" (the detection map).
Coulomb diamonds (DC sweep): kind "DC", outer SG -0.6..1.4, inner bias -0.0015..0.0015 (inner axis
  name V_sd), options {{"seed": 1, "noise": false}}, method "Coulomb diamonds".
Tune-up: in "Tune-up", tick the four nodes, options {{"seed": 2, "noise": false}} -> "run tune-up".
Operating point: "add level" holds DC channels for the whole sweep; the Levels widget sets and holds them.
1-D: outer axis "- none (1-D)"; the view draws a trace.
Abort: the Queue widget aborts a running entry; it is recorded as aborted.

API docs at http://127.0.0.1:{port}/docs. Ctrl+C stops.
"""


def build(rebuild: bool) -> pathlib.Path:
    dist = APP / "dist"
    if (dist / "index.html").exists() and not rebuild:
        return dist
    corepack = shutil.which("corepack")
    if corepack is None:
        raise SystemExit(
            "Flight Deck is not built and corepack is not on PATH (install Node >= 20)"
        )
    if not (APP / "node_modules").exists():
        subprocess.run([corepack, "pnpm", "install", "--frozen-lockfile"], cwd=APP, check=True)
    subprocess.run([corepack, "pnpm", "build"], cwd=APP, check=True)
    return dist


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--root", type=pathlib.Path, default=pathlib.Path.home() / ".qdt" / "registry")
    p.add_argument("--port", type=int, default=8700, help="HTTP API (and UI) port")
    p.add_argument("--stream-port", type=int, default=8765, help="Dataset stream (WebSocket) port")
    p.add_argument("--rebuild", action="store_true", help="rebuild Flight Deck first")
    p.add_argument("--no-browser", action="store_true", help="print the URL, do not open it")
    a = p.parse_args()

    dist = build(a.rebuild)
    base = f"http://127.0.0.1:{a.port}"
    url = f"{base}/?api={base}&ws=ws://127.0.0.1:{a.stream_port}"
    print(WALKTHROUGH.format(url=url, port=a.port))
    if not a.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    app = create_app(Settings(root=a.root, stream_port=a.stream_port, ui=dist))
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
