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
import {
  annotationPath,
  axis,
  chooseView,
  DEFAULT_OPTIONS,
  meanAlongLeading,
  transformMap,
  transpose,
  type Transform,
  type ViewKind,
  type ViewOptions,
} from "./view";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const plot = $<HTMLCanvasElement>("plot");
const overlay = $<HTMLCanvasElement>("overlay");
const status = $<HTMLDivElement>("status");
const title = $<HTMLDivElement>("title");
const message = $<HTMLDivElement>("message");
const datasets = $<HTMLSelectElement>("datasets");
const transformSelect = $<HTMLSelectElement>("transform");
const swapBox = $<HTMLInputElement>("swap");
const options = (): ViewOptions => ({ swap: swapBox.checked, transform: transformSelect.value as Transform });
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
  let derived: Float64Array | null = null; // transformed map
  let swapped: Float64Array | null = null; // transposed map
  let shown: ViewOptions = { ...DEFAULT_OPTIONS };
  const onOptions = () => {
    const o = options();
    if (o.swap === shown.swap && o.transform === shown.transform) return;
    shown = o;
    range = null;
    const rows = store.get(view.variable).shape;
    dirty = [0, view.kind === "heatmap" && view.stackDim ? rows[1]! : rows[0]!];
    overlaysDirty = true;
  };
  transformSelect.addEventListener("change", onOptions);
  swapBox.addEventListener("change", onOptions);
  signal.addEventListener("abort", () => {
    transformSelect.removeEventListener("change", onOptions);
    swapBox.removeEventListener("change", onOptions);
  }, { once: true });
  shown = options();

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
        const plain = shown.transform === "raw" && !shown.swap;
        if (plain) {
          // the live path: only the dirty rows are mapped and uploaded (the bench measures this)
          const r = finiteRange(map.subarray(dirty[0] * cols, dirty[1] * cols));
          if (r) range = range ? { min: Math.min(range.min, r.min), max: Math.max(range.max, r.max) } : r;
          if (r2.shape[0] !== rows || r2.shape[1] !== cols) {
            r2.resize(rows, cols);
            r2.upload(map, 0, rows);
            range = finiteRange(map) ?? range;
          } else r2.upload(map, dirty[0], dirty[1]);
        } else {
          // a view option: recompute the whole display map client-side (no round trip)
          if (shown.transform !== "raw") {
            if (derived?.length !== rows * cols) derived = new Float64Array(rows * cols);
            map = transformMap(map, rows, cols, shown.transform, derived);
          }
          let [shownRows, shownCols] = [rows, cols];
          if (shown.swap) {
            if (swapped?.length !== rows * cols) swapped = new Float64Array(rows * cols);
            map = transpose(map, rows, cols, swapped);
            [shownRows, shownCols] = [cols, rows];
          }
          range = finiteRange(map);
          if (r2.shape[0] !== shownRows || r2.shape[1] !== shownCols) r2.resize(shownRows, shownCols);
          r2.upload(map, 0, shownRows);
        }
        if (range) r2.draw(range);
        if (bench) r2.finish();
        drawOverlay(store, view, shown);
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
      drawOverlay(store, view, shown); // overlays that arrived after the last chunk
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
      (view.kind === "heatmap" && shown.transform !== "raw" ? ` · ${TRANSFORM_LABEL[shown.transform]} (per step)` : "") +
      (view.kind === "heatmap" && shown.swap ? " · axes swapped" : "") +
      ` · seq ${store.lastSeq}` +
      `${store.complete ? " (complete)" : ""} · ${points.toLocaleString()} pts · ${rate.toLocaleString()} pts/s` +
      (Number.isFinite(latency) ? ` · last chunk age ${latency.toFixed(0)} ms` : "");
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

const TRANSFORM_LABEL: Record<Transform, string> = { raw: "raw", d_col: "d/d(inner)", d_row: "d/d(outer)", grad: "|gradient|" };

/** Axis names, units and extents on the overlay canvas: which coordinate runs which way. */
function drawAxes(store: DatasetStore, view: Extract<ViewKind, { kind: "heatmap" }>, swap: boolean): void {
  const ctx = overlay.getContext("2d")!;
  const { width: w, height: h } = overlay;
  const x = axis(store, swap ? view.rowDim : view.colDim);
  const y = axis(store, swap ? view.colDim : view.rowDim);
  const fmt = (v: number) => (Number.isFinite(v) ? Number(v.toPrecision(4)).toString() : "");
  const first = (a: ArrayLike<number>) => fmt(Number(a[0] ?? NaN));
  const last = (a: ArrayLike<number>) => fmt(Number(a[a.length - 1] ?? NaN));
  const unit = (u: string) => (u ? ` (${u})` : "");
  const font = Math.round(w / 48);
  ctx.font = `${font}px system-ui, sans-serif`;
  const label = (text: string, px: number, py: number, align: CanvasTextAlign, rotate = 0) => {
    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(rotate);
    ctx.textAlign = align;
    ctx.textBaseline = "middle";
    const m = ctx.measureText(text);
    const pad = font * 0.3;
    const left = align === "left" ? 0 : align === "right" ? -m.width : -m.width / 2;
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(left - pad, -font * 0.7, m.width + 2 * pad, font * 1.4);
    ctx.fillStyle = "#eee";
    ctx.fillText(text, 0, 0);
    ctx.restore();
  };
  const m = font;
  label(`${x.name}${unit(x.unit)}`, w / 2, h - m, "center");
  label(first(x.values), m, h - m, "left");
  label(last(x.values), w - m, h - m, "right");
  label(`${y.name}${unit(y.unit)}`, m, h / 2, "center", -Math.PI / 2);
  label(first(y.values), m, h - 3 * m, "left", -Math.PI / 2);
  label(last(y.values), m, 3 * m, "left", -Math.PI / 2);
}

function drawOverlay(store: DatasetStore, view: Extract<ViewKind, { kind: "heatmap" }>, o: ViewOptions): void {
  drawAnnotations(store, view, o.swap);
  drawAxes(store, view, o.swap);
}

function drawAnnotations(store: DatasetStore, view: Extract<ViewKind, { kind: "heatmap" }>, swap: boolean): void {
  const ctx = overlay.getContext("2d")!;
  const { width: w, height: h } = overlay;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = "#ff5370";
  ctx.fillStyle = "#ff5370";
  ctx.lineWidth = 2;
  for (const ann of store.annotations.values()) {
    const path = annotationPath(store, view, ann, swap);
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
