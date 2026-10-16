// The plot widget (ADR 0054, 0055): any number of panes in the centre, each with its own renderer, view
// options and line cut over the shared Dataset stores. A pane either follows the live stream (the newest
// Dataset as it arrives) or is pinned to one Dataset; History opens a stored record in a pane through
// `plot:open`. The ⚙ menu holds what the old header selects did. What is drawn stays a function of the
// Dataset stream (rule 8); a click on the map goes out as coordinate names and values (ADR 0053).
import { finiteRange, type Range } from "../render/cpu";
import { columnCut, displayMap, scratch, type DisplayMap } from "../render/display";
import { type Colormap, COLORMAPS } from "../render/colormap";
import { createMapRenderer, defaultMapRenderer, type MapRenderer, RENDERERS, type RendererName } from "../render/map";
import { drawTrace, type TraceMark } from "../render/trace";
import type { DatasetStore } from "../stream/store";
import { annotationPath, axis, chooseView, meanAlongLeading, partners, pointAt, type Transform, type ViewKind, type ViewOptions } from "../view";
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
const short = (id: string) => id.slice(0, 8);

export const plotWidget: Widget = {
  id: "plot",
  label: "Plot",
  sub: "live stream or a stored record",
  mount(body, head, ctx) {
    const pane = new PlotPane(body, head, ctx);
    return () => pane.unmount();
  },
};

class PlotPane {
  private readonly map: HTMLCanvasElement;
  private readonly overlay: HTMLCanvasElement;
  private readonly cutCanvas: HTMLCanvasElement;
  private readonly square: HTMLDivElement;
  private readonly src: HTMLSpanElement;
  private readonly menuButton: HTMLButtonElement;
  private readonly bench: boolean;
  private readonly offs: (() => void)[] = [];
  private readonly resize: ResizeObserver | null;
  private renderer: MapRenderer | null = null;
  private viewAbort: AbortController | null = null;
  private menu: HTMLElement | null = null;
  // view state: what this pane shows and how
  private follow = true;
  /** The record this pane was asked to show, until its Dataset arrives (then: what it is pinned to). */
  private pendingRef: string | null = null;
  private pendingPlan: string | null = null;
  private pinnedRecord: string | null = null;
  private shown: DatasetStore | null = null;
  private variable = "";
  private minus = "";
  private transform: Transform = "raw";
  private swap = false;
  private cut = 0.5;
  private colormap: Colormap = "viridis";
  /** Set by the running view so a menu change reaches its frame loop. */
  private onOptions: (() => void) | null = null;

  constructor(
    private readonly body: HTMLElement,
    private readonly head: HTMLElement,
    private readonly ctx: WidgetContext,
  ) {
    this.bench = ctx.params.get("bench") === "1";
    // the pane remembers its view across a reload (ADR 0061); a URL parameter wins for the pixel tests
    const remembered = (ctx.pane.state ?? {}) as Partial<{ variable: string; minus: string; transform: Transform; swap: boolean; cut: number; colormap: Colormap; follow: boolean }>;
    if (typeof remembered.variable === "string") this.variable = remembered.variable;
    if (typeof remembered.minus === "string") this.minus = remembered.minus;
    if (remembered.transform && ["raw", "d_col", "d_row", "grad"].includes(remembered.transform)) this.transform = remembered.transform;
    if (typeof remembered.swap === "boolean") this.swap = remembered.swap;
    if (typeof remembered.cut === "number" && remembered.cut >= 0 && remembered.cut <= 1) this.cut = remembered.cut;
    if (remembered.colormap && (COLORMAPS as readonly string[]).includes(remembered.colormap)) this.colormap = remembered.colormap;
    const urlMap = ctx.params.get("colormap");
    if (urlMap && (COLORMAPS as readonly string[]).includes(urlMap)) this.colormap = urlMap as Colormap;
    this.src = h("span", { className: "src", text: "live" });
    this.menuButton = h("button", { className: "icon", type: "button", text: "⚙", title: "View settings", attrs: { "data-menu": "", "aria-label": "View settings", "aria-haspopup": "menu", "aria-expanded": "false" } });
    head.append(this.src, this.menuButton);
    this.map = h("canvas", { className: "map", width: 1024, height: 1024 });
    this.overlay = h("canvas", { className: "overlay", width: 1024, height: 1024 });
    this.cutCanvas = h("canvas", { className: "cut", attrs: { "aria-label": "line cut" } });
    this.square = h("div", { className: "square" }, this.map, this.overlay);
    const stage = h("div", { className: "stage" }, this.square);
    body.append(h("div", { className: "plot" }, stage, this.cutCanvas));
    // the map is square whatever the pane's shape: the largest square that fits the stage
    const fit = () => {
      const s = Math.max(0, Math.min(stage.clientWidth, stage.clientHeight));
      this.square.style.width = `${s}px`;
      this.square.style.height = `${s}px`;
    };
    this.resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(fit);
    this.resize?.observe(stage);
    fit();

    this.menuButton.addEventListener("click", (e) => {
      e.stopPropagation();
      this.toggleMenu();
    });

    // the shared stores: the newest now, then every new one while following; a record this pane waits for
    const newest = ctx.datasets.all().at(-1);
    if (newest) this.select(newest);
    this.offs.push(
      ctx.datasets.onStore((store) => {
        // display only: a registry replay names its record (ADR 0027); nothing branches on where data came from
        if (this.pendingRef && this.isRecord(store, this.pendingRef, this.pendingPlan)) {
          this.pinnedRecord = this.pendingRef;
          this.pendingRef = this.pendingPlan = null;
          this.follow = false;
          this.select(store);
        } else if (this.follow) this.select(store);
        this.refreshMenu();
      }),
      ctx.datasets.onSource(() => {
        this.viewAbort?.abort();
        this.shown = null;
        this.follow = true;
        this.pendingRef = this.pendingPlan = this.pinnedRecord = null;
        this.announce();
        this.refreshMenu();
      }),
      ctx.bus.on("plot:open", ({ recordId, planId, paneId }) => {
        if (paneId === ctx.paneId) this.openRecord(recordId, planId);
      }),
    );
    this.announce();
  }

