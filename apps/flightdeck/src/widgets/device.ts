// The Device widget (ADR 0089, #164): the device's gates seen from above, drawn to scale from the
// stand server's layout (`GET /device/layout`), each gate filled by the colormap at the DC level it sits
// at (the held level, else the setpoint, from `GET /levels/state`), with a colour bar and a scale bar.
// Labels are sized in screen pixels and written inside a gate only where they fit (`labelFit`, again on
// every resize); the legend under the drawing always lists every gate's level. It reads; it never sets
// a level. The pure parts are `src/control/device.ts`.
import { ApiError } from "../api/client";
import { gradientStops, labelFit, layoutBounds, levelText, paint, scaleBarNm, viewBoxOf, type Box, type GatePaint } from "../control/device";
import { sittingLevels } from "../control/sweeps";
import { COLORMAPS, type Colormap } from "../render/colormap";
import type { DeviceLayout } from "../schema/api";
import { h } from "../workspace/dom";
import type { Widget, WidgetContext } from "../workspace/widget";

const POLL_MS = 2000;
const SVG = "http://www.w3.org/2000/svg";

const s = <K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number> = {}, text?: string): SVGElementTagNameMap[K] => {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  if (text !== undefined) el.textContent = text;
  return el;
};

export const deviceWidget: Widget = {
  id: "device",
  label: "Device",
  sub: "the gates to scale, coloured by the level each sits at",
  single: true,
  mount(body, head, ctx) {
    const w = new DeviceWidget(body, head, ctx);
    return () => w.unmount();
  },
};

interface GateEls {
  shape: SVGPathElement;
  label: SVGTextElement;
  title: SVGTitleElement;
  swatch: HTMLSpanElement;
  value: HTMLSpanElement;
}

/** Text in the drawing that is sized in screen pixels: its element and its size there. */
interface Decor {
  el: SVGElement;
  px: number;
  attr: "font-size" | "stroke-width";
}

class DeviceWidget {
  private layout: DeviceLayout | null = null;
  private levels: Record<string, number> = {};
  private shown = "";
  private cmap: Colormap;
  private timer: ReturnType<typeof setInterval> | null = null;
  private readonly gateEls = new Map<string, GateEls>();
  private painted: GatePaint[] = [];
  private decor: Decor[] = [];
  private svg: SVGSVGElement | null = null;
  private box: Box | null = null;
  private pxPerNm = 0;
  private readonly resize: ResizeObserver | null;
  private readonly frame: HTMLDivElement;
  private readonly legend: HTMLDivElement;
  private readonly scale: HTMLSpanElement;
  private readonly scaleLine: HTMLSpanElement;
  private readonly scaleLabel: HTMLSpanElement;
  private scaleNm = 0;
  private readonly bar: HTMLDivElement;
  private readonly lo: HTMLSpanElement;
  private readonly hi: HTMLSpanElement;
  private readonly foot: HTMLDivElement;
  private readonly offs: (() => void)[] = [];

