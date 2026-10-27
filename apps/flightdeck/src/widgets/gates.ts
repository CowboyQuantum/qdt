// The Virtual gates widget (ADR 0049, 0057, 0085): the coupling matrix a stepped axis carries. A row is a
// DC channel used as a sweep axis; its off-diagonal entries are the volts per volt by which other DC
// channels move with it (`SweepAxis.couplings`). The Sweep widget takes each stepped axis's row
// (`gates:couplings`). A stage axis cannot couple (it expresses its couplings in the pulse sequence,
// Affine); the widget says so for the inner axis of a stage sweep. The matrix is the stand's (ADR 0075):
// read from `GET /stand/state`; an edit is a draft until it is saved with a reason (`POST /stand/state`),
// and sweeps take the saved matrix, never the draft.
import { ApiError } from "../api/client";
import type { ChannelMap } from "../schema/api";
import { standChannels } from "../control/sweeps";
import { h } from "../workspace/dom";
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

/** Whether two matrices hold the same couplings (zeros and the diagonal implicit). Pure. */
export function sameMatrix(a: CouplingMatrix, b: CouplingMatrix): boolean {
  const rows = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const r of rows) {
    const x = couplingsFor(a, r);
    const y = couplingsFor(b, r);
    const keys = new Set([...Object.keys(x), ...Object.keys(y)]);
    for (const k of keys) if (x[k] !== y[k]) return false;
  }
  return true;
}

