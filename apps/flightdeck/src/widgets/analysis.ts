// The Analysis widget (ADR 0031, 0036, 0058): run a curated method on a stored record and put what it
// produced on the stream. The record comes from History's "analyse" action (`analysis:record`) or the
// widget's own picker over GET /records; the method from GET /methods, its parameters as a form over the
// pure `control/methods.ts` (defaults, parse, check, overrides). Estimates are shown here; overlays and
// the output Dataset go to the stream through the replay path, where every plot pane sees them.
import { ApiError } from "../api/client";
import type { AnalysisResult, MeasurementRecord, MethodSpec } from "../schema/api";
import { check, overrides, parse, type ParamValues } from "../control/methods";
import { h } from "../workspace/dom";
import type { Widget, WidgetContext } from "../workspace/widget";

const short = (id: string) => id.slice(0, 8);

/** The lines the widget shows for a result: status and overlay count, then one per estimate. Pure. */
export function resultLines(result: AnalysisResult): string[] {
  const lines = [`${result.status}${result.message ? `: ${result.message}` : ""} · ${(result.annotations ?? []).length} overlays`];
  for (const e of result.estimates ?? []) lines.push(`${e.name.padEnd(18)} ${e.value.toPrecision(5)} ${e.unit}`);
  return lines;
}

export const analysisWidget: Widget = {
  id: "analysis",
  label: "Analysis",
  sub: "a curated method on a stored record; overlays to the stream",
  single: true,
  mount(body, head, ctx) {
    const w = new AnalysisWidget(body, head, ctx);
    return () => w.unmount();
  },
};

class AnalysisWidget {
  private methods: MethodSpec[] = [];
  private records: MeasurementRecord[] = [];
  private lastResult: AnalysisResult | null = null;
  private readonly record: HTMLSelectElement;
  private readonly method: HTMLSelectElement;
  private readonly params: HTMLDivElement;
  private readonly estimates: HTMLPreElement;
  private readonly offs: (() => void)[] = [];

  constructor(
    private readonly body: HTMLElement,
    private readonly head: HTMLElement,
    private readonly ctx: WidgetContext,
  ) {
    this.record = h("select", { name: "record", attrs: { "aria-label": "Record to analyse" } });
    this.method = h("select", { name: "method", attrs: { "aria-label": "Method" } });
    this.params = h("div", { className: "params" });
    this.estimates = h("pre", { className: "estimates" });
    const run = h("button", { type: "button", text: "run analysis", attrs: { "data-analyse": "" } });
    run.addEventListener("click", () => void this.analyse());
    const overlaysButton = h("button", { type: "button", text: "show overlays", title: "Replay the record with its stored overlays on the stream", attrs: { "data-overlays": "" } });
    overlaysButton.addEventListener("click", () => void this.showOverlays());
    const outputButton = h("button", { type: "button", text: "show output", title: "Put the last result's output Dataset on the stream", attrs: { "data-output": "" } });
    outputButton.addEventListener("click", () => void this.showOutput());
    head.append(run);
    body.append(
      h(
        "div",
        { className: "form-widget analysis" },
        h("label", {}, "record ", this.record),
        h("label", {}, "method ", this.method),
        this.params,
        h("div", { className: "buttons" }, run.cloneNode(true) as HTMLElement, overlaysButton, outputButton),
        this.estimates,
      ),
    );
    // the head's Run and the body's are the same action; the clone in the body needs its own listener
    (body.querySelector("[data-analyse]") as HTMLButtonElement).addEventListener("click", () => void this.analyse());
    this.method.addEventListener("change", () => this.fillParams());
    this.record.addEventListener("change", () => {
      this.lastResult = null;
      this.estimates.textContent = "";
    });
    this.offs.push(
      ctx.bus.on("analysis:record", ({ recordId }) => this.select(recordId)),
      ctx.bus.on("records:changed", () => void this.refreshRecords()),
      ctx.bus.on("stream:dataset", ({ store }) => {
        const off = store.onUpdate((u) => {
          if (!u.final) return;
          off();
          for (const ms of [500, 3000]) setTimeout(() => void this.refreshRecords(), ms);
        });
      }),
    );
    void this.init();
  }