  constructor(
    private readonly body: HTMLElement,
    private readonly head: HTMLElement,
    private readonly ctx: WidgetContext,
  ) {
    const remembered = (ctx.pane.state ?? {}) as { colormap?: Colormap };
    this.cmap = COLORMAPS.includes(remembered.colormap as Colormap) ? remembered.colormap! : "viridis";
    const pick = h("select", { name: "colormap", attrs: { "aria-label": "Colormap" } }, ...COLORMAPS.map((c) => h("option", { value: c, text: c, selected: c === this.cmap })));
    pick.addEventListener("change", () => {
      this.cmap = pick.value as Colormap;
      ctx.pane.save({ colormap: this.cmap });
      this.shown = "";
      this.render();
    });
    const refresh = h("button", { type: "button", text: "refresh", attrs: { "data-refresh": "" } });
    refresh.addEventListener("click", () => void this.refresh());
    head.append(pick, refresh);
    this.frame = h("div", { className: "frame" });
    this.bar = h("div", { className: "bar" });
    this.lo = h("span", { attrs: { "data-lo": "" } });
    this.hi = h("span", { attrs: { "data-hi": "" } });
    this.foot = h("div", { className: "hint foot" });
    this.legend = h("div", { className: "legend" });
    this.scaleLine = h("span", { className: "line" });
    this.scaleLabel = h("span");
    this.scale = h("span", { className: "sbar", title: "Scale bar" }, this.scaleLine, this.scaleLabel);
    const scale = h("div", { className: "cbar" }, this.scale, this.lo, this.bar, this.hi);
    body.append(h("div", { className: "devmap" }, this.frame, scale, this.legend, this.foot));
    this.resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => this.fit());
    this.resize?.observe(this.frame);
    this.offs.push(
      ctx.bus.on("levels:changed", () => void this.refresh()),
      ctx.bus.on("run:state", ({ run }) => {
        if (run && ["completed", "aborted", "failed"].includes(run.state)) void this.refresh();
      }),
    );
    void this.refresh();
    this.timer = setInterval(() => void this.refresh(), POLL_MS);
  }

  unmount(): void {
    if (this.timer) clearInterval(this.timer);
    this.resize?.disconnect();
    for (const off of this.offs.splice(0)) off();
    this.body.replaceChildren();
    this.head.replaceChildren();
  }

  private async refresh(): Promise<void> {
    if (!this.layout) {
      try {
        this.layout = await this.ctx.api.deviceLayout();
        this.build(this.layout);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          if (this.timer) clearInterval(this.timer);
          this.timer = null;
          this.frame.replaceChildren(h("div", { className: "hint", attrs: { "data-no-layout": "" }, text: "This stand's device has no layout to draw. The simulated stand has one; a real stand has none yet." }));
        } else {
          this.frame.replaceChildren(h("div", { className: "hint", text: `Could not read the device's layout (${describe(e)}); trying again.` }));
        }
        return;
      }
    }
    try {
      this.levels = sittingLevels(await this.ctx.api.levelState());
    } catch (e) {
      this.foot.textContent = `Could not read the levels (${describe(e)}); showing the last ones read.`;
      return;
    }
    this.render();
  }

  /** The static drawing: the area, the channel and sensor outlines, every gate, the scale bar, and a
   * legend row per gate. Text sizes are set by `fit` once the drawing has a size on screen. */
  private build(layout: DeviceLayout): void {
    const box = layoutBounds(layout);
    const width = box.x1 - box.x0;
    const svg = s("svg", { viewBox: viewBoxOf(box), preserveAspectRatio: "xMidYMid meet", role: "img", "aria-label": `Gate layout of device ${layout.device_id}` });
    svg.append(s("rect", { x: box.x0, y: -box.y1, width, height: box.y1 - box.y0, class: "area" }));
    this.decor = [];
    for (const [rect, name] of [
      [layout.channel_nm, "channel"],
      [layout.sensor_nm, "sensor"],
    ] as const) {
      if (!rect) continue;
      const outline = s("rect", { x: rect[0], y: -rect[3], width: rect[1] - rect[0], height: rect[3] - rect[2], class: "region" });
      outline.dataset.region = name;
      svg.append(outline);
      this.decor.push({ el: outline, px: 1.5, attr: "stroke-width" });
    }
    this.gateEls.clear();
    this.legend.replaceChildren();
    for (const g of paint(layout, {}, this.cmap).gates) {
      const shape = s("path", { d: g.path, class: "gate", "data-gate": g.name });
      const title = s("title");
      shape.append(title);
      const label = s("text", { "text-anchor": "middle", "dominant-baseline": "central", class: "glabel" });
      svg.append(shape, label);
      this.decor.push({ el: shape, px: 1.5, attr: "stroke-width" });
      const swatch = h("span", { className: "sw" });
      const value = h("span", { className: "v" });
      this.legend.append(h("span", { className: "item", attrs: { "data-legend": g.name }, title: g.role }, swatch, h("span", { className: "n", text: g.name }), value));
      this.gateEls.set(g.name, { shape, label, title, swatch, value });
    }
    this.scaleNm = scaleBarNm(width);
    this.scaleLabel.textContent = `${this.scaleNm} nm`;
    this.scale.dataset.scaleNm = String(this.scaleNm);
    this.frame.replaceChildren(svg);
    this.svg = svg;
    this.box = box;
    this.pxPerNm = 0;
    this.shown = "";
  }

  /** Screen pixels per nanometre now (the viewBox is fitted inside the frame, `meet`), and every text
   * and stroke sized for it; gate labels re-fitted. A no-op until the drawing has a size. */
  private fit(): void {
    if (!this.svg || !this.box) return;
    const r = this.svg.getBoundingClientRect();
    const px = Math.min(r.width / (this.box.x1 - this.box.x0), r.height / (this.box.y1 - this.box.y0));
    if (!(px > 0) || Math.abs(px - this.pxPerNm) < 1e-6) return;
    this.pxPerNm = px;
    for (const d of this.decor) d.el.setAttribute(d.attr, String(d.px / px));
    this.scaleLine.style.width = `${this.scaleNm * px}px`;
    for (const g of this.painted) this.labelGate(g);
  }

  /** Fill and label every gate at the levels read last; a no-op when nothing changed. */
  private render(): void {
    const layout = this.layout;
    if (!layout) return;
    const { gates, range } = paint(layout, this.levels, this.cmap);
    const key = JSON.stringify([this.cmap, gates.map((g) => g.level)]);
    if (key === this.shown) return;
    this.shown = key;
    this.painted = gates;
    for (const g of gates) this.paintGate(g);
    this.bar.style.background = `linear-gradient(to right, ${gradientStops(this.cmap)})`;
    this.lo.textContent = range ? levelText(range.lo) : "—";
    this.hi.textContent = range ? levelText(range.hi) : "—";
    const unset = gates.filter((g) => g.level === null).map((g) => g.name);
    this.foot.textContent = [
      `${layout.material ? `${layout.material}, ` : ""}${layout.source || `device ${layout.device_id}`}.`,
      "Drawn to scale from the device's declared layout, seen from above. The dashed outlines are the conducting channel and the sensor island.",
      "Each gate shows its DC level: the held level, else the setpoint. Pulses are not shown.",
      unset.length ? `No level for ${unset.join(", ")}.` : "",
    ]
      .filter(Boolean)
      .join(" ");
    // the legend and the note above take their room first, so the drawing is measured after them
    this.fit();
    requestAnimationFrame(() => this.fit());
  }

  private paintGate(g: GatePaint): void {
    const els = this.gateEls.get(g.name);
    if (!els) return;
    els.shape.style.fill = g.fill ?? "";
    els.shape.classList.toggle("unset", g.fill === null);
    els.shape.dataset.level = g.level === null ? "" : String(g.level);
    els.label.style.fill = g.ink;
    els.swatch.style.background = g.fill ?? "";
    els.swatch.classList.toggle("unset", g.fill === null);
    els.value.textContent = levelText(g.level);
    els.title.textContent = `${g.name} (${g.role}) on channel ${g.channel ?? "none"}: ${levelText(g.level)}`;
    this.labelGate(g);
  }

  /** The gate's label at the current scale: name and level, the name alone, or nothing. */
  private labelGate(g: GatePaint): void {
    const els = this.gateEls.get(g.name);
    if (!els) return;
    els.label.replaceChildren();
    const fit = labelFit(g.size, g.vertical, g.name, levelText(g.level), this.pxPerNm);
    if (!fit) return;
    const [cx, cy] = g.centre;
    els.label.setAttribute("x", String(cx));
    els.label.setAttribute("y", String(cy));
    els.label.setAttribute("font-size", String(fit.fontNm));
    els.label.setAttribute("transform", g.vertical ? `rotate(-90 ${cx} ${cy})` : "");
    if (fit.lines.length === 1) els.label.textContent = fit.lines[0]!;
    else fit.lines.forEach((line, i) => els.label.append(s("tspan", { x: cx, dy: (i ? 1.25 : -0.625 * (fit.lines.length - 1)) * fit.fontNm }, line)));
  }
}

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.status} ${e.detail}`;
  return e instanceof Error ? e.message : String(e);
}
