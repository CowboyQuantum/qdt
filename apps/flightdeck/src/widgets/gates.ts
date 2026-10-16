// The Virtual gates widget (ADR 0049, 0057): the coupling matrix a stepped axis carries. A row is a
// DC channel used as a sweep axis; its off-diagonal entries are the volts per volt by which other DC
// channels move with it (`SweepAxis.couplings`). The Sweep widget takes each stepped axis's row
// (`gates:couplings`). A stage axis cannot couple (it expresses its couplings in the pulse sequence,
// Affine); the widget says so for the inner axis of a stage sweep. Per browser; never stored on the server.
import type { ChannelMap } from "../schema/api";
import { standChannels } from "../control/sweeps";
import { h } from "../workspace/dom";
import { safeStorage } from "../workspace/layout";
import type { Widget, WidgetContext } from "../workspace/widget";

/** axis channel → companion channel → volts per volt. Diagonal and zero entries are implicit. */
export type CouplingMatrix = Record<string, Record<string, number>>;

/** The `SweepAxis.couplings` for an axis channel: its row without the diagonal and without zeros. Pure. */
export function couplingsFor(matrix: CouplingMatrix, channel: string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [other, v] of Object.entries(matrix[channel] ?? {})) if (other !== channel && Number.isFinite(v) && v !== 0) out[other] = v;
  return out;
}

/** Parse a stored matrix: only finite numbers over known channels survive. Pure. */
export function parseMatrix(text: string | null, channels: readonly string[]): CouplingMatrix {
  if (!text) return {};
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return {};
  }
  if (!raw || typeof raw !== "object") return {};
  const out: CouplingMatrix = {};
  for (const [axis, row] of Object.entries(raw as Record<string, unknown>)) {
    if (!channels.includes(axis) || !row || typeof row !== "object") continue;
    for (const [other, v] of Object.entries(row as Record<string, unknown>)) {
      if (channels.includes(other) && other !== axis && typeof v === "number" && Number.isFinite(v) && v !== 0) (out[axis] ??= {})[other] = v;
    }
  }
  return out;
}

const KEY = "flightdeck.gates.v1";

export const gatesWidget: Widget = {
  id: "gates",
  label: "Virtual gates",
  sub: "coupling matrix: volts per volt a stepped axis moves other gates",
  single: true,
  mount(body, head, ctx) {
    const w = new GatesWidget(body, head, ctx);
    return () => w.unmount();
  },
};

class GatesWidget {
  private dc: ChannelMap[] = [];
  private matrix: CouplingMatrix = {};
  private stageInner = "";
  private offer: { node: string; gates: [string, string]; c_21: number; c_12: number } | null = null;
  private readonly offerBox: HTMLDivElement;
  private readonly grid: HTMLDivElement;
  private readonly note: HTMLDivElement;
  private readonly offs: (() => void)[] = [];

  constructor(
    private readonly body: HTMLElement,
    private readonly head: HTMLElement,
    private readonly ctx: WidgetContext,
  ) {
    this.grid = h("div", { className: "grid" });
    this.note = h("div", { className: "foot hint" });
    this.offerBox = h("div", { className: "offer" });
    const reset = h("button", { type: "button", text: "identity", title: "No couplings: every axis moves its own gate only", attrs: { "data-reset": "" } });
    reset.addEventListener("click", () => {
      this.matrix = {};
      this.save();
      this.render();
      this.publish();
    });
    head.append(reset);
    body.append(h("div", { className: "matrix" }, h("div", { className: "hint", text: "row: the gate an axis steps; columns: how much each other gate moves with it (V/V). A stepped axis takes its row as SweepAxis.couplings (ADR 0049)." }), this.grid, this.offerBox, this.note));
    this.offs.push(
      ctx.bus.on("sweep:axes", ({ kind, inner }) => {
        this.stageInner = kind === "stage" ? inner.replace(/_pulse$/, "") : "";
        this.render();
      }),
      ctx.bus.on("layout:changed", () => this.publish()),
      // a finished tune-up's virtual-gate coefficients (ADR 0049) are offered, never applied unasked
      ctx.bus.on("tuneup:outputs", (o) => {
        this.offer = o;
        this.renderOffer();
      }),
    );
    void ctx.api
      .stand()
      .then((s) => {
        this.dc = standChannels(s).dc;
        try {
          this.matrix = parseMatrix(safeStorage()?.getItem(KEY) ?? null, this.dc.map((c) => c.logical));
        } catch {
          this.matrix = {};
        }
        this.render();
        this.publish();
      })
      .catch((e: unknown) => ctx.bus.emit("say", { text: `server: ${String(e)}`, error: true }));
  }

