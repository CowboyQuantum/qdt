// The control panel (Step 4b, ADR 0032), shrinking one widget per session (ADR 0054): what remains is
// the held operating point (click-to-set, ADR 0053), the records list, a curated analysis and the
// tune-up runner (ADR 0050). The sweep form and the pulse editor became the Sweep and Pulse widgets
// (ADR 0056), History the records browser (ADR 0055). Talks to qdt-server through ApiClient only.
import { ApiClient, ApiError } from "../api/client";
import type { AnalysisResult, CalibrationNode, ChannelMap, FixedLevel, MeasurementRecord, MethodSpec, TuneUp } from "../schema/api";
import { check, defaults, overrides, parse, type ParamValues } from "./methods";
import { standChannels, type StandChannels } from "./sweeps";

const h = <K extends keyof HTMLElementTagNameMap>(tag: K, props: Partial<HTMLElementTagNameMap[K]> & { text?: string } = {}, ...children: (Node | string)[]) => {
  const el = document.createElement(tag);
  const { text, ...rest } = props;
  Object.assign(el, rest);
  if (text !== undefined) el.textContent = text;
  el.append(...children);
  return el;
};

const short = (id: string) => id.slice(0, 8);
const TUNEUP_TERMINAL = new Set(["completed", "stopped", "failed"]);

/** A clicked point as the setpoint it means: the coordinates whose names are DC channels of the stand
 * become levels; the rest are reported as not settable (ADR 0053). Pure, so click-to-set is testable. */
export function setpointFor(point: { name: string; value: number }[], dc: readonly ChannelMap[]): { levels: FixedLevel[]; skipped: string[] } {
  const names = new Set(dc.map((c) => c.logical));
  const levels: FixedLevel[] = [];
  const skipped: string[] = [];
  for (const p of point) {
    if (names.has(p.name) && Number.isFinite(p.value)) levels.push({ channel: p.name, value: p.value });
    else skipped.push(p.name);
  }
  return { levels, skipped };
}

/** One line per node of a tune-up: its status so far, its message, and an accepted node's outputs
 * (ADR 0050). Pure, so the DAG state the finish line asks for is testable without a DOM. */
export function tuneupLines(t: TuneUp): { node: string; status: string; message: string; outputs: string }[] {
  const byNode = new Map((t.outcomes ?? []).map((o) => [o.node_id, o]));
  return t.nodes.map((n) => {
    const o = byNode.get(n.node_id);
    const status = o ? o.status : t.current_node === n.node_id ? "running" : t.state === "running" || t.state === "queued" ? "waiting" : "not run";
    const outputs = o && o.status === "accepted" ? Object.entries(o.outputs ?? {}).map(([k, v]) => `${k}=${Number(v).toPrecision(4)}`).join(" ") : "";
    return { node: n.node_id, status, message: o?.message ?? "", outputs };
  });
}

export interface ControlHost {
  /** Report a message (an error or a status) to the user. */
  say(message: string, isError?: boolean): void;
}

export class ControlPanel {
  private stand: StandChannels = { dc: [], pulse: [], sensors: [], waveforms: [] };
  private methods: MethodSpec[] = [];
  private nodes: CalibrationNode[] = [];
  private tuneup: TuneUp | null = null;
  private records: MeasurementRecord[] = [];
  private selectedRecord: MeasurementRecord | null = null;
  private lastResult: AnalysisResult | null = null;
  private readonly els: {
    recordsList: HTMLUListElement;
    method: HTMLSelectElement;
    params: HTMLDivElement;
    analysisTarget: HTMLSpanElement;
    estimates: HTMLPreElement;
    nodes: HTMLDivElement;
    tuneupOptions: HTMLInputElement;
    tuneupState: HTMLDivElement;
    setpoint: HTMLDivElement;
    held: HTMLDivElement;
  };

