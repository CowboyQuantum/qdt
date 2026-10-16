// The plot widget: the single stage of Step 1–6 as the first centre pane (ADR 0054, deliverable 1).
// Every announced Dataset is selectable; the newest is shown as it arrives; the live map or trace,
// the annotation overlay, the client-side view options (variable, minus, transform, swap) and the
// stream telemetry (emitted as `stream:state` for the strip). What is drawn stays a function of the
// Dataset stream (rule 8); a click on the map goes out as coordinate names and values (ADR 0053).
// One instance this session: the ids `plot`/`overlay`/`datasets`/… are what the e2e tests drive; the
// next session makes N panes over the shared stores and moves these selects into the ⚙ menu.
import { finiteRange, type Range } from "../render/cpu";
import { createMapRenderer, defaultMapRenderer, type MapRenderer, RENDERERS, type RendererName } from "../render/map";
import { drawTrace, type TraceMark } from "../render/trace";
import type { DatasetStore } from "../stream/store";
import {
  annotationPath,
  axis,
  chooseView,
  DEFAULT_OPTIONS,
  difference,
  meanAlongLeading,
  partners,
  pointAt,
  transformMap,
  transpose,
  type Transform,
  type ViewKind,
  type ViewOptions,
} from "../view";
import { h } from "../workspace/dom";
import type { Widget, WidgetContext } from "../workspace/widget";

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

const TRANSFORM_LABEL: Record<Transform, string> = { raw: "raw", d_col: "d/d(inner)", d_row: "d/d(outer)", grad: "|gradient|" };

export const plotWidget: Widget = {
  id: "plot",
  label: "Plot",
  sub: "live stream or a stored record",
  single: true,
  mount(body, head, ctx) {
    const pane = new PlotPane(body, head, ctx);
    return () => pane.unmount();
  },
};

class PlotPane {
  private readonly plot: HTMLCanvasElement;
  private readonly overlay: HTMLCanvasElement;
  private readonly square: HTMLDivElement;
  private readonly datasets: HTMLSelectElement;
  private readonly variableSelect: HTMLSelectElement;
  private readonly minusSelect: HTMLSelectElement;
  private readonly transformSelect: HTMLSelectElement;
  private readonly swapBox: HTMLInputElement;
  private readonly bench: boolean;
  private readonly offs: (() => void)[] = [];
  private readonly resize: ResizeObserver | null;
  private renderer: MapRenderer | null = null;
  private viewAbort: AbortController | null = null;