const POLL_MS = 5000;

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
  /** The stand's matrix (the saved one: what sweeps take) and the one being edited. */
  private saved: CouplingMatrix = {};
  private draft: CouplingMatrix = {};
  private version = 0;
  private stageInner = "";
  private offer: { node: string; gates: [string, string]; c_21: number; c_12: number } | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private readonly offerBox: HTMLDivElement;
  private readonly grid: HTMLDivElement;
  private readonly note: HTMLDivElement;
  private readonly reason: HTMLInputElement;
  private readonly saveButton: HTMLButtonElement;
  private readonly offs: (() => void)[] = [];

  constructor(
    private readonly body: HTMLElement,
    private readonly head: HTMLElement,
    private readonly ctx: WidgetContext,
  ) {
    this.grid = h("div", { className: "grid" });
    this.note = h("div", { className: "foot hint", attrs: { "data-gates-note": "" } });
    this.offerBox = h("div", { className: "offer" });
    const reset = h("button", { type: "button", text: "identity", title: "No couplings: every axis moves its own gate only (a draft until saved)", attrs: { "data-reset": "" } });
    reset.addEventListener("click", () => {
      this.draft = {};
      this.render();
    });
    const revert = h("button", { type: "button", text: "revert", title: "Back to the stand's matrix", attrs: { "data-revert": "" } });
    revert.addEventListener("click", () => {
      this.draft = clone(this.saved);
      this.render();
    });
    head.append(reset, revert);
    this.reason = h("input", { type: "text", name: "gates_reason", placeholder: "why (kept with the stand state)", attrs: { "aria-label": "Why the couplings change" } });
    this.saveButton = h("button", { type: "button", text: "save to the stand", attrs: { "data-save": "" } });
    this.saveButton.addEventListener("click", () => void this.save());
    body.append(
      h(
        "div",
        { className: "matrix" },
        h("div", { className: "hint", text: "row: the gate an axis steps; columns: how much each other gate moves with it (V/V). A stepped axis takes its row as SweepAxis.couplings (ADR 0049); sweeps use the matrix saved to the stand." }),
        this.grid,
        h("div", { className: "save" }, this.reason, this.saveButton),
        this.offerBox,
        this.note,
      ),
    );
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
        return this.load();
      })
      .catch((e: unknown) => ctx.bus.emit("say", { text: `server: ${describe(e)}`, error: true }));
    // another desk may change the stand's matrix: follow it while nothing is being edited here
    this.timer = setInterval(() => {
      if (sameMatrix(this.draft, this.saved)) void this.load(true);
    }, POLL_MS);
  }

  unmount(): void {
    if (this.timer) clearInterval(this.timer);
    for (const off of this.offs.splice(0)) off();
    this.body.replaceChildren();
    this.head.replaceChildren();
    this.ctx.bus.emit("gates:couplings", { matrix: {} });
  }

  private names(): string[] {
    return this.dc.map((c) => c.logical);
  }

  /** Read the stand's matrix; the draft follows it when it holds no edit of its own. */
  private async load(quiet = false): Promise<void> {
    try {
      const state = await this.ctx.api.standState();
      const saved = parseMatrix(JSON.stringify(state.couplings ?? {}), this.names());
      const editing = !sameMatrix(this.draft, this.saved);
      const changed = !sameMatrix(saved, this.saved) || state.version !== this.version;
      this.saved = saved;
      this.version = state.version;
      if (!editing) this.draft = clone(saved);
      if (changed || !quiet) {
        this.render();
        this.publish();
      }
    } catch (e) {
      if (!quiet) this.ctx.bus.emit("say", { text: `virtual gates: ${describe(e)}`, error: true });
    }
  }

  private async save(): Promise<void> {
    const reason = this.reason.value.trim();
    if (!reason) {
      this.note.textContent = "say why the couplings change: the stand state keeps the reason";
      return;
    }
    try {
      const state = await this.ctx.api.changeStandState({ couplings: this.draft, reason });
      this.saved = parseMatrix(JSON.stringify(state.couplings ?? {}), this.names());
      this.version = state.version;
      this.draft = clone(this.saved);
      this.reason.value = "";
      this.render();
      this.publish();
      this.ctx.bus.emit("say", { text: `virtual gates saved to the stand (stand state v${state.version})`, error: false });
    } catch (e) {
      this.note.textContent = describe(e);
    }
  }

  /** The Sweep widget takes the stand's matrix, never an unsaved draft. */
  private publish(): void {
    this.ctx.bus.emit("gates:couplings", { matrix: this.saved });
  }

  /** "apply c_21, c_12 from node X": row g1 ← g2 = c_21 (moving virtual gate 1 moves g2 by c_21 V/V),
   * row g2 ← g1 = c_12; into the draft, with the reason filled in, until it is saved. */
  private renderOffer(): void {
    const o = this.offer;
    if (!o) return this.offerBox.replaceChildren();
    const [g1, g2] = o.gates;
    const apply = h("button", { type: "button", text: `apply from ${o.node}: ${g1}→${g2} = ${o.c_21.toPrecision(3)}, ${g2}→${g1} = ${o.c_12.toPrecision(3)}`, attrs: { "data-apply": "" } });
    apply.addEventListener("click", () => {
      (this.draft[g1] ??= {})[g2] = o.c_21;
      (this.draft[g2] ??= {})[g1] = o.c_12;
      if (!this.reason.value.trim()) this.reason.value = `couplings of ${g1} and ${g2} from tune-up node ${o.node}`;
      this.render();
      this.ctx.bus.emit("say", { text: `virtual gates: ${g1}/${g2} couplings from ${o.node} in the draft; save to use them`, error: false });
    });
    this.offerBox.replaceChildren(apply);
  }

  private render(): void {
    const names = this.names();
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
        const input = h("input", { type: "number", step: "any", name: `c_${axis}_${other}`, value: String(this.draft[axis]?.[other] ?? 0), disabled: axis === this.stageInner, attrs: { "aria-label": `${other} per volt of ${axis}` } });
        input.addEventListener("change", () => {
          const v = Number(input.value);
          const row = (this.draft[axis] ??= {});
          if (Number.isFinite(v) && v !== 0) row[other] = v;
          else delete row[other];
          if (!Object.keys(row).length) delete this.draft[axis];
          this.renderNote();
        });
        cells.push(h("div", { className: "cell" }, input));
      }
    }
    this.grid.replaceChildren(...cells);
    this.renderNote();
  }

  private renderNote(): void {
    const dirty = !sameMatrix(this.draft, this.saved);
    this.saveButton.disabled = !dirty;
    const coupled = Object.keys(this.saved).filter((a) => Object.keys(couplingsFor(this.saved, a)).length);
    const now = this.names().length ? (coupled.length ? `virtual gates on the stand: ${coupled.join(", ")}` : "identity on the stand: no axis moves another gate") : "no DC channels on this stand";
    this.note.textContent = `${now}${this.version ? ` (stand state v${this.version})` : ""}${dirty ? " · unsaved changes: sweeps use the stand's matrix until you save" : ""}`;
  }
}

function clone(m: CouplingMatrix): CouplingMatrix {
  return Object.fromEntries(Object.entries(m).map(([k, row]) => [k, { ...row }]));
}

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.status} ${e.detail}`;
  return e instanceof Error ? e.message : String(e);
}