  constructor(
    private readonly root: HTMLElement,
    private readonly api: ApiClient,
    private readonly host: ControlHost,
  ) {
    this.els = {
      recordsList: h("ul", { id: "records" }),
      method: h("select", { id: "method" }),
      params: h("div", { id: "params" }),
      analysisTarget: h("span", { id: "analysis-target", text: "no record selected" }),
      estimates: h("pre", { id: "estimates" }),
      nodes: h("div", { id: "nodes" }),
      tuneupOptions: h("input", { id: "tuneup-options", name: "tuneup_options", value: '{"seed": 1, "noise": true}' }),
      tuneupState: h("div", { id: "tuneup-state" }),
      setpoint: h("div", { id: "setpoint" }),
      held: h("div", { id: "held-levels" }),
    };
    this.build();
  }

  async init(): Promise<void> {
    try {
      const [stand, methods, nodes] = await Promise.all([this.api.stand(), this.api.methods(), this.api.nodes()]);
      this.stand = standChannels(stand);
      this.methods = methods;
      this.nodes = nodes;
      this.els.method.replaceChildren(...this.methods.map((m) => h("option", { value: m.name, text: m.title })));
      this.fillParams();
      this.renderNodes();
      await this.refreshRecords();
      await this.refreshHeld();
    } catch (e) {
      this.host.say(`server: ${describe(e)}`, true);
    }
  }

  // --- layout --------------------------------------------------------------------------------------

  private build(): void {
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

    const tuneup = h(
      "div",
      { id: "tuneup" },
      h("h3", { text: "Tune-up" }),
      h("div", { className: "hint", text: "calibration nodes this stand can run (ADR 0048–0050); the server orders them by their dependencies and stops at the first that is not accepted" }),
      this.els.nodes,
      h("label", {}, "options ", this.els.tuneupOptions),
      h("div", { className: "buttons" },
        h("button", { type: "button", id: "run-tuneup", text: "run tune-up", onclick: () => void this.startTuneUp() }),
        h("button", { type: "button", id: "stop-tuneup", text: "stop", onclick: () => void this.stopTuneUp() }),
      ),
      this.els.tuneupState,
    );

    const operating = h(
      "div",
      { id: "operating" },
      h("h3", { text: "Operating point on the stand" }),
      h("div", { className: "hint", text: "click a point on the map to set the gates there (FINISH_LINE's one up edge, ADR 0053); every later sweep inherits the held levels unless it moves the channel itself" }),
      this.els.setpoint,
      this.els.held,
    );

    this.root.append(
      operating,
      h("h3", {}, "Records ", h("button", { type: "button", text: "refresh", onclick: () => void this.refreshRecords() })),
      this.els.recordsList,
      analysis,
      tuneup,
    );
  }

  // --- click-to-set (ADR 0053): the view offers a point, the user sends it, the server holds it ------

  /** Offer the point the view was clicked at as a setpoint for the stand. */
  offerSetpoint(point: { name: string; unit: string; value: number }[]): void {
    const { levels, skipped } = setpointFor(point, this.stand.dc);
    const text = point.map((p) => `${p.name} = ${p.value.toPrecision(4)}${p.unit ? ` ${p.unit}` : ""}`).join(" · ");
    this.els.setpoint.replaceChildren(
      h("div", { className: "clicked", text: `clicked: ${text}` }),
      ...(levels.length
        ? [h("button", { type: "button", id: "set-levels", text: `set ${levels.map((l) => l.channel).join(", ")} on the stand`, onclick: () => void this.setLevels(levels) })]
        : []),
      ...(skipped.length ? [h("span", { className: "hint", text: ` (${skipped.join(", ")}: not a DC channel of the stand)` })] : []),
    );
  }

  private async setLevels(levels: FixedLevel[]): Promise<void> {
    try {
      this.renderHeld(await this.api.setLevels(levels));
      this.host.say(`set ${levels.map((l) => `${l.channel}=${l.value.toPrecision(4)}`).join(", ")} on the stand`);
    } catch (e) {
      this.host.say(describe(e), true);
    }
  }

  async refreshHeld(): Promise<void> {
    try {
      this.renderHeld(await this.api.levels());
    } catch (e) {
      this.host.say(describe(e), true);
    }
  }