  constructor(
    private readonly body: HTMLElement,
    private readonly head: HTMLElement,
    private readonly ctx: WidgetContext,
  ) {
    this.bench = ctx.params.get("bench") === "1";
    this.datasets = h("select", { id: "datasets" });
    this.variableSelect = h("select", { id: "variable" });
    this.minusSelect = h("select", { id: "minus" });
    this.transformSelect = h(
      "select",
      { id: "transform" },
      new Option("raw", "raw"),
      new Option("d/d(inner axis)", "d_col"),
      new Option("d/d(outer axis)", "d_row"),
      new Option("|gradient|", "grad"),
    );
    this.swapBox = h("input", { id: "swap", type: "checkbox" });
    head.append(
      h("label", {}, "dataset ", this.datasets),
      h("label", {}, "variable ", this.variableSelect),
      h("label", {}, "minus ", this.minusSelect),
      h("label", {}, "view ", this.transformSelect),
      h("label", {}, this.swapBox, " swap axes"),
    );
    this.plot = h("canvas", { id: "plot", width: 1024, height: 1024 });
    this.overlay = h("canvas", { id: "overlay", width: 1024, height: 1024 });
    this.square = h("div", { className: "square" }, this.plot, this.overlay);
    const stage = h("div", { className: "stage" }, this.square);
    body.append(h("div", { className: "plot" }, stage));
    // the map is square whatever the pane's shape: the largest square that fits the stage
    const fit = () => {
      const s = Math.max(0, Math.min(stage.clientWidth, stage.clientHeight));
      this.square.style.width = `${s}px`;
      this.square.style.height = `${s}px`;
    };
    this.resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(fit);
    this.resize?.observe(stage);
    fit();

    for (const el of [this.variableSelect, this.minusSelect]) {
      const on = () => {
        if (el === this.variableSelect) this.minusSelect.value = ""; // a new variable starts without a subtraction
        const store = ctx.datasets.get(this.datasets.value);
        if (store) this.select(store); // a different display map: restart the view, keep the stream
      };
      el.addEventListener("change", on);
      this.offs.push(() => el.removeEventListener("change", on));
    }
    const onPick = () => {
      const store = ctx.datasets.get(this.datasets.value);
      if (store) this.select(store);
    };
    this.datasets.addEventListener("change", onPick);
    this.offs.push(() => this.datasets.removeEventListener("change", onPick));

    // the shared stores: what is there already, then every new one (the newest is what the user asked for)
    for (const store of ctx.datasets.all()) this.datasets.append(new Option(store.dataset.name, store.dataset.dataset_id));
    const newest = ctx.datasets.all().at(-1);
    if (newest) this.select(newest);
    this.offs.push(
      ctx.datasets.onStore((store) => {
        this.datasets.append(new Option(store.dataset.name, store.dataset.dataset_id));
        this.select(store);
      }),
      ctx.datasets.onSource(() => {
        this.viewAbort?.abort();
        this.datasets.replaceChildren();
        this.state("idle", null, "");
      }),
    );
  }

  unmount(): void {
    this.viewAbort?.abort();
    for (const off of this.offs.splice(0)) off();
    this.resize?.disconnect();
    if (window.__flightdeckRenderer === this.renderer) delete window.__flightdeckRenderer;
    this.renderer = null;
    this.body.replaceChildren();
    this.head.replaceChildren();
    this.state("idle", null, "");
  }

  private state(state: "idle" | "live" | "complete", progress: number | null, summary: string): void {
    this.ctx.bus.emit("stream:state", { state, progress, summary });
  }

  /** Show one store: the previous view's frame loop stops, the renderer and canvases are reused. */
  private select(store: DatasetStore): void {
    this.viewAbort?.abort();
    this.viewAbort = new AbortController();
    this.datasets.value = store.dataset.dataset_id;
    this.fillVariables(store);
    this.show(store, this.viewAbort.signal);
  }

  /** The variable picker keeps its choice across Datasets that have it; "minus" offers same-shape partners. */
  private fillVariables(store: DatasetStore): void {
    const names = store.dataset.data_vars.map((v) => v.name);
    const had = this.variableSelect.value;
    this.variableSelect.replaceChildren(...names.map((n) => new Option(n, n)));
    this.variableSelect.value = names.includes(had) ? had : (names[0] ?? "");
    const minusHad = this.minusSelect.value;
    const others = partners(store.dataset, this.variableSelect.value);
    this.minusSelect.replaceChildren(new Option("—", ""), ...others.map((n) => new Option(n, n)));
    this.minusSelect.value = others.includes(minusHad) ? minusHad : "";
  }

  private options(): ViewOptions {
    return { swap: this.swapBox.checked, transform: this.transformSelect.value as Transform };
  }

  private makeRenderer(): MapRenderer {
    const name = this.ctx.params.get("renderer");
    if (name && (RENDERERS as readonly string[]).includes(name)) return createMapRenderer(name as RendererName, this.plot);
    return defaultMapRenderer(this.plot);
  }

