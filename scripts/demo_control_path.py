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

Stability diagram (stage sweep; the inner axis pulsed by the sequencer):
  1. Sweep: kind "stage", outer P1, inner P2_pulse, 48 x 48 -> "run". The map draws live.
  2. Pulse sequence: edit the rows (step / ramp / wait / drive / measure); a value is a number or a
     symbol, and each symbol is bound below to an axis or a number. Errors show while you type;
     "reset to template" returns to step(P2_pulse, v_P2) ; measure(sensor).
  3. Records -> "analyse" on the new record -> method "Charge transitions" -> "run analysis" ->
     "show overlays" (segments on the honeycomb) and "show output" (the detection map).
Coulomb diamonds (DC sweep): kind "DC", outer SG -0.2..0.2, inner bias -0.0015..0.0015 (inner axis
  name V_sd), options {{"seed": 1, "noise": false, "sensor_width_v": 0.01}}, method "Coulomb diamonds".
Chopped readout (ADR 0037): rows step P2_pulse v_P2 / measure I_on / step P2_pulse v_P2 + 0.002 /
  measure I_off / difference dI = I_on - I_off. The record holds I_on, I_off and dI: choose one under
  "variable" in the header, or subtract any two with "minus".
Operating point (ADR 0038): "add level" holds DC channels for the whole sweep, e.g. P2 = 0.05 with the
  P2_pulse axis swept around it (-0.02..0.12).
1-D: outer axis "- none (1-D)"; the view draws a trace.
Abort: a queued or running run has an "abort" button; a running one is recorded as aborted.
View options (transform, swap axes) are client-side; any Dataset on the stream is under the selector.

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
