// The Sweep widget (ADR 0054, 0056): the sweep form of Step 4b–6 over the unchanged pure builders in
// `control/sweeps.ts` (stage, DC, capture; the operating-point levels of ADR 0038), plus compile. It
// never runs: the strip's one Run asks (`run:request`) and this widget, which holds the compiled plan,
// starts the run and follows it (`run:state`). Editing after a compile marks the plan stale
// (`plan:changed`); Run then compiles again before it runs, so what runs is always what the editors hold.
// The pulse sequence comes from the Pulse widget over the bus (`pulse:sequence`); this widget tells it
// the axes and the sensor the template follows (`sweep:axes`).
import { ApiError } from "../api/client";
import type { ChannelMap, ExecutionPlan, Run, StandConfig, SweepDefinition } from "../schema/api";
import type { BindingRow, OpRow } from "../control/sequence";
import {
  axisName,
  buildLevels,
  captureSequencer,
  captureSweep,
  dcSweep,
  sensorPerPoint,
  sensorResult,
  sensorSequencer,
  stageSweep,
  standChannels,
  type AxisForm,
  type LevelRow,
  type Readout,
  type StandChannels,
  type Stepping,
} from "../control/sweeps";
import { h } from "../workspace/dom";
import type { Widget, WidgetContext } from "../workspace/widget";

const short = (id: string) => id.slice(0, 8);
const TERMINAL = new Set(["completed", "aborted", "failed"]);

export type SweepKind = "stage" | "dc" | "capture";

/** One line about a compiled plan for the strip and the widget: axes, points, channels, a stage program. */
export function planSummary(plan: ExecutionPlan): string {
  const dims = plan.dataset.dims ?? [];
  const points = dims.reduce((a, d) => a * (d.size ?? 1), 1);
  const axes = dims.map((d) => `${d.name} ${d.size ?? "?"}`).join(" × ");
  return `${plan.definition.name} · ${axes || "no axes"} · ${points.toLocaleString()} pts · ${plan.channels.length} channels${plan.stage_program ? " · stage program" : ""}`;
}

/** How each axis of a compiled plan advances (ADR 0066): the server decides from the stand, this says what
 * it chose, one line per axis. Pure. */
export function pacingLines(plan: ExecutionPlan): string[] {
  return (plan.pacing ?? []).map((p) => {
    if (p.pacing === "sequencer") return `${p.axis}: swept in the sequence`;
    if (p.pacing === "software") return `${p.axis}: stepped from the host`;
    return `${p.axis}: triggered ${p.lines?.length ? `on ${p.lines.join(", ")}` : "by the sequencer itself"}`;
  });
}

/** The next-run line before anything is compiled: what the form says. Pure. */
export function formSummary(v: (name: string) => string): string {
  const kind = v("kind");
  const outer = v("outer_channel");
  const inShot = (kind === "dc" || kind === "capture") && v("readout") === "shot"; // ADR 0067
  const parts = [outer && `${outer} ${v("outer_num")}`, kind === "capture" ? `${v("capture_channel")} ${v("capture_num")} samples` : `${v("inner_channel")} ${v("inner_num")}`].filter(Boolean);
  return `${v("name") || "sweep"} · ${kind}${inShot ? " in the shot" : ""} · ${parts.join(" × ")}`;
}

export const sweepWidget: Widget = {
  id: "sweep",
  label: "Sweep",
  sub: "axes, operating point, compile",
  single: true,
  mount(body, head, ctx) {
    const w = new SweepWidget(body, head, ctx);
    return () => w.unmount();
  },
};

class SweepWidget {
  private stand: StandChannels = { dc: [], pulse: [], sensors: [], waveforms: [] };
  private standConfig: StandConfig | null = null;
  /** The sequencer a DC or capture sweep read in the shot runs on (ADR 0067); "" when it cannot. */
  private shotSequencer = "";
  private channels: ChannelMap[] = [];
  private levelRows: LevelRow[] = [];
  private sequence: { rows: OpRow[]; bindings: BindingRow[]; errors: string[] } | null = null;
  /** axis channel → companion → V/V from the Virtual gates widget (ADR 0049); empty when none is open. */
  private couplings: Record<string, Record<string, number>> = {};
  /** The last compile: what Run runs unless the editors changed since (then it compiles again first). */
  private compiled: { plan: ExecutionPlan; definition: SweepDefinition; options: Record<string, string | number | boolean> } | null = null;
  private stale = false;
  /** Every run this widget started, by id; the server queues them (one executes at a time). */
  private readonly runs = new Map<string, Run>();
  private starting = false;
  private readonly form: HTMLFormElement;
  private readonly capture: HTMLFieldSetElement;
  private readonly levels: HTMLDivElement;
  private readonly levelErrors: HTMLUListElement;
  private readonly planBox: HTMLPreElement;
  private readonly sweepOnly: HTMLElement[] = [];
  private readonly steppingField: HTMLElement;
  private readonly steppingHint: HTMLDivElement;
  private readonly readoutField: HTMLElement;
  private readonly readoutHint: HTMLDivElement;
  private readonly shotsField: HTMLElement;
  private readonly measureField: HTMLElement;
  private readonly paceField: HTMLElement;
  private readonly offs: (() => void)[] = [];

