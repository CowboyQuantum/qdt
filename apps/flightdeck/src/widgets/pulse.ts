// The Pulse widget (ADR 0035, 0054, 0056): the per-shot pulse-sequence editor over the unchanged pure
// model in `control/sequence.ts` (one row per primitive, symbols bound to axes or numbers). It follows
// the one-step template for the Sweep widget's inner axis and sensor until edited (`sweep:axes`), and
// publishes its rows, bindings and errors (`pulse:sequence`) for the stage sweep the Sweep widget builds.
import type { ChannelMap } from "../schema/api";
import {
  buildBindings,
  buildSequence,
  fieldUnit,
  measuredResults,
  moveRow,
  newRow,
  OP_FIELDS,
  OP_KINDS,
  symbolInText,
  syncBindings,
  templateRows,
  unusedStageAxes,
  type BindingRow,
  type FieldName,
  type OpKind,
  type OpRow,
} from "../control/sequence";
import { h } from "../workspace/dom";
import type { Widget, WidgetContext } from "../workspace/widget";

export const pulseWidget: Widget = {
  id: "pulse",
  label: "Pulse",
  sub: "per-shot sequence for a stage sweep",
  single: true,
  mount(body, head, ctx) {
    const w = new PulseWidget(body, head, ctx);
    return () => w.unmount();
  },
};

class PulseWidget {
  private channels: ChannelMap[] = [];
  private rows: OpRow[] = [];
  private bindings: BindingRow[] = [];
  private rowsEdited = false;
  private axes: string[] = [];
  private inner = "";
  private sensor = "";
  private kind = "stage";
  private readonly ops: HTMLDivElement;
  private readonly symbols: HTMLDivElement;
  private readonly errors: HTMLUListElement;
  private readonly note: HTMLDivElement;
  private readonly offs: (() => void)[] = [];

  constructor(
    private readonly body: HTMLElement,
    private readonly head: HTMLElement,
    private readonly ctx: WidgetContext,
  ) {
    this.ops = h("div", { className: "ops" });
    this.symbols = h("div", { className: "symbols" });
    this.errors = h("ul", { className: "errors sequence-errors" });
    this.note = h("div", { className: "hint" });
    const add = h("select", { className: "add-op", attrs: { "aria-label": "Primitive to add" } }, ...OP_KINDS.map((k) => h("option", { value: k, text: k })));
    const addButton = h("button", { type: "button", text: "add op" });
    addButton.addEventListener("click", () => this.editRows([...this.rows, newRow(add.value as OpKind, this.channels, measuredResults(this.rows))]));
    const reset = h("button", { type: "button", text: "reset to template" });
    reset.addEventListener("click", () => {
      this.rowsEdited = false;
      this.followTemplate();
    });
    head.append(reset);
    body.append(
      h(
        "div",
        { className: "form-widget pulse" },
        this.note,
        this.ops,
        h("div", { className: "buttons" }, add, addButton),
        h("div", { className: "hint", text: "a value is a number (V, ns, Hz), a symbol name, or symbol ± offset (v_P2 + 0.002); bind each symbol below to an axis (swept) or a number" }),
        h("div", { className: "hint", text: "difference: result = a − b of two earlier measures, per shot (chopped readout); recorded beside them" }),
        h("div", { className: "hint", text: "a pulse level adds to the gate's DC level, holds until the next op on that line, and returns to 0 at the start of every shot" }),
        this.symbols,
        this.errors,
      ),
    );
    this.offs.push(
      ctx.bus.on("sweep:axes", ({ kind, axes, inner, sensor }) => {
        const changed = axes.join(",") !== this.axes.join(",") || inner !== this.inner || sensor !== this.sensor || kind !== this.kind;
        [this.axes, this.inner, this.sensor, this.kind] = [axes, inner, sensor, kind];
        this.note.textContent = kind === "stage" ? "" : `the ${kind} sweep has no stage; this sequence applies to a stage sweep`;
        if (changed) this.followTemplate();
      }),
      ctx.bus.on("layout:changed", () => this.publish()),
    );
    void ctx.api
      .stand()
      .then((s) => {
        this.channels = [...s.channels];
        this.followTemplate();
      })
      .catch((e: unknown) => ctx.bus.emit("say", { text: `server: ${String(e)}`, error: true }));
  }

  unmount(): void {
    for (const off of this.offs.splice(0)) off();
    this.body.replaceChildren();
    this.head.replaceChildren();
  }

  /** Until the user edits the sequence, it is the one-step template for the current inner axis and sensor. */
  private followTemplate(): void {
    if (!this.rowsEdited) {
      const inner = this.axes.at(-1) ?? "";
      this.rows = templateRows({ channel: this.inner, symbol: `v_${inner}`, sensor: this.sensor, stepNs: 500, measureNs: 2000, result: "I_sensor" });
      this.bindings = [];
    }
    this.renderOps();
  }

  private editRows(rows: OpRow[]): void {
    this.rows = rows;
    this.rowsEdited = true;
    this.renderOps();
  }