  unmount(): void {
    this.closeMenu();
    this.viewAbort?.abort();
    for (const off of this.offs.splice(0)) off();
    this.resize?.disconnect();
    if (window.__flightdeckRenderer === this.renderer) delete window.__flightdeckRenderer;
    this.renderer?.dispose();
    this.renderer = null;
    this.body.replaceChildren();
    this.head.replaceChildren();
    if (this.follow) this.state("idle", null, "");
    this.ctx.bus.emit("plot:view", { paneId: this.ctx.paneId, datasetId: null, registryRef: null, name: "" });
  }

  // --- what this pane shows -----------------------------------------------------------------------

  /** The Dataset that is a record: a replay names it by registry ref (ADR 0027); a run still on the stream
   * is the record's plan id, and the server then publishes only the overlays. Ids only, never a producer. */
  private isRecord(store: DatasetStore, recordId: string, planId: string | null): boolean {
    return store.dataset.source.registry_ref === recordId || (!!planId && store.dataset.dataset_id === planId);
  }

  /** Pin to the Dataset that is the record, now if it is on the stream already, else when it arrives. */
  private openRecord(recordId: string, planId: string): void {
    this.follow = false;
    const existing = this.ctx.datasets.all().find((s) => this.isRecord(s, recordId, planId));
    if (existing) {
      this.pendingRef = this.pendingPlan = null;
      this.pinnedRecord = recordId;
      this.select(existing);
    } else {
      this.pendingRef = recordId;
      this.pendingPlan = planId;
      this.src.textContent = `opening ${short(recordId)}…`;
    }
    this.refreshMenu();
  }

  private announce(): void {
    const s = this.shown;
    const ref = s?.dataset.source.registry_ref ?? (!this.follow ? this.pinnedRecord : null);
    this.src.textContent = s ? `${this.follow ? "live" : "pinned"} · ${ref ? `record ${short(ref)}` : s.dataset.name}` : this.pendingRef ? `opening ${short(this.pendingRef)}…` : this.follow ? "live" : "pinned";
    this.ctx.bus.emit("plot:view", { paneId: this.ctx.paneId, datasetId: s?.dataset.dataset_id ?? null, registryRef: ref, name: s?.dataset.name ?? "" });
  }

  private state(state: "idle" | "live" | "complete", progress: number | null, summary: string): void {
    if (this.follow) this.ctx.bus.emit("stream:state", { state, progress, summary });
  }

  /** Show one store: the previous view's frame loop stops, the renderer and canvases are reused. */
  private select(store: DatasetStore): void {
    this.viewAbort?.abort();
    this.viewAbort = new AbortController();
    this.shown = store;
    const names = store.dataset.data_vars.map((v) => v.name);
    if (!names.includes(this.variable)) this.variable = names[0] ?? "";
    if (!partners(store.dataset, this.variable).includes(this.minus)) this.minus = "";
    this.announce();
    this.show(store, this.viewAbort.signal);
  }