  unmount(): void {
    for (const off of this.offs.splice(0)) off();
    this.body.replaceChildren();
    this.head.replaceChildren();
    this.ctx.bus.emit("gates:couplings", { matrix: {} });
  }

  private save(): void {
    try {
      safeStorage()?.setItem(KEY, JSON.stringify(this.matrix));
    } catch {
      /* no storage */
    }
  }

  private publish(): void {
    this.ctx.bus.emit("gates:couplings", { matrix: this.matrix });
  }

  /** "apply c_21, c_12 from node X": row g1 ← g2 = c_21 (moving virtual gate 1 moves g2 by c_21 V/V), row g2 ← g1 = c_12. */
  private renderOffer(): void {
    const o = this.offer;
    if (!o) return this.offerBox.replaceChildren();
    const [g1, g2] = o.gates;
    const apply = h("button", { type: "button", text: `apply from ${o.node}: ${g1}→${g2} = ${o.c_21.toPrecision(3)}, ${g2}→${g1} = ${o.c_12.toPrecision(3)}`, attrs: { "data-apply": "" } });
    apply.addEventListener("click", () => {
      (this.matrix[g1] ??= {})[g2] = o.c_21;
      (this.matrix[g2] ??= {})[g1] = o.c_12;
      this.save();
      this.render();
      this.publish();
      this.ctx.bus.emit("say", { text: `virtual gates: ${g1}/${g2} couplings taken from ${o.node}`, error: false });
    });
    this.offerBox.replaceChildren(apply);
  }

  private render(): void {
    const names = this.dc.map((c) => c.logical);
    const n = names.length;
    this.grid.style.gridTemplateColumns = `auto repeat(${n}, minmax(3.5em, 1fr))`;
    const cells: HTMLElement[] = [h("div", { className: "lab", text: "axis ↓ · moves →" }), ...names.map((c) => h("div", { className: "lab", text: c }))];
    for (const axis of names) {
      cells.push(h("div", { className: `lab${axis === this.stageInner ? " stage" : ""}`, text: axis, title: axis === this.stageInner ? "the stage's inner axis: couplings go in the pulse sequence, not here" : "" }));
      for (const other of names) {
        if (other === axis) {
          cells.push(h("div", { className: "cell diag", text: "1" }));
          continue;
        }
        const input = h("input", { type: "number", step: "any", name: `c_${axis}_${other}`, value: String(this.matrix[axis]?.[other] ?? 0), disabled: axis === this.stageInner, attrs: { "aria-label": `${other} per volt of ${axis}` } });
        input.addEventListener("change", () => {
          const v = Number(input.value);
          const row = (this.matrix[axis] ??= {});
          if (Number.isFinite(v) && v !== 0) row[other] = v;
          else delete row[other];
          if (!Object.keys(row).length) delete this.matrix[axis];
          this.save();
          this.publish();
        });
        cells.push(h("div", { className: "cell" }, input));
      }
    }
    this.grid.replaceChildren(...cells);
    const coupled = Object.keys(this.matrix).filter((a) => Object.keys(couplingsFor(this.matrix, a)).length);
    this.note.textContent = n ? (coupled.length ? `virtual gates: ${coupled.join(", ")}` : "identity: no axis moves another gate") : "no DC channels on this stand";
  }
}
