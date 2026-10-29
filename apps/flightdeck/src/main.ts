// Flight Deck: wiring only (ADR 0054). The strip, the workspace of widgets, the shared Dataset stores
// and one source. URL parameters:
//   ?ws=ws://127.0.0.1:8765   WebSocket source (default)
//   ?api=http://127.0.0.1:8700  qdt-server API for the control widget (default)
//   ?token=<token>            command token for a stand server on another computer (ADR 0074): kept in
//                             this browser for that server and dropped from the address; `#token=` too
//   ?replay=<url>&speed=1     replay a .qdtrec fetched from <url> (speed omitted = unpaced)
//   ?renderer=webgl2|cpu      2D renderer (default webgl2, falling back to cpu)
//   ?bench=1                  record per-chunk latency in window.__flightdeck (benchmark harness)
// A .qdtrec can also be loaded with the strip's file picker.
import { ApiClient, addressWithoutToken, apiBase, commandToken } from "./api/client";
import { ReplaySource } from "./sources/replay";
import type { Source } from "./sources/source";
import { WebSocketSource } from "./sources/websocket";
import { Datasets } from "./stream/datasets";
import { analysisWidget } from "./widgets/analysis";
import { deviceWidget } from "./widgets/device";
import { emptyWidget } from "./widgets/empty";
import { gatesWidget } from "./widgets/gates";
import { historyWidget } from "./widgets/history";
import { levelsWidget } from "./widgets/levels";
import { plotWidget } from "./widgets/plot";
import { pulseWidget } from "./widgets/pulse";
import { queueWidget } from "./widgets/queue";
import { scriptWidget } from "./widgets/script";
import { sweepWidget } from "./widgets/sweep";
import { tuneupWidget } from "./widgets/tuneup";
import { Bus } from "./workspace/bus";
import { LAYOUT_KEY, defaultLayout, loadLayout, READ_ONLY_LAYOUT_KEY, readOnlyLayout, safeStorage } from "./workspace/layout";
import { mountStrip } from "./workspace/strip";
import { applyTheme, loadWebFonts, setWebFonts, ThemeManager } from "./workspace/theme";
import { WidgetRegistry } from "./workspace/widget";
import { Workspace } from "./workspace/workspace";

const params = new URLSearchParams(location.search);
const base = apiBase(params);
const { token, fromAddress } = commandToken(params, location.hash, safeStorage(), base);
if (fromAddress) history.replaceState(null, "", addressWithoutToken(location));
const api = new ApiClient(base, undefined, token);
const bus = new Bus();
const datasets = new Datasets();
// The kind of server decides what is on offer (ADR 0074): against a read server the command widgets and
// the strip's Run are absent, not disabled; an unreachable server is treated as a stand server.
const readOnly = (await api.server().catch(() => null))?.read_only === true;
const registry = new WidgetRegistry().register(plotWidget).register(emptyWidget).register(historyWidget);
if (!readOnly) registry.register(sweepWidget).register(pulseWidget).register(levelsWidget).register(queueWidget).register(gatesWidget).register(deviceWidget).register(analysisWidget).register(tuneupWidget).register(scriptWidget);
const layoutKey = readOnly ? READ_ONLY_LAYOUT_KEY : LAYOUT_KEY;

const themes = new ThemeManager(safeStorage(), applyTheme, matchMedia("(prefers-color-scheme: light)").matches);
themes.apply();
setWebFonts(loadWebFonts(safeStorage()));

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
  readOnly,
});
new Workspace(document.getElementById("ws")!, registry, bus, { api, datasets, params }, loadLayout(registry.ids(), safeStorage(), layoutKey, readOnly ? readOnlyLayout : defaultLayout), layoutKey);

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