  constructor(
    private readonly body: HTMLElement,
    private readonly head: HTMLElement,
    private readonly ctx: WidgetContext,
  ) {
    this.form = h("form", { className: "sweep", attrs: { "aria-label": "Sweep" } });
    this.capture = h("fieldset", { className: "capture" });
    this.levels = h("div", { className: "levels" });
    this.levelErrors = h("ul", { className: "errors level-errors" });
    this.planBox = h("pre", { className: "plan", text: "not compiled" });
    // ADR 0066: a preference for the innermost stepped axis of a sweep with a shot; the compiler decides
    this.steppingField = h(
      "label",
      {},
      "stepping",
      h(
        "select",
        { name: "stepping", title: "How the innermost stepped axis advances (ADR 0066); compile shows what the stand chose" },
        h("option", { value: "auto", text: "auto: the stand decides" }),
        h("option", { value: "software", text: "software: set from the host" }),
        h("option", { value: "triggered", text: "triggered: required" }),
      ),
    );
    this.steppingHint = h("div", { className: "hint", attrs: { "data-stepping-hint": "" } });
    // ADR 0067: a DC or capture sweep reads per point (the host) or in the shot (the sequencer)
    this.readoutField = h("label", {}, "readout", h("select", { name: "readout" }, h("option", { value: "point", text: "per point" }), h("option", { value: "shot", text: "in the shot" })));
    this.readoutHint = h("div", { className: "hint", attrs: { "data-readout-hint": "" } });
    this.shotsField = h("label", {}, "shots", h("input", { name: "shots", type: "number", value: "1", step: "1" }));
    this.measureField = h("label", {}, "integration (ns)", h("input", { name: "shot_measure_ns", type: "number", value: "2000", step: "1" }));
    this.paceField = h("label", {}, "wait after each record (ms)", h("input", { name: "capture_pace_ms", type: "number", value: "50", step: "any" }));
    this.build();
    body.append(h("div", { className: "form-widget" }, this.form));
    const compile = h("button", { type: "button", text: "compile", title: "Compile the sweep on the server and show the plan", attrs: { "data-compile": "" } });
    compile.addEventListener("click", () => void this.compile());
    head.append(compile);
    this.form.addEventListener("submit", (e) => {
      e.preventDefault();
      this.ctx.bus.emit("run:request", {}); // Enter in a field means Run, like before; the strip is the one control
    });
    this.form.addEventListener("input", () => this.changed());
    this.form.addEventListener("change", () => this.changed());
    this.offs.push(
      ctx.bus.on("run:request", () => void this.runNow()),
      ctx.bus.on("run:abort", () => void this.abort()),
      ctx.bus.on("pulse:sequence", (s) => {
        this.sequence = s;
        this.markStale();
      }),
      ctx.bus.on("gates:couplings", ({ matrix }) => {
        this.couplings = matrix;
        this.markStale();
      }),
      ctx.bus.on("layout:changed", () => this.emitAxes()),
    );
    void this.init();
  }

  unmount(): void {
    for (const off of this.offs.splice(0)) off();
    this.body.replaceChildren();
    this.head.replaceChildren();
    this.ctx.bus.emit("run:next", { summary: "" });
    this.runs.clear();
  }

  private async init(): Promise<void> {
    try {
      const stand = await this.ctx.api.stand();
      this.standConfig = stand;
      this.stand = standChannels(stand);
      this.channels = [...stand.channels];
      this.fillSelects();
      this.changed();
    } catch (e) {
      this.say(`server: ${describe(e)}`, true);
    }
  }

  private say(text: string, error = false): void {
    this.ctx.bus.emit("say", { text, error });
  }

  // --- the form ------------------------------------------------------------------------------------