  private show(store: DatasetStore, signal: AbortSignal): void {
    const { plot, overlay, bench } = this;
    const view = chooseView(store.dataset, this.variableSelect.value);
    const minus = view && partners(store.dataset, view.variable).includes(this.minusSelect.value) ? this.minusSelect.value : "";
    let diff: Float64Array | null = null;
    const displayed = () => {
      const data = store.get(view!.variable);
      if (!minus) return data;
      const d = difference(data, store.get(minus), diff);
      diff = d.values as Float64Array;
      return d;
    };
    if (!view) {
      this.state("idle", null, `${store.dataset.name}: no v0 view for this shape`);
      return;
    }
    if (view.kind === "heatmap" && !this.renderer) this.renderer = this.makeRenderer();
    const renderer = this.renderer;
    // the map renderer owns `plot` (a WebGL context refuses a 2-D one afterwards), so a trace draws on the
    // 2-D overlay canvas and the map canvas is hidden under it
    plot.style.visibility = view.kind === "heatmap" ? "" : "hidden";
    const state: BenchState = { renderer: view.kind === "heatmap" ? (renderer?.name ?? "cpu") : "trace", samples: [], frames: 0, complete: false, error: null };
    if (bench) window.__flightdeck = state;
    if (renderer) window.__flightdeckRenderer = renderer;
    // display only: a registry replay names its record (ADR 0027); nothing branches on where data came from
    const ref = store.dataset.source.registry_ref;
    const title = ref ? `record ${ref} · ${store.dataset.name}` : store.dataset.name;

    const rowDim = view.kind === "heatmap" ? view.rowDim : view.latestAlong;
    const totalRows = () => {
      const shape = store.get(view.variable).shape;
      return view.kind === "heatmap" && view.stackDim ? shape[1]! : shape[0]!;
    };
    const current = store.get(view.variable).shape;
    let dirty: [number, number] | null = current[0] ? [0, totalRows()] : null;
    let received = 0; // rows seen so far along the row dim: the progress bar
    let pending: [number, number][] = []; // [produced_at ms, points] of chunks not yet drawn
    let points = 0;
    let latency = NaN;
    const recent: [number, number][] = []; // [time ms, points]
    let overlaysDirty = store.annotations.size > 0;
    const offAnnotation = store.onAnnotation(() => (overlaysDirty = true));
    signal.addEventListener("abort", offAnnotation, { once: true });
    const offUpdate = store.onUpdate((u) => {
      const rows = u.region.find((s) => s.dim === rowDim);
      const [r0, r1] = rows ? [rows.start, rows.stop] : [0, 1];
      dirty = dirty ? [Math.min(dirty[0], r0), Math.max(dirty[1], r1)] : [r0, r1];
      received = Math.max(received, r1);
      const n = u.region.reduce((a, s) => a * (s.stop - s.start), 1);
      points += n;
      recent.push([performance.now(), n]);
      pending.push([Date.parse(u.producedAt), n]);
    });
    signal.addEventListener("abort", offUpdate, { once: true });

    let range: Range | null = null;
    let mean: Float64Array | null = null; // display map for a stacked heatmap: mean over the stack dim
    let derived: Float64Array | null = null; // transformed map
    let swapped: Float64Array | null = null; // transposed map
    let shown: ViewOptions = { ...DEFAULT_OPTIONS };
    const onOptions = () => {
      const o = this.options();
      if (o.swap === shown.swap && o.transform === shown.transform) return;
      shown = o;
      range = null;
      dirty = [0, totalRows()];
      overlaysDirty = true;
    };
    this.transformSelect.addEventListener("change", onOptions);
    this.swapBox.addEventListener("change", onOptions);
    signal.addEventListener(
      "abort",
      () => {
        this.transformSelect.removeEventListener("change", onOptions);
        this.swapBox.removeEventListener("change", onOptions);
      },
      { once: true },
    );
    shown = this.options();

    /** The latest record of a trace view, with every 1-coordinate marker on its x axis as a rule. */
    const drawTraceView = (data: ReturnType<typeof displayed>) => {
      if (view.kind !== "trace") return;
      const x = axis(store, view.xDim);
      const n = view.latestAlong ? data.shape[1]! : data.values.length;
      const last = view.latestAlong ? data.shape[0]! - 1 : 0;
      if (last < 0) return;
      const marks: TraceMark[] = [];
      for (const ann of store.annotations.values()) {
        if (ann.kind === "marker" && ann.coords.length === 1 && ann.coords[0] === x.name) marks.push({ x: ann.points[0]![0]!, label: ann.label ?? "" });
      }
      drawTrace(overlay, x.values as never, data.values.subarray(last * n, (last + 1) * n), marks);
    };

    // click-to-set (ADR 0053): a click on the map offers the point under it, as coordinate names and
    // values; whoever holds the stand's channels decides which are settable (rule 8: not this widget)
    const onClick = (e: MouseEvent) => {
      if (view.kind !== "heatmap") return;
      const r = overlay.getBoundingClientRect();
      if (!r.width || !r.height) return;
      const fx = (e.clientX - r.left) / r.width;
      const fy = 1 - (e.clientY - r.top) / r.height;
      this.ctx.bus.emit("map:click", { point: pointAt(store, view, fx, fy, shown.swap) });
    };
    // both canvases: whichever is on top receives the click (the overlay may not take pointer events)
    overlay.addEventListener("click", onClick);
    plot.addEventListener("click", onClick);
    signal.addEventListener(
      "abort",
      () => {
        overlay.removeEventListener("click", onClick);
        plot.removeEventListener("click", onClick);
      },
      { once: true },
    );

    const frame = () => {
      if (signal.aborted) return;
      if (dirty) {
        const data = displayed();
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
          this.drawOverlay(store, view, shown);
        } else if (view.kind === "trace") {
          drawTraceView(data);
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
        this.drawOverlay(store, view, shown); // overlays that arrived after the last chunk
        overlaysDirty = false;
      } else if (overlaysDirty && view.kind === "trace") {
        drawTraceView(displayed());
        overlaysDirty = false;
      }
      const now = performance.now();
      while (recent.length && recent[0]![0] < now - 1000) recent.shift();
      const rate = recent.reduce((a, [, n]) => a + n, 0);
      const summary =
        `${title} · ${view.variable}${minus ? ` − ${minus}` : ""} · ${view.kind}${renderer && view.kind === "heatmap" ? ` (${renderer.name})` : ""}` +
        (view.kind === "heatmap" && view.stackDim ? ` · mean over ${store.get(view.variable).shape[0]} ${view.stackDim}` : "") +
        (view.kind === "heatmap" && shown.transform !== "raw" ? ` · ${TRANSFORM_LABEL[shown.transform]} (per step)` : "") +
        (view.kind === "heatmap" && shown.swap ? " · axes swapped" : "") +
        ` · seq ${store.lastSeq}` +
        `${store.complete ? " (complete)" : ""} · ${points.toLocaleString()} pts · ${rate.toLocaleString()} pts/s` +
        (Number.isFinite(latency) ? ` · last chunk age ${latency.toFixed(0)} ms` : "");
      const total = totalRows();
      this.state(store.complete ? "complete" : recent.length ? "live" : "idle", total ? Math.min(1, received / total) : null, summary);
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }

  /** Axis names, units and extents on the overlay canvas: which coordinate runs which way. */
  private drawAxes(store: DatasetStore, view: Extract<ViewKind, { kind: "heatmap" }>, swap: boolean): void {
    const { overlay } = this;
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

  private drawOverlay(store: DatasetStore, view: Extract<ViewKind, { kind: "heatmap" }>, o: ViewOptions): void {
    this.drawAnnotations(store, view, o.swap);
    this.drawAxes(store, view, o.swap);
  }

  private drawAnnotations(store: DatasetStore, view: Extract<ViewKind, { kind: "heatmap" }>, swap: boolean): void {
    const { overlay } = this;
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
}
