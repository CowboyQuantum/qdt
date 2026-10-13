// Flight Deck: one source, every announced Dataset selectable (the newest shown first), live map or
// trace, annotation overlay, stream stats, and the control panel over qdt-server's API (Step 4b).
// URL parameters:
//   ?ws=ws://127.0.0.1:8765   WebSocket source (default)
//   ?api=http://127.0.0.1:8700  qdt-server API for the control panel (default)
//   ?replay=<url>&speed=1     replay a .qdtrec fetched from <url> (speed omitted = unpaced)
//   ?renderer=webgl2|cpu      2D renderer (default webgl2, falling back to cpu)
//   ?bench=1                  record per-chunk latency in window.__flightdeck (benchmark harness)
// A .qdtrec can also be loaded with the file picker.
import { ApiClient, apiBase } from "./api/client";
import { ControlPanel } from "./control/panel";
import { finiteRange, type Range } from "./render/cpu";
import { createMapRenderer, defaultMapRenderer, type MapRenderer, RENDERERS, type RendererName } from "./render/map";
import { drawTrace } from "./render/trace";
import { ReplaySource } from "./sources/replay";
import { consume, type Source } from "./sources/source";
import { WebSocketSource } from "./sources/websocket";
import type { DatasetStore } from "./stream/store";
import { annotationPath, axis, chooseView, meanAlongLeading, type ViewKind } from "./view";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const plot = $<HTMLCanvasElement>("plot");
const overlay = $<HTMLCanvasElement>("overlay");
const status = $<HTMLDivElement>("status");
const title = $<HTMLDivElement>("title");
const message = $<HTMLDivElement>("message");
const datasets = $<HTMLSelectElement>("datasets");
const params = new URLSearchParams(location.search);
const bench = params.get("bench") === "1";

/** Benchmark record, read by apps/flightdeck/bench/run.mjs. Times are epoch ms (same clock as the producer). */
export interface BenchState {
  renderer: string;
  /** [chunk produced_at, frame drawn (after GPU finish), points in chunk] per chunk */
  samples: [number, number, number][];
  frames: number;
  complete: boolean;
  error: string | null;
}
declare global {
  interface Window {
    __flightdeck?: BenchState;
    __flightdeckRenderer?: MapRenderer;
  }
}

let abort: AbortController | null = null;
const stores = new Map<string, DatasetStore>();
let viewAbort: AbortController | null = null;
const sourceLabel = { text: "" };

/** Show one store: the previous view's frame loop stops, the renderer and canvases are reused. */
function select(store: DatasetStore): void {
  viewAbort?.abort();
  viewAbort = new AbortController();
  datasets.value = store.dataset.dataset_id;
  // display only: a registry replay names its record (ADR 0027); nothing branches on where data came from
  const ref = store.dataset.source.registry_ref;
  title.textContent = ref ? `${sourceLabel.text} · record ${ref}` : sourceLabel.text;
  show(store, viewAbort.signal);
}

function start(source: Source): void {
  abort?.abort();
  abort = new AbortController();
  sourceLabel.text = source.label;
  title.textContent = source.label;
  stores.clear();
  datasets.replaceChildren();
  consume(
    source,
    (store) => {
      stores.set(store.dataset.dataset_id, store);
      datasets.append(new Option(store.dataset.name, store.dataset.dataset_id));
      select(store); // the newest Dataset is what the user just asked for (a run, a replay)
    },
    abort.signal,
  ).catch((e: unknown) => {
    status.textContent = `error: ${String(e)}`;
    if (window.__flightdeck) window.__flightdeck.error = String(e);
  });
}
datasets.addEventListener("change", () => {
  const store = stores.get(datasets.value);
  if (store) select(store);
});

function makeRenderer(): MapRenderer {
  const name = params.get("renderer");
  if (name && (RENDERERS as readonly string[]).includes(name)) return createMapRenderer(name as RendererName, plot);
  return defaultMapRenderer(plot);
}

let renderer: MapRenderer | null = null;