  private build(): void {
    const f = this.form;
    const field = (label: string, input: HTMLElement) => h("label", {}, label, input);
    const num = (name: string, value: number, step = "any") => h("input", { name, type: "number", value: String(value), step });
    const axisRow = (prefix: string, a: AxisForm) =>
      h("div", { className: "axis" }, h("select", { name: `${prefix}_channel` }), num(`${prefix}_start`, a.start), num(`${prefix}_stop`, a.stop), num(`${prefix}_num`, a.num, "1"));
    const sweepOnly = (el: HTMLElement) => {
      this.sweepOnly.push(el);
      return el;
    };
    this.capture.append(
      h("legend", { text: "capture (a WaveformSense record; the outer axis above steps it, or leave it at none)" }),
      field("channel", h("select", { name: "capture_channel" })),
      field("start (s)", num("capture_start", -0.001)),
      field("stop (s)", num("capture_stop", 0.009)),
      field("samples", num("capture_num", 1000, "1")),
      field("records per point", num("capture_records", 1, "1")),
      this.paceField,
      field("variable", h("input", { name: "capture_result", value: "trace" })),
      h("div", { className: "hint", text: "times are relative to the instrument's trigger; one record per frame lands on the declared grid" }),
    );
    const addLevel = h("button", { type: "button", text: "add level" });
    addLevel.addEventListener("click", () => {
      const touched = this.touchedChannels();
      const free = this.stand.dc.find((c) => !touched.includes(c.logical) && !this.levelRows.some((r) => r.channel === c.logical));
      this.levelRows = [...this.levelRows, { channel: free?.logical ?? "", value: "0" }];
      this.renderLevels();
      this.changed();
    });
    f.append(
      field(
        "kind",
        h(
          "select",
          { name: "kind" },
          h("option", { value: "stage", text: "stage: inner axis pulsed" }),
          h("option", { value: "dc", text: "DC: both axes stepped, sensed" }),
          h("option", { value: "capture", text: "capture: a time-resolved record" }),
        ),
      ),
      field("name", h("input", { name: "name", value: "stability" })),
      h("div", { className: "axis head" }, ...["channel", "start", "stop", "num"].map((t) => h("span", { text: t }))),
      h("div", {}, "outer", axisRow("outer", { channel: "", start: 0.03, stop: 0.18, num: 48 })),
      sweepOnly(h("div", {}, "inner", axisRow("inner", { channel: "", start: 0.03, stop: 0.18, num: 48 }))),
      this.steppingField,
      this.steppingHint,
      sweepOnly(field("inner axis name", h("input", { name: "inner_name", placeholder: "defaults to the channel" }))),
      sweepOnly(field("sensor", h("select", { name: "sensor" }))),
      this.readoutField,
      this.readoutHint,
      this.shotsField,
      this.measureField,
      this.capture,
      h(
        "fieldset",
        { className: "operating-point" },
        h("legend", { text: "operating point (DC levels held for the whole sweep)" }),
        this.levels,
        h("div", { className: "buttons" }, addLevel),
        h("div", { className: "hint", text: "gates not listed keep whatever level they have; a pulse on a gate's _pulse line adds to its level here" }),
        this.levelErrors,
      ),
      field("options", h("input", { name: "options", value: '{"seed": 1, "noise": true}' })),
      h("div", { className: "hint", text: "Run is in the strip: it compiles what the editors hold and runs that; compile here to see the plan first" }),
      this.planBox,
    );
    (f.elements.namedItem("kind") as HTMLSelectElement).addEventListener("change", () => this.fillSelects());
    for (const name of ["inner_channel", "inner_name", "sensor", "outer_channel", "capture_channel"]) {
      (f.elements.namedItem(name) as HTMLElement).addEventListener("change", () => this.validateLevels()); // a newly swept channel may clash with a held one
    }
  }

  private value(name: string): string {
    return (this.form.elements.namedItem(name) as HTMLInputElement | HTMLSelectElement | null)?.value ?? "";
  }

  private fillSelects(): void {
    const f = this.form;
    const kind = this.value("kind");
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
    fill("capture_channel", this.stand.waveforms, ["scope1"]);
    this.capture.hidden = kind !== "capture";
    for (const el of this.sweepOnly) show(el, kind !== "capture");
    this.renderLevels();
    this.refreshShot();
  }