  unmount(): void {
    for (const off of this.offs.splice(0)) off();
    this.body.replaceChildren();
    this.head.replaceChildren();
  }

  private say(text: string, error = false): void {
    this.ctx.bus.emit("say", { text, error });
  }

  private async init(): Promise<void> {
    try {
      this.methods = await this.ctx.api.methods();
      this.method.replaceChildren(...this.methods.map((m) => new Option(m.title, m.name)));
      this.fillParams();
      await this.refreshRecords();
    } catch (e) {
      this.say(`server: ${describe(e)}`, true);
    }
  }

  private async refreshRecords(): Promise<void> {
    try {
      this.records = await this.ctx.api.records();
    } catch (e) {
      this.say(describe(e), true);
      return;
    }
    const had = this.record.value;
    this.record.replaceChildren(
      new Option("— pick a record (or press analyse in History)", ""),
      ...[...this.records].reverse().map((r) => new Option(`${short(r.record_id)} ${r.definition_name} · ${r.started_at.slice(0, 19).replace("T", " ")} · ${r.outcome}`, r.record_id)),
    );
    this.record.value = this.records.some((r) => r.record_id === had) ? had : "";
  }

  /** History's "analyse": the record is selected here (fetched if the list is behind). */
  private select(recordId: string): void {
    if (!this.records.some((r) => r.record_id === recordId)) {
      void this.refreshRecords().then(() => this.select(recordId));
      return;
    }
    this.record.value = recordId;
    this.lastResult = null;
    this.estimates.textContent = "";
    this.say(`analysis: record ${short(recordId)} selected`);
  }

  private fillParams(): void {
    const spec = this.methods.find((m) => m.name === this.method.value);
    this.params.replaceChildren();
    if (!spec) return;
    for (const p of spec.parameters ?? []) {
      const input =
        p.kind === "bool"
          ? h("input", { name: p.name, type: "checkbox", checked: Boolean(p.default) })
          : h("input", { name: p.name, value: String(p.default), title: p.description });
      this.params.append(h("label", { title: p.description }, `${p.name}${p.unit ? ` (${p.unit})` : ""} `, input));
    }
  }

  private readParams(spec: MethodSpec): ParamValues {
    const values: ParamValues = {};
    for (const p of spec.parameters ?? []) {
      const input = this.params.querySelector<HTMLInputElement>(`input[name="${p.name}"]`)!;
      values[p.name] = parse(p, p.kind === "bool" ? input.checked : input.value);
    }
    const errors = check(spec, values);
    if (errors.length) throw new Error(errors.join("; "));
    return values;
  }

  private async analyse(): Promise<void> {
    const recordId = this.record.value;
    const spec = this.methods.find((m) => m.name === this.method.value);
    if (!recordId || !spec) return this.say("pick a record and a method first", true);
    try {
      const parameters = overrides(spec, this.readParams(spec));
      this.say(`running ${spec.title} on ${short(recordId)}…`);
      const result = await this.ctx.api.analyse(recordId, { method: spec.name, parameters });
      this.lastResult = result;
      this.estimates.textContent = resultLines(result).join("\n");
      this.say(`analysis ${short(result.result_id)} ${result.status}`, result.status === "failed");
    } catch (e) {
      this.say(describe(e), true);
    }
  }

  private async showOverlays(): Promise<void> {
    if (!this.record.value) return this.say("pick a record first", true);
    await this.replay({ record_id: this.record.value });
  }

  private async showOutput(): Promise<void> {
    if (!this.lastResult?.output) return this.say("run an analysis that produced an output first", true);
    await this.replay({ result_id: this.lastResult.result_id });
  }

  private async replay(request: { record_id?: string; result_id?: string }): Promise<void> {
    try {
      await this.ctx.api.replay(request);
      this.say(`replaying ${short(request.record_id ?? request.result_id ?? "")} on the stream`);
    } catch (e) {
      this.say(describe(e), true);
    }
  }
}

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.status} ${e.detail}`;
  return e instanceof Error ? e.message : String(e);
}