function show(store: DatasetStore, signal: AbortSignal): void {
  const view = chooseView(store.dataset);
  if (!view) {
    status.textContent = `${store.dataset.name}: no v0 view for this shape`;
    return;
  }
  if (view.kind === "heatmap" && !renderer) renderer = makeRenderer();
  const state: BenchState = { renderer: renderer?.name ?? "trace", samples: [], frames: 0, complete: false, error: null };
  if (bench) window.__flightdeck = state;
  if (renderer) window.__flightdeckRenderer = renderer;

  const current = store.get(view.variable).shape;
  let dirty: [number, number] | null = current[0] ? [0, view.kind === "heatmap" && view.stackDim ? current[1]! : current[0]!] : null;
  let pending: [number, number][] = []; // [produced_at ms, points] of chunks not yet drawn
  let points = 0;
  let latency = NaN;
  const recent: [number, number][] = []; // [time ms, points]
  let overlaysDirty = store.annotations.size > 0;
  const offAnnotation = store.onAnnotation(() => (overlaysDirty = true));
  signal.addEventListener("abort", offAnnotation, { once: true });
  store.onUpdate((u) => {
    const rows = u.region.find((s) => s.dim === (view.kind === "heatmap" ? view.rowDim : view.latestAlong));
    const [r0, r1] = rows ? [rows.start, rows.stop] : [0, 1];
    dirty = dirty ? [Math.min(dirty[0], r0), Math.max(dirty[1], r1)] : [r0, r1];
    const n = u.region.reduce((a, s) => a * (s.stop - s.start), 1);
    points += n;
    recent.push([performance.now(), n]);
    pending.push([Date.parse(u.producedAt), n]);
  });

  let range: Range | null = null;
  let mean: Float64Array | null = null; // display map for a stacked heatmap: mean over the stack dim

  const frame = () => {
    if (signal.aborted) return;
    if (dirty) {
      const data = store.get(view.variable);
      if (view.kind === "heatmap" && renderer) {
        const r2 = renderer;
        let map = data.values;
        const [rows, cols] = data.shape.slice(-2) as [number, number];
        if (view.stackDim) {
          if (mean?.length !== rows * cols) mean = new Float64Array(rows * cols).fill(NaN);
          meanAlongLeading(data, dirty[0], dirty[1], mean);
          map = mean;
        }
        const r = finiteRange(map.subarray(dirty[0] * cols, dirty[1] * cols));
        if (r) range = range ? { min: Math.min(range.min, r.min), max: Math.max(range.max, r.max) } : r;
        if (r2.shape[0] !== rows || r2.shape[1] !== cols) {
          r2.resize(rows, cols);
          r2.upload(map, 0, rows);
          range = finiteRange(map) ?? range;
        } else r2.upload(map, dirty[0], dirty[1]);
        if (range) r2.draw(range);
        if (bench) r2.finish();
        drawAnnotations(store, view);
      } else if (view.kind === "trace") {
        const x = axis(store, view.xDim).values;
        const n = view.latestAlong ? data.shape[1]! : data.values.length;
        const last = view.latestAlong ? data.shape[0]! - 1 : 0;
        if (last >= 0) drawTrace(plot, x as never, data.values.subarray(last * n, (last + 1) * n));
      }
      const drawn = Date.now();
      // age of the newest chunk: glass-to-glass latency while live; data age for history on late join
      if (pending.length) latency = drawn - pending[pending.length - 1]![0];
      if (bench) for (const [produced, n] of pending) state.samples.push([produced, drawn, n]);
      pending = [];
      state.frames++;
      state.complete = store.complete;
      dirty = null;
      overlaysDirty = false;
    } else if (overlaysDirty && view.kind === "heatmap" && renderer) {
      drawAnnotations(store, view); // overlays that arrived after the last chunk
      overlaysDirty = false;
    }
    const now = performance.now();
    while (recent.length && recent[0]![0] < now - 1000) recent.shift();
    const rate = recent.reduce((a, [, n]) => a + n, 0);
    status.textContent =
      `${store.dataset.name} · ${view.kind}${renderer ? ` (${renderer.name})` : ""}` +
      (view.kind === "heatmap" && view.stackDim
        ? ` · mean over ${store.get(view.variable).shape[0]} ${view.stackDim}`
        : "") +
      ` · seq ${store.lastSeq}` +
      `${store.complete ? " (complete)" : ""} · ${points.toLocaleString()} pts · ${rate.toLocaleString()} pts/s` +
      (Number.isFinite(latency) ? ` · last chunk age ${latency.toFixed(0)} ms` : "");
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

function drawAnnotations(store: DatasetStore, view: Extract<ViewKind, { kind: "heatmap" }>): void {
  const ctx = overlay.getContext("2d")!;
  const { width: w, height: h } = overlay;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = "#ff5370";
  ctx.fillStyle = "#ff5370";
  ctx.lineWidth = 2;
  for (const ann of store.annotations.values()) {
    const path = annotationPath(store, view, ann);
    if (!path) continue;
    const px = path.map(([x, y]) => [x * w, (1 - y) * h] as const);
    ctx.beginPath();
    px.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    if (ann.kind === "region") ctx.closePath();
    if (ann.kind === "marker") ctx.arc(px[0]![0], px[0]![1], 4, 0, 2 * Math.PI);
    ctx.stroke();
    if (ann.label) ctx.fillText(ann.label, px[0]![0] + 6, px[0]![1] - 6);
  }
}

const api = new ApiClient(apiBase(params));
const panel = new ControlPanel($<HTMLElement>("control"), api, {
  say(text, isError = false) {
    message.textContent = text;
    message.className = isError ? "error" : "";
  },
});
void panel.init();

$<HTMLInputElement>("file").addEventListener("change", async (e) => {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (file) start(new ReplaySource(new Uint8Array(await file.arrayBuffer()), file.name, 1));
});

const replay = params.get("replay");
if (replay) {
  const speed = params.get("speed");
  fetch(replay)
    .then((r) => r.arrayBuffer())
    .then((b) => start(new ReplaySource(new Uint8Array(b), replay, speed ? Number(speed) : null)))
    .catch((e: unknown) => (status.textContent = `error: ${String(e)}`));
} else {
  start(new WebSocketSource(params.get("ws") ?? "ws://127.0.0.1:8765"));
}
