// The control panel (Step 4b, ADR 0032): craft a sweep, run it, watch its Run, browse records, run a
// curated analysis, put overlays and outputs on the stream. Talks to qdt-server through ApiClient only.
// The view itself (what is drawn) stays a function of the Dataset stream (rule 8).
import { ApiClient, ApiError } from "../api/client";
import type { AnalysisResult, MeasurementRecord, MethodSpec, Run, SweepDefinition } from "../schema/api";
import { check, defaults, overrides, parse, type ParamValues } from "./methods";
import { dcSweep, stageSweep, standChannels, type AxisForm, type StandChannels } from "./sweeps";

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
    };
    this.build();
  }

  async init(): Promise<void> {
    try {
      const [stand, methods] = await Promise.all([this.api.stand(), this.api.methods()]);
      this.stand = standChannels(stand);
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
      h("div", { className: "axis head" }, "axis", "channel", "start", "stop", "num"),
      h("div", {}, "outer", axisRow("outer", { channel: "", start: 0.03, stop: 0.18, num: 48 })),
      h("div", {}, "inner", axisRow("inner", { channel: "", start: 0.03, stop: 0.18, num: 48 })),
      field("inner axis name", h("input", { name: "inner_name", placeholder: "defaults to the channel" })),
      field("sensor", h("select", { name: "sensor" })),
      field("shots", num("shots", 1, "1")),
      field("options", h("input", { name: "options", value: '{"seed": 1, "noise": true}' })),
      h("button", { type: "submit", text: "run" }),
    );
    f.addEventListener("submit", (e) => {
      e.preventDefault();
      void this.submit();
    });
    (f.elements.namedItem("kind") as HTMLSelectElement).addEventListener("change", () => this.fillSelects());

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
      const had = s.value;
      s.replaceChildren(...items.map((c) => h("option", { value: c.logical, text: c.logical })));
      s.value = items.some((c) => c.logical === had) ? had : (preferred.find((p) => items.some((c) => c.logical === p)) ?? items[0]?.logical ?? "");
    };
    fill("outer_channel", this.stand.dc, ["P1", "SG"]);
    fill("inner_channel", kind === "stage" ? this.stand.pulse : this.stand.dc, ["P2_pulse", "bias"]);
    fill("sensor", this.stand.sensors, ["sensor"]);
    this.els.method.replaceChildren(...this.methods.map((m) => h("option", { value: m.name, text: m.title })));
    this.fillParams();
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
    if (v("kind") === "stage") {
      const inner = this.stand.pulse.find((c) => c.logical === v("inner_channel"));
      if (!inner) throw new Error("a stage sweep needs a pulse channel for its inner axis");
      return {
        definition: stageSweep({
          name: v("name"),
          outer: axis("outer"),
          inner: axis("inner", innerName),
          sensor,
          instrument: inner.instrument,
          shots: Number(v("shots")),
          stepNs: 500,
          measureNs: 2000,
          result: "I_sensor",
        }),
        options,
      };
    }
    return {
      definition: dcSweep({ name: v("name"), outer: axis("outer"), inner: axis("inner", innerName), sensor, result: "I_sensor" }),
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
