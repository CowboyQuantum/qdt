// Flight Deck v0: one source, first Dataset, live map or trace, annotation overlay, stream stats.
// URL parameters:
//   ?ws=ws://127.0.0.1:8765   WebSocket source (default)
//   ?replay=<url>&speed=1     replay a .qdtrec fetched from <url> (speed omitted = unpaced)
//   ?renderer=webgl2|cpu      2D renderer (default webgl2, falling back to cpu)
//   ?bench=1                  record per-chunk latency in window.__flightdeck (benchmark harness)
// A .qdtrec can also be loaded with the file picker.
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

function start(source: Source): void {
  abort?.abort();
  abort = new AbortController();
  title.textContent = source.label;
  let shown: DatasetStore | null = null;
  consume(
    source,
    (store) => {
      if (!shown) {
        shown = store;
        show(store, abort!.signal);
      }
    },
    abort.signal,
  ).catch((e: unknown) => {
    status.textContent = `error: ${String(e)}`;
    if (window.__flightdeck) window.__flightdeck.error = String(e);
  });
}

function makeRenderer(): MapRenderer {
  const name = params.get("renderer");
  if (name && (RENDERERS as readonly string[]).includes(name)) return createMapRenderer(name as RendererName, plot);
  return defaultMapRenderer(plot);
}

function show(store: DatasetStore, signal: AbortSignal): void {
  // display only: a registry replay names its record (ADR 0027); nothing branches on where data came from
  const ref = store.dataset.source.registry_ref;
  if (ref) title.textContent = `${title.textContent} · record ${ref}`;
  const view = chooseView(store.dataset);
  if (!view) {
    status.textContent = `${store.dataset.name}: no v0 view for this shape`;
    return;
  }
  const renderer = view.kind === "heatmap" ? makeRenderer() : null;
  const state: BenchState = { renderer: renderer?.name ?? "trace", samples: [], frames: 0, complete: false, error: null };
  if (bench) window.__flightdeck = state;
  if (renderer) window.__flightdeckRenderer = renderer;

  let dirty: [number, number] | null = null;
  let pending: [number, number][] = []; // [produced_at ms, points] of chunks not yet drawn
  let points = 0;
  let latency = NaN;
  const recent: [number, number][] = []; // [time ms, points]
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
        let map = data.values;
        const [rows, cols] = data.shape.slice(-2) as [number, number];
        if (view.stackDim) {
          if (mean?.length !== rows * cols) mean = new Float64Array(rows * cols).fill(NaN);
          meanAlongLeading(data, dirty[0], dirty[1], mean);
          map = mean;
        }
        const r = finiteRange(map.subarray(dirty[0] * cols, dirty[1] * cols));
        if (r) range = range ? { min: Math.min(range.min, r.min), max: Math.max(range.max, r.max) } : r;
        if (renderer.shape[0] !== rows || renderer.shape[1] !== cols) {
          renderer.resize(rows, cols);
          renderer.upload(map, 0, rows);
        } else renderer.upload(map, dirty[0], dirty[1]);
        if (range) renderer.draw(range);
        if (bench) renderer.finish();
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
