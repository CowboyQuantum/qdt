// Flight Deck v0: one source, first Dataset, live heatmap or trace, annotation overlay, stream stats.
// URL: ?ws=ws://127.0.0.1:8765 (default) — or load a .qdtrec file with the file picker.
import { finiteRange, type Range, renderRGBA } from "./render/cpu";
import { Heatmap } from "./render/heatmap";
import { drawTrace } from "./render/trace";
import { ReplaySource } from "./sources/replay";
import { consume, type Source } from "./sources/source";
import { WebSocketSource } from "./sources/websocket";
import type { DatasetStore } from "./stream/store";
import { annotationPath, axis, chooseView, type ViewKind } from "./view";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const plot = $<HTMLCanvasElement>("plot");
const overlay = $<HTMLCanvasElement>("overlay");
const status = $<HTMLDivElement>("status");
const title = $<HTMLDivElement>("title");

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
  ).catch((e: unknown) => (status.textContent = `error: ${String(e)}`));
}

function show(store: DatasetStore, signal: AbortSignal): void {
  const view = chooseView(store.dataset);
  if (!view) {
    status.textContent = `${store.dataset.name}: no v0 view for this shape`;
    return;
  }
  let dirty: [number, number] | null = null;
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
    // age of the newest chunk: glass-to-glass latency while live; data age for history on late join
    latency = Date.now() - Date.parse(u.producedAt);
  });

  const gl = view.kind === "heatmap" && Heatmap.supported(plot) ? new Heatmap(plot) : null;
  let range: Range | null = null;

  const frame = () => {
    if (signal.aborted) return;
    if (dirty) {
      const data = store.get(view.variable);
      if (view.kind === "heatmap") {
        const [rows, cols] = data.shape as [number, number];
        const r = finiteRange(data.values.subarray(dirty[0] * cols, dirty[1] * cols));
        if (r) range = range ? { min: Math.min(range.min, r.min), max: Math.max(range.max, r.max) } : r;
        if (gl) {
          if (gl.shape[0] !== rows || gl.shape[1] !== cols) {
            gl.resize(rows, cols);
            gl.upload(data.values, 0, rows);
          } else gl.upload(data.values, dirty[0], dirty[1]);
          if (range) gl.draw(range);
        } else if (range) {
          plot.width = cols;
          plot.height = rows;
          plot.getContext("2d")!.putImageData(new ImageData(renderRGBA(data.values, [rows, cols], range) as Uint8ClampedArray<ArrayBuffer>, cols, rows), 0, 0);
        }
        drawAnnotations(store, view);
      } else {
        const x = axis(store, view.xDim).values;
        const n = view.latestAlong ? data.shape[1]! : data.values.length;
        const last = view.latestAlong ? data.shape[0]! - 1 : 0;
        if (last >= 0) drawTrace(plot, x as never, data.values.subarray(last * n, (last + 1) * n));
      }
      dirty = null;
    }
    const now = performance.now();
    while (recent.length && recent[0]![0] < now - 1000) recent.shift();
    const rate = recent.reduce((a, [, n]) => a + n, 0);
    status.textContent =
      `${store.dataset.name} · ${view.kind} · seq ${store.lastSeq}${store.complete ? " (complete)" : ""}` +
      ` · ${points.toLocaleString()} pts · ${rate.toLocaleString()} pts/s` +
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

const ws = new URLSearchParams(location.search).get("ws") ?? "ws://127.0.0.1:8765";
start(new WebSocketSource(ws));