  /** The readout (ADR 0067) and stepping (ADR 0066) controls: where a DC or capture sweep reads, whether it
   * can read in the shot (else the option is disabled and the hint says why), the fields a shot needs, and
   * which axis the stepping preference applies to. */
  private refreshShot(): void {
    const kind = this.value("kind");
    const f = this.form.elements;
    const readout = f.namedItem("readout") as HTMLSelectElement;
    const [point, shot] = [readout.options[0]!, readout.options[1]!];
    const reads = kind === "dc" || kind === "capture";
    if (kind === "dc") [point.text, shot.text] = ["per point: the host senses the sensor", "in the shot: its sequencer integrates it"];
    if (kind === "capture") [point.text, shot.text] = ["per point: the host arms the scope", "in the shot: from the sequencer's marker"];
    const where = !this.standConfig
      ? { reason: "the stand is not loaded yet" }
      : kind === "dc"
        ? sensorSequencer(this.standConfig, this.value("sensor"))
        : captureSequencer(this.standConfig, this.value("capture_channel"));
    this.shotSequencer = reads && "sequencer" in where ? where.sequencer : "";
    shot.disabled = !this.shotSequencer;
    if (shot.disabled && readout.value === "shot") readout.value = "point";
    // a sequencer's own input has no meter behind it: per point is unavailable and the sensor is read in the shot
    const perPoint = kind === "dc" && this.standConfig ? sensorPerPoint(this.standConfig, this.value("sensor")) : { ok: true as const };
    point.disabled = !("ok" in perPoint);
    if (point.disabled && readout.value === "point" && this.shotSequencer) readout.value = "shot";
    const inShot = reads && readout.value === "shot";
    show(this.readoutField, reads);
    show(this.readoutHint, reads);
    this.readoutHint.textContent = !reads
      ? ""
      : !this.shotSequencer
        ? `in the shot is unavailable: ${"reason" in where ? where.reason : ""}`
        : !inShot
          ? `can instead be read in a shot of ${this.shotSequencer}, so a wired stand can trigger the ${kind === "dc" ? "inner" : "outer"} axis`
          : kind === "dc"
            ? `${this.value("sensor")} is integrated by ${this.shotSequencer} in a one-measure shot at each point, the shots averaged${"reason" in perPoint ? `; per point is unavailable: ${perPoint.reason}` : ""}`
            : "own" in where && where.own
              ? `${this.value("capture_channel")} is ${this.shotSequencer}'s own input: it records it in the shot (t = 0 at the capture), one record per shot`
              : `${this.value("capture_channel")} is captured in a shot of ${this.shotSequencer} from its marker (t = 0), one record per shot`;
    show(this.shotsField, kind === "stage" || (kind === "dc" && inShot));
    show(this.measureField, kind === "dc" && inShot);
    show(this.paceField, kind === "capture" && inShot);
    // in the shot a record starts at its marker: the start is 0 while it is there, and comes back after
    const start = f.namedItem("capture_start") as HTMLInputElement;
    if (kind === "capture" && inShot) {
      if (!start.disabled) {
        start.dataset.was = start.value;
        start.value = "0";
        start.disabled = true;
      }
    } else if (start.disabled) {
      start.value = start.dataset.was ?? start.value;
      start.disabled = false;
    }
    // the stepping preference applies to the innermost stepped axis of a sweep with a shot
    const channel = this.value(kind === "dc" ? "inner_channel" : "outer_channel");
    const stepping = kind === "stage" || inShot ? channel : "";
    show(this.steppingField, !!stepping);
    show(this.steppingHint, !!stepping);
    this.steppingHint.textContent = stepping ? `applies to ${stepping}, the innermost DC axis; auto lets the stand decide, and compile shows what it chose` : "";
  }

  /** Channels the sweep itself steps or senses: not available to the operating point. */
  private touchedChannels(): string[] {
    const kind = this.value("kind");
    if (kind === "capture") return [this.value("outer_channel"), this.value("capture_channel")].filter(Boolean);
    const out = [this.value("inner_channel"), this.value("outer_channel")];
    if (kind === "dc") out.push(this.value("sensor"));
    return out.filter(Boolean);
  }