  private renderOps(): void {
    const byName = new Map(this.channels.map((c) => [c.logical, c]));
    this.ops.replaceChildren(
      ...this.rows.map((row, i) => {
        const opSelect = h("select", { className: "op", title: "primitive" }, ...OP_KINDS.map((k) => h("option", { value: k, text: k })));
        opSelect.value = row.op;
        opSelect.addEventListener("change", () => {
          // a new primitive starts prefilled; it keeps the channel when that channel suits it
          const next = newRow(opSelect.value as OpKind, this.channels, measuredResults(this.rows.slice(0, i)));
          const kept = row.fields.channel && byName.get(row.fields.channel);
          if (kept && "channel" in next.fields && (kept.quantity === "current") === (next.op === "measure")) next.fields.channel = kept.logical;
          this.editRows(this.rows.map((r, j) => (j === i ? next : r)));
        });
        const cells = (OP_FIELDS[row.op] as readonly FieldName[]).map((field) => {
          const value = row.fields[field] ?? "";
          let input: HTMLInputElement | HTMLSelectElement;
          if (field === "channel") {
            const wanted = row.op === "measure" ? "current" : "voltage";
            const options = this.channels.filter((c) => c.quantity === wanted);
            input = h("select", { name: field }, ...options.map((c) => h("option", { value: c.logical, text: c.logical })));
            if (value && !options.some((c) => c.logical === value)) input.append(h("option", { value, text: `${value}?` }));
            input.value = value;
          } else {
            const unit = field === "result" ? "" : fieldUnit(field, byName.get(row.fields.channel ?? ""));
            const label = `${field}${unit ? ` (${unit})` : ""}`;
            input = h("input", { name: field, value, placeholder: label, title: label });
          }
          input.addEventListener(field === "channel" ? "change" : "input", () => {
            row.fields[field] = input.value;
            this.rowsEdited = true;
            if (field === "channel") this.renderOps(); // units in the placeholders follow the channel
            else this.validate();
          });
          input.dataset.field = field;
          return h("label", { title: field }, h("span", { className: "field", text: field }), input);
        });
        const up = h("button", { type: "button", text: "↑", title: "earlier" });
        up.addEventListener("click", () => this.editRows(moveRow(this.rows, i, -1)));
        const down = h("button", { type: "button", text: "↓", title: "later" });
        down.addEventListener("click", () => this.editRows(moveRow(this.rows, i, 1)));
        const remove = h("button", { type: "button", text: "✕", title: "remove" });
        remove.addEventListener("click", () => this.editRows(this.rows.filter((_, j) => j !== i)));
        return h("div", { className: "op-row" }, h("span", { className: "index", text: String(i + 1) }), opSelect, ...cells, up, down, remove);
      }),
    );
    this.validate();
  }

  /** Rebuild the sequence, refresh the symbol bindings, list what the server would refuse, and publish. */
  private validate(): string[] {
    const built = buildSequence("sequence", this.rows, this.channels);
    const axes = this.axes;
    const before = this.bindings.map((b) => b.symbol).join(",");
    this.bindings = syncBindings(built.symbols.keys(), this.bindings, axes);
    // re-render the bindings only when the set of symbols changed, so typing in one keeps its focus
    if (this.bindings.map((b) => b.symbol).join(",") !== before || this.symbols.dataset.axes !== axes.join(",")) this.renderBindings(built.symbols, axes);
    const bound = buildBindings(this.bindings, axes);
    this.showBindingsOnCells(axes);
    const errors = [...built.errors, ...bound.errors];
    if (!bound.errors.length) errors.push(...unusedStageAxes(bound.bindings, axes.slice(-1)));
    this.errors.replaceChildren(...errors.map((e) => h("li", { text: e })));
    this.publish(errors);
    return errors;
  }

  private publish(errors?: string[]): void {
    const errs = errors ?? [...this.errors.querySelectorAll("li")].map((li) => li.textContent ?? "");
    this.ctx.bus.emit("pulse:sequence", { rows: this.rows, bindings: this.bindings, errors: errs });
  }

  /** Over each value cell holding a symbol, say what it takes: `level ← P2 (swept)`, `duration ← 300`. */
  private showBindingsOnCells(axes: string[]): void {
    const targets = new Map(this.bindings.map((b) => [b.symbol, b.target.trim()]));
    for (const input of this.ops.querySelectorAll<HTMLInputElement>("input[data-field]")) {
      const span = input.previousElementSibling as HTMLSpanElement | null;
      if (!span) continue;
      const field = input.dataset.field!;
      const t = targets.get(symbolInText(input.value) ?? "");
      span.textContent = t === undefined ? field : `${field} ← ${t === "" ? "?" : axes.includes(t) ? `${t} (swept)` : t}`;
    }
  }

  private renderBindings(units: Map<string, string>, axes: string[]): void {
    this.symbols.dataset.axes = axes.join(",");
    const listId = `binding-axes-${this.ctx.paneId}`;
    this.symbols.replaceChildren(
      h("datalist", { id: listId }, ...axes.map((a) => h("option", { value: a }))),
      ...this.bindings.map((b) => {
        const input = h("input", { name: `bind_${b.symbol}`, value: b.target, placeholder: "axis or number" });
        input.setAttribute("list", listId);
        input.addEventListener("input", () => {
          // by symbol: syncBindings hands out fresh rows, so `b` may be stale by now
          this.bindings = this.bindings.map((x) => (x.symbol === b.symbol ? { ...x, target: input.value } : x));
          this.validate();
        });
        const unit = units.get(b.symbol);
        return h("label", {}, `${b.symbol}${unit ? ` (${unit})` : ""} ←`, input);
      }),
    );
  }
}
