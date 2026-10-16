// Flight Deck: wiring only (ADR 0054). The strip, the workspace of widgets, the shared Dataset stores
// and one source. URL parameters:
//   ?ws=ws://127.0.0.1:8765   WebSocket source (default)
//   ?api=http://127.0.0.1:8700  qdt-server API for the control widget (default)
//   ?replay=<url>&speed=1     replay a .qdtrec fetched from <url> (speed omitted = unpaced)
//   ?renderer=webgl2|cpu      2D renderer (default webgl2, falling back to cpu)
//   ?bench=1                  record per-chunk latency in window.__flightdeck (benchmark harness)
// A .qdtrec can also be loaded with the strip's file picker.
import { ApiClient, apiBase } from "./api/client";
import { ReplaySource } from "./sources/replay";
import type { Source } from "./sources/source";
import { WebSocketSource } from "./sources/websocket";
import { Datasets } from "./stream/datasets";
import { controlWidget } from "./widgets/control";
import { emptyWidget } from "./widgets/empty";
import { plotWidget } from "./widgets/plot";
import { Bus } from "./workspace/bus";
import { loadLayout, safeStorage } from "./workspace/layout";
import { mountStrip } from "./workspace/strip";
import { applyTheme, ThemeManager } from "./workspace/theme";
import { WidgetRegistry } from "./workspace/widget";
import { Workspace } from "./workspace/workspace";

const params = new URLSearchParams(location.search);
const api = new ApiClient(apiBase(params));
const bus = new Bus();
const datasets = new Datasets();
const registry = new WidgetRegistry().register(plotWidget).register(controlWidget).register(emptyWidget);

const themes = new ThemeManager(safeStorage(), applyTheme, matchMedia("(prefers-color-scheme: light)").matches);
themes.apply();

const say = (text: string, error = false) => bus.emit("say", { text, error });
const start = (source: Source) =>
  datasets.start(source, (e: unknown) => {
    say(`stream error: ${String(e)}`, true);
    if (window.__flightdeck) window.__flightdeck.error = String(e);
  });

mountStrip(document.querySelector("header.strip")!, {
  bus,
  api,
  datasets,
  themes,
  onReplayFile: async (file) => start(new ReplaySource(new Uint8Array(await file.arrayBuffer()), file.name, 1)),
});
new Workspace(document.getElementById("ws")!, registry, bus, { api, datasets, params }, loadLayout(registry.ids()));

const replay = params.get("replay");
if (replay) {
  const speed = params.get("speed");
  fetch(replay)
    .then((r) => r.arrayBuffer())
    .then((b) => start(new ReplaySource(new Uint8Array(b), replay, speed ? Number(speed) : null)))
    .catch((e: unknown) => say(`replay: ${String(e)}`, true));
} else {
  start(new WebSocketSource(params.get("ws") ?? "ws://127.0.0.1:8765"));
}