  private renderLevels(): void {
    this.levels.replaceChildren(
      ...this.levelRows.map((row, i) => {
        const channel = h("select", { name: "level_channel" }, ...this.stand.dc.map((c) => h("option", { value: c.logical, text: c.logical })));
        channel.value = row.channel;
        channel.addEventListener("change", () => {
          row.channel = channel.value;
          this.validateLevels();
        });
        const value = h("input", { name: "level_value", value: row.value, placeholder: "level (V)" });
        value.addEventListener("input", () => {
          row.value = value.value;
          this.validateLevels();
        });
        const remove = h("button", { type: "button", text: "✕", title: "remove" });
        remove.addEventListener("click", () => {
          this.levelRows = this.levelRows.filter((_, j) => j !== i);
          this.renderLevels();
          this.changed();
        });
        return h("div", { className: "level-row" }, channel, value, h("span", { text: "V" }), remove);
      }),
    );
    this.validateLevels();
  }

  private validateLevels(): ReturnType<typeof buildLevels> {
    const built = buildLevels(this.levelRows, this.stand.dc, this.touchedChannels());
    this.levelErrors.replaceChildren(...built.errors.map((e) => h("li", { text: e })));
    return built;
  }

  /** Axis names as the sweep will have them, outer to inner: what a pulse symbol may be bound to. */
  private axisNames(): string[] {
    const inner = axisName({ channel: this.value("inner_channel"), start: 0, stop: 0, num: 1, name: this.value("inner_name").trim() || undefined });
    const outer = this.value("outer_channel");
    return outer ? [axisName({ channel: outer, start: 0, stop: 0, num: 1 }), inner] : [inner];
  }

  private emitAxes(): void {
    this.ctx.bus.emit("sweep:axes", { kind: this.value("kind") as SweepKind, axes: this.axisNames(), inner: this.value("inner_channel"), sensor: this.value("sensor") });
  }

  /** Anything in the form changed: the next-run line, the Pulse widget's template, and the plan goes stale. */
  private changed(): void {
    this.refreshShot();
    this.ctx.bus.emit("run:next", { summary: formSummary((n) => this.value(n)) });
    this.emitAxes();
    this.markStale();
  }

  private markStale(): void {
    if (!this.compiled || this.stale) return;
    this.stale = true;
    this.planBox.textContent = `${this.planBox.textContent}\n(stale: the editors changed; Run compiles again)`;
    this.ctx.bus.emit("plan:changed", {});
  }

  // --- definition, compile, run --------------------------------------------------------------------

  private readForm(): { definition: SweepDefinition; options: Record<string, string | number | boolean> } {
    const v = (name: string) => this.value(name);
    const coupled = (channel: string) => {
      const row: Record<string, number> = {};
      for (const [other, c] of Object.entries(this.couplings[channel] ?? {})) if (other !== channel && Number.isFinite(c) && c !== 0) row[other] = c;
      return row;
    };
    const axis = (prefix: string, name?: string, stepped = true): AxisForm => ({
      channel: v(`${prefix}_channel`),
      start: Number(v(`${prefix}_start`)),
      stop: Number(v(`${prefix}_stop`)),
      num: Number(v(`${prefix}_num`)),
      ...(name ? { name } : {}),
      ...(stepped ? { couplings: coupled(v(`${prefix}_channel`)) } : {}),
    });
    const options = JSON.parse(v("options") || "{}") as Record<string, string | number | boolean>;
    const sensor = v("sensor");
    const innerName = v("inner_name").trim() || undefined;
    const kind = v("kind");
    // ADR 0067: where a DC or capture sweep reads; ADR 0066: the stepping preference of the innermost
    // stepped axis of a sweep with a shot (the inner axis of a DC sweep, else the outer one)
    const readout: Readout = (kind === "dc" || kind === "capture") && v("readout") === "shot" ? "shot" : "point";
    const stepping = (v("stepping") || "auto") as Stepping;
    const paced = kind === "stage" || readout === "shot" ? { stepping } : {};
    const outer = v("outer_channel") ? { ...axis("outer"), ...(kind === "dc" ? {} : paced) } : null;
    const held = this.validateLevels();
    if (held.errors.length) throw new Error(held.errors.join("; "));
    const levels = held.levels;
    if (kind === "capture") {
      return {
        definition: captureSweep({
          name: v("name"),
          levels,
          outer,
          channel: v("capture_channel"),
          startS: Number(v("capture_start")),
          stopS: Number(v("capture_stop")),
          num: Number(v("capture_num")),
          records: Number(v("capture_records")),
          result: v("capture_result").trim() || "trace",
          readout,
          ...(readout === "shot" ? { shot: { instrument: this.shotSequencer, paceNs: Math.round(Number(v("capture_pace_ms")) * 1e6) } } : {}),
        }),
        options,
      };
    }
    if (kind === "stage") {
      const inner = this.stand.pulse.find((c) => c.logical === v("inner_channel"));
      if (!inner) throw new Error("a stage sweep needs a pulse channel for its inner axis");
      const seq = this.sequence;
      if (!seq) throw new Error("a stage sweep needs the Pulse widget's sequence: open it in a pane");
      if (seq.errors.length) throw new Error(seq.errors.join("; "));
      return {
        definition: stageSweep({
          name: v("name"),
          levels,
          outer,
          inner: axis("inner", innerName, false), // a stage axis couples in the sequence, never as a virtual gate
          sensor,
          instrument: inner.instrument,
          shots: Number(v("shots")),
          stepNs: 500,
          measureNs: 2000,
          result: sensorResult(this.channels, sensor),
          sequence: { rows: seq.rows, bindings: seq.bindings, channels: this.channels, sensors: this.stand.sensors.map((c) => c.logical) },
        }),
        options,
      };
    }
    return {
      definition: dcSweep({
        name: v("name"),
        levels,
        outer,
        inner: { ...axis("inner", innerName), ...paced },
        sensor,
        result: sensorResult(this.channels, sensor),
        readout,
        ...(readout === "shot" ? { shot: { instrument: this.shotSequencer, measureNs: Number(v("shot_measure_ns")), shots: Number(v("shots")) } } : {}),
      }),
      options,
    };
  }

