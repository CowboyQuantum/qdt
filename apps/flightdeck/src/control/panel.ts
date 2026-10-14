// The control panel (Step 4b, ADR 0032): craft a sweep, run it, watch its Run, browse records, run a
// curated analysis, put overlays and outputs on the stream. Talks to qdt-server through ApiClient only.
// The view itself (what is drawn) stays a function of the Dataset stream (rule 8).
import { ApiClient, ApiError } from "../api/client";
import type { AnalysisResult, ChannelMap, MeasurementRecord, MethodSpec, Run, SweepDefinition } from "../schema/api";
import { check, defaults, overrides, parse, type ParamValues } from "./methods";
import {
  buildBindings,
  buildSequence,
  fieldUnit,
  moveRow,
  newRow,
  OP_FIELDS,
  OP_KINDS,
  syncBindings,
  templateRows,
  type BindingRow,
  type FieldName,
  type OpKind,
  type OpRow,
} from "./sequence";
import { axisName, dcSweep, stageSweep, standChannels, type AxisForm, type StandChannels } from "./sweeps";

const h = <K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> & { text?: string } = {}, ...children: (Node | string)[]) => {
  const el = document.createElement(tag);
  const { text, ...rest } = props;
  Object.assign(el, rest);
  if (text !== undefined) el.textContent = text;
  el.append(...children);
  return el;
};

const short = (id: string) => id.slice(0, 8);
const TERMINAL = new Set(["completed", "aborted", "failed"]);

export interface ControlHost {
  /** Report a message (an error or a status) to the user. */
  say(message: string, isError?: boolean): void;
}