  private options(): ViewOptions {
    return { swap: this.swap, transform: this.transform };
  }

  /** What the pane remembers across a reload: its view, never a dataset id (the stream is new each time). */
  private remember(): void {
    this.ctx.pane.save({ variable: this.variable, minus: this.minus, transform: this.transform, swap: this.swap, cut: this.cut, colormap: this.colormap });
  }

  // --- the ⚙ menu ----------------------------------------------------------------------------------

  private toggleMenu(): void {
    if (this.menu) return this.closeMenu();
    const menu = h("div", { className: "menu plot", attrs: { role: "menu", "aria-label": "View settings" } });
    this.menu = menu;
    this.fillMenu();
    const pane = this.body.closest(".pane") ?? this.body;
    pane.append(menu);
    this.menuButton.setAttribute("aria-expanded", "true");
    menu.addEventListener("click", (e) => e.stopPropagation());
    menu.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        this.closeMenu();
        this.menuButton.focus();
        return;
      }
      if (e.key !== "Tab") return;
      // focus stays in the menu until it closes
      const items = [...menu.querySelectorAll<HTMLElement>("select, input, button")].filter((el) => !el.hasAttribute("disabled"));
      if (!items.length) return;
      const first = items[0]!;
      const last = items[items.length - 1]!;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    });
    document.addEventListener("click", this.onDocClick);
    (menu.querySelector("select, input, button") as HTMLElement | null)?.focus();
  }

  private readonly onDocClick = (): void => this.closeMenu();

  private closeMenu(): void {
    if (!this.menu) return;
    this.menu.remove();
    this.menu = null;
    this.menuButton.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", this.onDocClick);
  }

  /** Rebuild the menu's option lists when the stores change while it is open. */
  private refreshMenu(): void {
    if (this.menu) this.fillMenu();
  }

  private fillMenu(): void {
    const menu = this.menu!;
    const active = document.activeElement instanceof HTMLElement && menu.contains(document.activeElement) ? (document.activeElement as HTMLInputElement | HTMLSelectElement).name : null;
    const row = (label: string, control: HTMLElement) => h("label", { className: "row" }, label, control);
    const stores = this.ctx.datasets.all();
    const dataset = h(
      "select",
      { name: "dataset", attrs: { "aria-label": "Dataset shown in this pane" } },
      new Option("live — follow the stream", "live"),
      ...stores.map((s) => new Option(`${s.dataset.name}${s.dataset.source.registry_ref ? ` · record ${short(s.dataset.source.registry_ref)}` : ""}`, s.dataset.dataset_id)),
    );
    dataset.value = this.follow || !this.shown ? "live" : this.shown.dataset.dataset_id;
    dataset.addEventListener("change", () => {
      if (dataset.value === "live") {
        this.follow = true;
        this.pendingRef = this.pendingPlan = this.pinnedRecord = null;
        const newest = stores.at(-1);
        if (newest && newest !== this.shown) this.select(newest);
        else this.announce();
      } else {
        this.follow = false;
        this.pendingRef = this.pendingPlan = this.pinnedRecord = null;
        const s = this.ctx.datasets.get(dataset.value);
        if (s) this.select(s);
      }
      this.fillMenu();
    });
    const names = this.shown?.dataset.data_vars.map((v) => v.name) ?? [];
    const variable = h("select", { name: "variable", disabled: !names.length }, ...names.map((n) => new Option(n, n)));
    variable.value = this.variable;
    variable.addEventListener("change", () => {
      this.variable = variable.value;
      this.minus = ""; // a new variable starts without a subtraction
      if (this.shown) this.select(this.shown); // a different display map: restart the view, keep the stream
      this.remember();
      this.fillMenu();
    });
    const others = this.shown ? partners(this.shown.dataset, this.variable) : [];
    const minus = h("select", { name: "minus", disabled: !others.length }, new Option("—", ""), ...others.map((n) => new Option(n, n)));
    minus.value = this.minus;
    minus.addEventListener("change", () => {
      this.minus = minus.value;
      if (this.shown) this.select(this.shown);
      this.remember();
    });
    const transform = h(
      "select",
      { name: "transform" },
      new Option("raw", "raw"),
      new Option("d/d(inner axis)", "d_col"),
      new Option("d/d(outer axis)", "d_row"),
      new Option("|gradient|", "grad"),
    );
    transform.value = this.transform;
    transform.addEventListener("change", () => {
      this.transform = transform.value as Transform;
      this.onOptions?.();
      this.remember();
    });
    const cmap = h("select", { name: "colormap" }, ...COLORMAPS.map((c) => new Option(c, c)));
    cmap.value = this.colormap;
    cmap.addEventListener("change", () => {
      this.colormap = cmap.value as Colormap;
      this.renderer?.setColormap(this.colormap);
      this.onOptions?.();
      this.remember();
    });
    const swap = h("input", { name: "swap", type: "checkbox", checked: this.swap });
    swap.addEventListener("change", () => {
      this.swap = swap.checked;
      this.onOptions?.();
      this.remember();
    });
    const cutValue = h("span", { className: "mono", text: this.cutLabel() });
    const cut = h("input", { name: "cut", type: "range", min: "0", max: "1", step: "0.01", value: String(this.cut), attrs: { "aria-label": "Line cut position" } });
    cut.addEventListener("input", () => {
      this.cut = Number(cut.value);
      cutValue.textContent = this.cutLabel();
      this.onOptions?.();
    });
    cut.addEventListener("change", () => this.remember());
    menu.replaceChildren(
      row("dataset", dataset),
      row("variable", variable),
      row("minus", minus),
      row("view", transform),
      row("colormap", cmap),
      h("label", { className: "row" }, h("span", { text: "swap axes" }), swap),
      h("label", { className: "row" }, h("span", {}, "cut at ", cutValue), cut),
      h("div", { className: "row hint", text: "click the map to set the gates there; the cut follows the slider" }),
    );
    if (active) (menu.querySelector(`[name="${active}"]`) as HTMLElement | null)?.focus();
  }

  /** The cut's position in the shown map's x coordinate, for the menu. */
  private cutLabel(): string {
    const s = this.shown;
    if (!s) return "—";
    const view = chooseView(s.dataset, this.variable);
    if (!view || view.kind !== "heatmap") return "—";
    const x = axis(s, this.swap ? view.rowDim : view.colDim);
    const i = Math.round(this.cut * (x.values.length - 1));
    const v = Number(x.values[i] ?? NaN);
    return Number.isFinite(v) ? `${x.name} = ${Number(v.toPrecision(4))}${x.unit ? ` ${x.unit}` : ""}` : "—";
  }

  // --- drawing -------------------------------------------------------------------------------------

  private makeRenderer(): MapRenderer {
    const name = this.ctx.params.get("renderer");
    if (name && (RENDERERS as readonly string[]).includes(name)) return createMapRenderer(name as RendererName, this.map);
    return defaultMapRenderer(this.map);
  }

  private show(store: DatasetStore, signal: AbortSignal): void {
    const { map: plot, overlay, bench } = this;
    const view = chooseView(store.dataset, this.variable);
    const minus = view && partners(store.dataset, view.variable).includes(this.minus) ? this.minus : "";
    let diff: Float64Array | null = null;
    const displayed = () => {
      const data = store.get(view!.variable);
      if (!minus) return data;
      const d = difference(data, store.get(minus), diff);
      diff = d.values as Float64Array;
      return d;
    };
    if (!view) {
      this.cutCanvas.hidden = true;
      this.state("idle", null, `${store.dataset.name}: no v0 view for this shape`);
      return;
    }
    if (view.kind === "heatmap" && !this.renderer) {
      this.renderer = this.makeRenderer();
      this.renderer.setColormap(this.colormap);
    }
    const renderer = this.renderer;
    // the map renderer owns the map canvas (a WebGL context refuses a 2-D one afterwards), so a trace draws
    // on the 2-D overlay canvas and the map canvas is hidden under it
    plot.style.visibility = view.kind === "heatmap" ? "" : "hidden";
    this.cutCanvas.hidden = view.kind !== "heatmap";
    const state: BenchState = { renderer: view.kind === "heatmap" ? (renderer?.name ?? "cpu") : "trace", samples: [], frames: 0, complete: false, error: null };
    if (bench && this.follow) window.__flightdeck = state;
    if (renderer && this.follow) window.__flightdeckRenderer = renderer;
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
    let cutDirty = true;
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
    let mean: Float64Array | null = null; // display map for a stacked heatmap on the live path: mean over the stack dim
    const scratchBuffers = scratch();
    let last: DisplayMap | null = null; // what was uploaded last: the cut reads it
    let shown: ViewOptions = this.options();
    let cutAt = this.cut;
    let shownMap = this.colormap;
    this.onOptions = () => {
      const o = this.options();
      if (o.swap !== shown.swap || o.transform !== shown.transform || shownMap !== this.colormap) {
        shownMap = this.colormap;
        shown = o;
        range = null;
        dirty = [0, totalRows()];
        overlaysDirty = true;
      }
      if (this.cut !== cutAt) {
        cutAt = this.cut;
        cutDirty = true;
        overlaysDirty = true;
      }
    };
    signal.addEventListener("abort", () => (this.onOptions = null), { once: true });

    /** The latest record of a trace view, with every 1-coordinate marker on its x axis as a rule. */
    const drawTraceView = (data: ReturnType<typeof displayed>) => {
      if (view.kind !== "trace") return;
      const x = axis(store, view.xDim);
      const n = view.latestAlong ? data.shape[1]! : data.values.length;
      const lastRecord = view.latestAlong ? data.shape[0]! - 1 : 0;
      if (lastRecord < 0) return;
      const marks: TraceMark[] = [];
      for (const ann of store.annotations.values()) {
        if (ann.kind === "marker" && ann.coords.length === 1 && ann.coords[0] === x.name) marks.push({ x: ann.points[0]![0]!, label: ann.label ?? "" });
      }
      drawTrace(overlay, x.values as never, data.values.subarray(lastRecord * n, (lastRecord + 1) * n), marks);
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
          const [rows, cols] = data.shape.slice(-2) as [number, number];
          const plain = shown.transform === "raw" && !shown.swap;
          if (plain) {
            // the live path: only the dirty rows are mapped and uploaded (the bench measures this)
            let map = data.values;
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
            last = { values: map, rows, cols, range };
          } else {
            // a view option: recompute the whole display map client-side (no round trip)
            const d = displayMap(data, !!view.stackDim, shown, scratchBuffers);
            range = d.range;
            if (r2.shape[0] !== d.rows || r2.shape[1] !== d.cols) r2.resize(d.rows, d.cols);
            r2.upload(d.values, 0, d.rows);
            last = d;
          }
          if (range) r2.draw(range);
          if (bench) r2.finish();
          this.drawOverlay(store, view, shown, cutAt);
          cutDirty = true;
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
        this.drawOverlay(store, view, shown, cutAt); // overlays that arrived after the last chunk
        overlaysDirty = false;
      } else if (overlaysDirty && view.kind === "trace") {
        drawTraceView(displayed());
        overlaysDirty = false;
      }
      if (cutDirty && last) {
        this.drawCut(last, cutAt);
        cutDirty = false;
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

  /** The line cut under the map: one column of the display map at the cursor, bottom row first. */
  private drawCut(map: DisplayMap, at: number): void {
    const c = this.cutCanvas;
    const dpr = window.devicePixelRatio || 1;
    const w = (c.width = Math.max(1, Math.round(c.clientWidth * dpr)));
    const hgt = (c.height = Math.max(1, Math.round(c.clientHeight * dpr)));
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, w, hgt);
    const col = columnCut(map, at);
    const r = finiteRange(col);
    if (!r || col.length < 2) return;
    const span = r.max - r.min || 1;
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--live").trim() || "#f2b544";
    ctx.lineWidth = 1.5 * dpr;
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < col.length; i++) {
      const v = col[i]!;
      if (!Number.isFinite(v)) continue;
      const x = (i / (col.length - 1)) * w;
      const y = hgt - 6 * dpr - ((v - r.min) / span) * (hgt - 12 * dpr);
      if (started) ctx.lineTo(x, y);
      else ctx.moveTo(x, y);
      started = true;
    }
    ctx.stroke();
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

  private drawOverlay(store: DatasetStore, view: Extract<ViewKind, { kind: "heatmap" }>, o: ViewOptions, cutAt: number): void {
    this.drawAnnotations(store, view, o.swap);
    this.drawCursor(cutAt);
    this.drawAxes(store, view, o.swap);
  }

  /** The cut's position as a dashed rule on the overlay. */
  private drawCursor(at: number): void {
    const ctx = this.overlay.getContext("2d")!;
    const { width: w, height: h } = this.overlay;
    ctx.save();
    ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--live").trim() || "#f2b544";
    ctx.setLineDash([8, 8]);
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(at * w, 0);
    ctx.lineTo(at * w, h);
    ctx.stroke();
    ctx.restore();
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

// `difference` lives in view.ts; imported here under its own name to keep the frame loop readable
import { difference } from "../view";