  private renderHeld(levels: FixedLevel[]): void {
    this.els.held.replaceChildren(
      h("span", { text: levels.length ? `held: ${levels.map((l) => `${l.channel} = ${l.value.toPrecision(4)} V`).join(" · ")}` : "held: nothing (the stand is where the last sweep left it)" }),
      ...(levels.length ? [h("button", { type: "button", id: "clear-levels", text: "release", onclick: () => void this.api.clearLevels().then((l) => this.renderHeld(l)).catch((e) => this.host.say(describe(e), true)) })] : []),
    );
  }

  // --- tune-ups (ADR 0050): nodes as data, run in order on the server, the DAG state rendered -------

  private renderNodes(): void {
    this.els.nodes.replaceChildren(
      ...this.nodes.map((n) =>
        h(
          "label",
          { className: "node" },
          h("input", { type: "checkbox", name: "node", value: n.node_id, checked: true }),
          h("span", { className: "node-id", text: n.node_id }),
          h("span", { className: "node-deps", text: n.depends_on?.length ? ` ← ${n.depends_on.join(", ")}` : "" }),
          h("span", { className: "hint", text: ` ${n.description ?? ""}` }),
        ),
      ),
    );
  }

  private selectedNodeIds(): string[] {
    return [...this.els.nodes.querySelectorAll<HTMLInputElement>("input[name=node]:checked")].map((i) => i.value);
  }

  private async startTuneUp(): Promise<void> {
    const node_ids = this.selectedNodeIds();
    if (!node_ids.length) return this.host.say("pick at least one node", true);
    try {
      const options = JSON.parse(this.els.tuneupOptions.value || "{}") as Record<string, string | number | boolean>;
      this.tuneup = await this.api.startTuneUp({ node_ids: node_ids as [string, ...string[]], options });
      this.renderTuneUp();
      this.host.say(`tune-up ${short(this.tuneup.tuneup_id)} queued`);
      void this.followTuneUp(this.tuneup.tuneup_id);
    } catch (e) {
      this.host.say(describe(e), true);
    }
  }

  private async stopTuneUp(): Promise<void> {
    if (!this.tuneup || TUNEUP_TERMINAL.has(this.tuneup.state)) return this.host.say("no tune-up running", true);
    try {
      this.tuneup = await this.api.stopTuneUp(this.tuneup.tuneup_id);
      this.renderTuneUp();
      this.host.say(`tune-up ${short(this.tuneup.tuneup_id)} stopping after the current node`);
    } catch (e) {
      this.host.say(describe(e), true);
    }
  }

  private async followTuneUp(tuneupId: string): Promise<void> {
    while (true) {
      await new Promise((r) => setTimeout(r, 1000));
      try {
        this.tuneup = await this.api.tuneup(tuneupId);
      } catch (e) {
        this.host.say(describe(e), true);
        return;
      }
      this.renderTuneUp();
      if (TUNEUP_TERMINAL.has(this.tuneup.state)) {
        this.host.say(`tune-up ${short(tuneupId)} ${this.tuneup.state}${this.tuneup.message ? `: ${this.tuneup.message}` : ""}`, this.tuneup.state === "failed");
        await this.refreshRecords();
        return;
      }
    }
  }

  private renderTuneUp(): void {
    const t = this.tuneup;
    if (!t) return this.els.tuneupState.replaceChildren();
    this.els.tuneupState.replaceChildren(
      h("div", { className: "tuneup-head", text: `${short(t.tuneup_id)} ${t.name} · ${t.state}${t.message ? ` · ${t.message}` : ""}` }),
      h(
        "ol",
        { className: "dag" },
        ...tuneupLines(t).map((l) =>
          h("li", { className: `node-${l.status}` }, h("b", { text: l.node }), ` · ${l.status}`, l.message ? ` · ${l.message}` : "", l.outputs ? h("div", { className: "outputs", text: l.outputs }) : ""),
        ),
      ),
    );
  }

  // --- records and analysis ------------------------------------------------------------------------

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

// `defaults` stays exported from ./methods for the unit tests; the panel reads parameters through `parse`.
void defaults;