export class ControlPanel {
  private stand: StandChannels = { dc: [], pulse: [], sensors: [] };
  private channels: ChannelMap[] = [];
  /** The stage's pulse sequence as the editor holds it; follows the template until edited. */
  private rows: OpRow[] = [];
  private bindings: BindingRow[] = [];
  private rowsEdited = false;
  private methods: MethodSpec[] = [];
  private records: MeasurementRecord[] = [];
  private selectedRecord: MeasurementRecord | null = null;
  private lastResult: AnalysisResult | null = null;
  private readonly runs = new Map<string, Run>();
  private readonly els: {
    form: HTMLFormElement;
    runsList: HTMLUListElement;
    recordsList: HTMLUListElement;
    method: HTMLSelectElement;
    params: HTMLDivElement;
    analysisTarget: HTMLSpanElement;
    estimates: HTMLPreElement;
    sequence: HTMLFieldSetElement;
    ops: HTMLDivElement;
    symbols: HTMLDivElement;
    sequenceErrors: HTMLUListElement;
  };

  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly host: ControlHost,
  ) {
    this.els = {
      form: h("form", { id: "sweep" }),
      runsList: h("ul", { id: "runs" }),
      recordsList: h("ul", { id: "records" }),
      method: h("select", { id: "method" }),
      params: h("div", { id: "params" }),
      analysisTarget: h("span", { id: "analysis-target", text: "no record selected" }),
      estimates: h("pre", { id: "estimates" }),
      sequence: h("fieldset", { id: "sequence" }),
      ops: h("div", { id: "ops" }),
      symbols: h("div", { id: "symbols" }),
      sequenceErrors: h("ul", { id: "sequence-errors" }),
    };
    this.build();
  }

  async init(): Promise<void> {
    try {
      const [stand, methods] = await Promise.all([this.api.stand(), this.api.methods()]);
      this.stand = standChannels(stand);
      this.channels = [...stand.channels];
      this.methods = methods;
      this.fillSelects();
      await this.refreshRecords();
    } catch (e) {
      this.host.say(`server: ${describe(e)}`, true);
    }
  }

  // --- layout --------------------------------------------------------------------------------------

  private build(): void {
    const f = this.els.form;
    const field = (label: string, input: HTMLElement) => h("label", {}, label, input);
    const num = (name: string, value: number, step = "any") => h("input", { name, type: "number", value: String(value), step });
    const axisRow = (prefix: string, a: AxisForm) =>
      h(
        "div",
        { className: "axis" },
        h("select", { name: `${prefix}_channel` }),
        num(`${prefix}_start`, a.start),
        num(`${prefix}_stop`, a.stop),
        num(`${prefix}_num`, a.num, "1"),
      );
    f.append(
      h("h3", { text: "Sweep" }),
      field("kind", h("select", { name: "kind" }, h("option", { value: "stage", text: "stage: inner axis pulsed" }), h("option", { value: "dc", text: "DC: both axes stepped, sensed" }))),
      field("name", h("input", { name: "name", value: "stability" })),
      h("div", { className: "axis head" }, ...["channel", "start", "stop", "num"].map((t) => h("span", { text: t }))),
      h("div", {}, "outer", axisRow("outer", { channel: "", start: 0.03, stop: 0.18, num: 48 })),
      h("div", {}, "inner", axisRow("inner", { channel: "", start: 0.03, stop: 0.18, num: 48 })),
      field("inner axis name", h("input", { name: "inner_name", placeholder: "defaults to the channel" })),
      field("sensor", h("select", { name: "sensor" })),
      field("shots", num("shots", 1, "1")),
      this.buildSequenceEditor(),
      field("options", h("input", { name: "options", value: '{"seed": 1, "noise": true}' })),
      h("button", { type: "submit", text: "run" }),
    );
    f.addEventListener("submit", (e) => {
      e.preventDefault();
      void this.submit();
    });
    (f.elements.namedItem("kind") as HTMLSelectElement).addEventListener("change", () => this.fillSelects());
    // the template follows the inner axis and the sensor until the sequence is edited; axis names feed the bindings
    for (const name of ["inner_channel", "inner_name", "sensor", "outer_channel"]) {
      (f.elements.namedItem(name) as HTMLElement).addEventListener("change", () => this.followTemplate());
    }

    const analysis = h(
      "div",
      { id: "analysis" },
      h("h3", { text: "Analysis" }),
      h("div", {}, "record: ", this.els.analysisTarget),
      h("label", {}, "method ", this.els.method),
      this.els.params,
      h("div", { className: "buttons" },
        h("button", { type: "button", text: "run analysis", onclick: () => void this.analyse() }),
        h("button", { type: "button", text: "show overlays", onclick: () => void this.showOverlays() }),
        h("button", { type: "button", text: "show output", onclick: () => void this.showOutput() }),
      ),
      this.els.estimates,
    );
    this.els.method.addEventListener("change", () => this.fillParams());

    this.root.append(
      f,
      h("h3", { text: "Runs" }),
      this.els.runsList,
      h("h3", {}, "Records ", h("button", { type: "button", text: "refresh", onclick: () => void this.refreshRecords() })),
      this.els.recordsList,
      analysis,
    );
  }

  private fillSelects(): void {
    const f = this.els.form;
    const kind = (f.elements.namedItem("kind") as HTMLSelectElement).value;
    const fill = (name: string, items: { logical: string }[], preferred: string[]) => {
      const s = f.elements.namedItem(name) as HTMLSelectElement;
      // keep the user's choice on a refill (it may be "", e.g. no outer axis); the first fill takes the preferred
      const had = s.dataset.filled ? s.value : null;
      s.replaceChildren(...items.map((c) => h("option", { value: c.logical, text: c.logical })));
      s.value = items.some((c) => c.logical === had) ? had! : (preferred.find((p) => items.some((c) => c.logical === p)) ?? items[0]?.logical ?? "");
      if (items.length) s.dataset.filled = "1";
    };
    fill("outer_channel", [...this.stand.dc, { logical: "" }], ["P1", "SG"]);
    const none = (f.elements.namedItem("outer_channel") as HTMLSelectElement).querySelector('option[value=""]');
    if (none) none.textContent = "— none (1-D)";
    fill("inner_channel", kind === "stage" ? this.stand.pulse : this.stand.dc, ["P2_pulse", "bias"]);
    fill("sensor", this.stand.sensors, ["sensor"]);
    this.els.sequence.hidden = kind !== "stage";
    this.followTemplate();
    this.els.method.replaceChildren(...this.methods.map((m) => h("option", { value: m.name, text: m.title })));
    this.fillParams();
  }

  // --- pulse-sequence editor (ADR 0035: a form over PulseSequence, one row per primitive) --------------

  private buildSequenceEditor(): HTMLFieldSetElement {
    const add = h("select", { id: "add-op" }, ...OP_KINDS.map((k) => h("option", { value: k, text: k })));
    const reset = () => {
      this.rowsEdited = false;
      this.followTemplate();
    };
    this.els.sequence.append(
      h("legend", { text: "pulse sequence (per shot)" }),
      this.els.ops,
      h(
        "div",
        { className: "buttons" },
        add,
        h("button", { type: "button", text: "add op", onclick: () => this.editRows([...this.rows, newRow(add.value as OpKind, this.channels)]) }),
        h("button", { type: "button", text: "reset to template", onclick: reset }),
      ),
      h("div", { className: "hint", text: "values: a number or a symbol name; bind each symbol to an axis or a number" }),
      this.els.symbols,
      this.els.sequenceErrors,
    );
    return this.els.sequence;
  }

  private value(name: string): string {
    return (this.els.form.elements.namedItem(name) as HTMLInputElement | HTMLSelectElement).value;
  }

  /** Axis names as the sweep will have them, outer to inner: what a symbol may be bound to. */
  private axisNames(): string[] {
    const inner = axisName({ channel: this.value("inner_channel"), start: 0, stop: 0, num: 1, name: this.value("inner_name").trim() || undefined });
    const outer = this.value("outer_channel");
    return outer ? [axisName({ channel: outer, start: 0, stop: 0, num: 1 }), inner] : [inner];
  }

  /** Until the user edits the sequence, it is the one-step template for the current inner axis and sensor. */
  private followTemplate(): void {
    if (!this.rowsEdited) {
      const inner = this.axisNames().at(-1)!;
      this.rows = templateRows({ channel: this.value("inner_channel"), symbol: `v_${inner}`, sensor: this.value("sensor"), stepNs: 500, measureNs: 2000, result: "I_sensor" });
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
    this.els.ops.replaceChildren(
      ...this.rows.map((row, i) => {
        const opSelect = h("select", { className: "op", title: "primitive" }, ...OP_KINDS.map((k) => h("option", { value: k, text: k })));
        opSelect.value = row.op;
        opSelect.addEventListener("change", () => {
          // a new primitive starts prefilled; it keeps the channel when that channel suits it
          const next = newRow(opSelect.value as OpKind, this.channels);
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
            else this.validateSequence();
          });
          return h("label", { title: field }, h("span", { text: field }), input);
        });
        return h(
          "div",
          { className: "op-row" },
          h("span", { className: "index", text: String(i + 1) }),
          opSelect,
          ...cells,
          h("button", { type: "button", text: "↑", title: "earlier", onclick: () => this.editRows(moveRow(this.rows, i, -1)) }),
          h("button", { type: "button", text: "↓", title: "later", onclick: () => this.editRows(moveRow(this.rows, i, 1)) }),
          h("button", { type: "button", text: "✕", title: "remove", onclick: () => this.editRows(this.rows.filter((_, j) => j !== i)) }),
        );
      }),
    );
    this.validateSequence();
  }

  /** Rebuild the sequence, refresh the symbol bindings, and list what the server would refuse. */
  private validateSequence(): string[] {
    const built = buildSequence("sequence", this.rows, this.channels);
    const axes = this.axisNames();
    const before = this.bindings.map((b) => b.symbol).join(",");
    this.bindings = syncBindings(built.symbols.keys(), this.bindings, axes);
    // re-render the bindings only when the set of symbols changed, so typing in one keeps its focus
    if (this.bindings.map((b) => b.symbol).join(",") !== before || this.els.symbols.dataset.axes !== axes.join(",")) {
      this.renderBindings(built.symbols, axes);
    }
    const errors = [...built.errors, ...buildBindings(this.bindings, axes).errors];
    this.els.sequenceErrors.replaceChildren(...errors.map((e) => h("li", { text: e })));
    return errors;
  }

  private renderBindings(units: Map<string, string>, axes: string[]): void {
    this.els.symbols.dataset.axes = axes.join(",");
    this.els.symbols.replaceChildren(
      h("datalist", { id: "binding-axes" }, ...axes.map((a) => h("option", { value: a }))),
      ...this.bindings.map((b) => {
        const input = h("input", { name: `bind_${b.symbol}`, value: b.target, placeholder: "axis or number" });
        input.setAttribute("list", "binding-axes");
        input.addEventListener("input", () => {
          // by symbol: syncBindings hands out fresh rows, so `b` may be stale by now
          this.bindings = this.bindings.map((x) => (x.symbol === b.symbol ? { ...x, target: input.value } : x));
          this.validateSequence();
        });
        const unit = units.get(b.symbol);
        return h("label", {}, `${b.symbol}${unit ? ` (${unit})` : ""} ←`, input);
      }),
    );
  }

  private fillParams(): void {
    const spec = this.methods.find((m) => m.name === this.els.method.value);
    this.els.params.replaceChildren();
    if (!spec) return;
    for (const p of spec.parameters ?? []) {
      const input =
        p.kind === "bool"
          ? h("input", { name: p.name, type: "checkbox", checked: Boolean(p.default) })
          : h("input", { name: p.name, value: String(p.default), title: p.description });
      this.els.params.append(h("label", { title: p.description }, `${p.name}${p.unit ? ` (${p.unit})` : ""} `, input));
    }
  }

  // --- sweeps and runs -----------------------------------------------------------------------------

  private readForm(): { definition: SweepDefinition; options: Record<string, string | number | boolean> } {
    const f = this.els.form;
    const v = (name: string) => (f.elements.namedItem(name) as HTMLInputElement | HTMLSelectElement).value;
    const axis = (prefix: string, name?: string): AxisForm => ({
      channel: v(`${prefix}_channel`),
      start: Number(v(`${prefix}_start`)),
      stop: Number(v(`${prefix}_stop`)),
      num: Number(v(`${prefix}_num`)),
      ...(name ? { name } : {}),
    });
    const options = JSON.parse(v("options") || "{}") as Record<string, string | number | boolean>;
    const sensor = v("sensor");
    const innerName = v("inner_name").trim() || undefined;
    const outer = v("outer_channel") ? axis("outer") : null;
    if (v("kind") === "stage") {
      const inner = this.stand.pulse.find((c) => c.logical === v("inner_channel"));
      if (!inner) throw new Error("a stage sweep needs a pulse channel for its inner axis");
      this.validateSequence(); // bring the bindings up to date with the axis names
      return {
        definition: stageSweep({
          name: v("name"),
          outer,
          inner: axis("inner", innerName),
          sensor,
          instrument: inner.instrument,
          shots: Number(v("shots")),
          stepNs: 500,
          measureNs: 2000,
          result: "I_sensor",
          sequence: { rows: this.rows, bindings: this.bindings, channels: this.channels },
        }),
        options,
      };
    }
    return {
      definition: dcSweep({ name: v("name"), outer, inner: axis("inner", innerName), sensor, result: "I_sensor" }),
      options,
    };
  }

  private async submit(): Promise<void> {
    try {
      const { definition, options } = this.readForm();
      const run = await this.api.startRun({ definition, options });
      this.runs.set(run.run_id, run);
      this.renderRuns();
      this.host.say(`run ${short(run.run_id)} queued`);
      void this.follow(run.run_id);
    } catch (e) {
      this.host.say(describe(e), true);
    }
  }

  private async follow(runId: string): Promise<void> {
    while (true) {
      await new Promise((r) => setTimeout(r, 1000));
      let run: Run;
      try {
        run = await this.api.run(runId);
      } catch (e) {
        this.host.say(describe(e), true);
        return;
      }
      this.runs.set(runId, run);
      this.renderRuns();
      if (TERMINAL.has(run.state)) {
        this.host.say(`run ${short(runId)} ${run.state}${run.error ? `: ${run.error}` : ""}`, run.state === "failed");
        await this.refreshRecords();
        return;
      }
    }
  }

  private renderRuns(): void {
    this.els.runsList.replaceChildren(
      ...[...this.runs.values()].reverse().map((r) =>
        h("li", { text: `${short(r.run_id)} ${r.definition_name} · ${r.state}${r.record_id ? ` → record ${short(r.record_id)}` : ""}` }),
      ),
    );
  }

  // --- records and analysis ------------------------------------------------------------------------

  async refreshRecords(): Promise<void> {
    try {
      this.records = await this.api.records();
    } catch (e) {
      this.host.say(describe(e), true);
      return;
    }
    this.els.recordsList.replaceChildren(
      ...[...this.records].reverse().map((r) =>
        h(
          "li",
          {},
          `${short(r.record_id)} ${r.definition_name} · ${r.started_at.slice(0, 19).replace("T", " ")} · ${r.outcome}`,
          h("button", { type: "button", text: "show", onclick: () => void this.replay({ record_id: r.record_id }) }),
          h("button", { type: "button", text: "analyse", onclick: () => this.select(r) }),
        ),
      ),
    );
  }

  private select(record: MeasurementRecord): void {
    this.selectedRecord = record;
    this.lastResult = null;
    this.els.analysisTarget.textContent = `${short(record.record_id)} ${record.definition_name}`;
    this.els.estimates.textContent = "";
  }

  private readParams(spec: MethodSpec): ParamValues {
    const values: ParamValues = {};
    for (const p of spec.parameters ?? []) {
      const input = this.els.params.querySelector<HTMLInputElement>(`input[name="${p.name}"]`)!;
      values[p.name] = parse(p, p.kind === "bool" ? input.checked : input.value);
    }
    const errors = check(spec, values);
    if (errors.length) throw new Error(errors.join("; "));
    return values;
  }

  private async analyse(): Promise<void> {
    const record = this.selectedRecord;
    const spec = this.methods.find((m) => m.name === this.els.method.value);
    if (!record || !spec) return this.host.say("select a record and a method first", true);
    try {
      const parameters = overrides(spec, this.readParams(spec));
      this.host.say(`running ${spec.title} on ${short(record.record_id)}…`);
      const result = await this.api.analyse(record.record_id, { method: spec.name, parameters });
      this.lastResult = result;
      const lines = [`${result.status}${result.message ? `: ${result.message}` : ""} · ${(result.annotations ?? []).length} overlays`];
      for (const e of result.estimates ?? []) lines.push(`${e.name.padEnd(18)} ${e.value.toPrecision(5)} ${e.unit}`);
      this.els.estimates.textContent = lines.join("\n");
      this.host.say(`analysis ${short(result.result_id)} ${result.status}`, result.status === "failed");
    } catch (e) {
      this.host.say(describe(e), true);
    }
  }

  private async showOverlays(): Promise<void> {
    if (!this.selectedRecord) return this.host.say("select a record first", true);
    await this.replay({ record_id: this.selectedRecord.record_id });
  }

  private async showOutput(): Promise<void> {
    if (!this.lastResult?.output) return this.host.say("run an analysis that produced an output first", true);
    await this.replay({ result_id: this.lastResult.result_id });
  }

  private async replay(request: { record_id?: string; result_id?: string }): Promise<void> {
    try {
      await this.api.replay(request);
      this.host.say(`replaying ${short(request.record_id ?? request.result_id ?? "")} on the stream`);
    } catch (e) {
      this.host.say(describe(e), true);
    }
  }
}

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.status} ${e.detail}`;
  return e instanceof Error ? e.message : String(e);
}