  /** Compile on the server: the plan's identity goes to the strip, its summary into the widget. */
  private async compile(): Promise<typeof this.compiled> {
    try {
      const { definition, options } = this.readForm();
      const plan = await this.ctx.api.compile(definition);
      this.compiled = { plan, definition, options };
      this.stale = false;
      const summary = planSummary(plan);
      this.planBox.textContent = [`plan ${plan.plan_id}`, summary, ...pacingLines(plan)].join("\n");
      this.ctx.bus.emit("plan:compiled", { planId: plan.plan_id, summary });
      return this.compiled;
    } catch (e) {
      this.say(describe(e), true);
      return null;
    }
  }

  /** The strip's Run: what is compiled, compiled again first when the editors changed since. The server
   * queues runs (one executes at a time), so Run is never refused while one is live (ADR 0061). */
  private async runNow(): Promise<void> {
    if (this.starting) return;
    this.starting = true;
    try {
      const compiled = this.compiled && !this.stale ? this.compiled : await this.compile();
      if (!compiled) return;
      const run = await this.ctx.api.startRun({ definition: compiled.definition, options: compiled.options });
      this.setRun(run);
      const live = [...this.runs.values()].filter((r) => !TERMINAL.has(r.state)).length;
      this.say(`run ${short(run.run_id)} queued${live > 1 ? ` (${live - 1} ahead of it)` : ""}`);
      void this.follow(run.run_id);
    } catch (e) {
      this.say(describe(e), true);
    } finally {
      this.starting = false;
    }
  }

  private setRun(run: Run): void {
    this.runs.set(run.run_id, run);
    this.ctx.bus.emit("run:state", { run });
  }

  private async follow(runId: string): Promise<void> {
    while (true) {
      await new Promise((r) => setTimeout(r, 1000));
      let run: Run;
      try {
        run = await this.ctx.api.run(runId);
      } catch (e) {
        this.say(describe(e), true);
        return;
      }
      if (!this.runs.has(runId)) return; // the widget went away
      this.setRun(run);
      if (TERMINAL.has(run.state)) {
        this.say(`run ${short(runId)} ${run.state}${run.error ? `: ${run.error}` : ""}`, run.state === "failed");
        this.ctx.bus.emit("records:changed", {});
        return;
      }
    }
  }

  /** Abort the run that is executing, else the newest queued one. */
  private async abort(): Promise<void> {
    const live = [...this.runs.values()].filter((r) => !TERMINAL.has(r.state));
    const target = live.find((r) => r.state === "running") ?? live.at(-1);
    if (!target) return this.say("no run to abort", true);
    try {
      this.setRun(await this.ctx.api.abort(target.run_id));
      this.say(`run ${short(target.run_id)} aborting`);
    } catch (e) {
      this.say(describe(e), true);
    }
  }
}

/** Show or hide a form row; the stylesheet gives labels a display, which beats the UA's [hidden] rule: set both. */
function show(el: HTMLElement, on: boolean): void {
  el.hidden = !on;
  el.style.display = on ? "" : "none";
}

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.status} ${e.detail}`;
  return e instanceof Error ? e.message : String(e);
}
