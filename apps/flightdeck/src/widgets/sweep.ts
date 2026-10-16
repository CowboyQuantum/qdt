// The Sweep widget (ADR 0054, 0056): the sweep form of Step 4b–6 over the unchanged pure builders in
// `control/sweeps.ts` (stage, DC, capture; the operating-point levels of ADR 0038), plus compile. It
// never runs: the strip's one Run asks (`run:request`) and this widget, which holds the compiled plan,
// starts the run and follows it (`run:state`). Editing after a compile marks the plan stale
// (`plan:changed`); Run then compiles again before it runs, so what runs is always what the editors hold.
// The pulse sequence comes from the Pulse widget over the bus (`pulse:sequence`); this widget tells it
// the axes and the sensor the template follows (`sweep:axes`).
import { ApiError } from "../api/client";
import type { ChannelMap, ExecutionPlan, Run, SweepDefinition } from "../schema/api";
import type { BindingRow, OpRow } from "../control/sequence";
import { axisName, buildLevels, captureSweep, dcSweep, stageSweep, standChannels, type AxisForm, type LevelRow, type StandChannels } from "../control/sweeps";
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

/** The next-run line before anything is compiled: what the form says. Pure. */
export function formSummary(v: (name: string) => string): string {
  const kind = v("kind");
  const outer = v("outer_channel");
  const parts = [outer && `${outer} ${v("outer_num")}`, kind === "capture" ? `${v("capture_channel")} ${v("capture_num")} samples` : `${v("inner_channel")} ${v("inner_num")}`].filter(Boolean);
  return `${v("name") || "sweep"} · ${kind} · ${parts.join(" × ")}`;
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
  private channels: ChannelMap[] = [];
  private levelRows: LevelRow[] = [];
  private sequence: { rows: OpRow[]; bindings: BindingRow[]; errors: string[] } | null = null;
  /** The last compile: what Run runs unless the editors changed since (then it compiles again first). */
  private compiled: { plan: ExecutionPlan; definition: SweepDefinition; options: Record<string, string | number | boolean> } | null = null;
  private stale = false;
  private run: Run | null = null;
  private readonly form: HTMLFormElement;
  private readonly capture: HTMLFieldSetElement;
  private readonly levels: HTMLDivElement;
  private readonly levelErrors: HTMLUListElement;
  private readonly planBox: HTMLPreElement;
  private readonly sweepOnly: HTMLElement[] = [];
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
      ctx.bus.on("layout:changed", () => this.emitAxes()),
    );
    void this.init();
  }

  unmount(): void {
    for (const off of this.offs.splice(0)) off();
    this.body.replaceChildren();
    this.head.replaceChildren();
    this.ctx.bus.emit("run:next", { summary: "" });
  }

  private async init(): Promise<void> {
    try {
      const stand = await this.ctx.api.stand();
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
      sweepOnly(field("inner axis name", h("input", { name: "inner_name", placeholder: "defaults to the channel" }))),
      sweepOnly(field("sensor", h("select", { name: "sensor" }))),
      sweepOnly(field("shots", num("shots", 1, "1"))),
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
    for (const el of this.sweepOnly) {
      // the stylesheet gives labels a display, which beats the UA's [hidden] rule: set both
      el.hidden = kind === "capture";
      el.style.display = kind === "capture" ? "none" : "";
    }
    this.renderLevels();
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
    const held = this.validateLevels();
    if (held.errors.length) throw new Error(held.errors.join("; "));
    const levels = held.levels;
    if (v("kind") === "capture") {
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
        }),
        options,
      };
    }
    if (v("kind") === "stage") {
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
          inner: axis("inner", innerName),
          sensor,
          instrument: inner.instrument,
          shots: Number(v("shots")),
          stepNs: 500,
          measureNs: 2000,
          result: "I_sensor",
          sequence: { rows: seq.rows, bindings: seq.bindings, channels: this.channels },
        }),
        options,
      };
    }
    return { definition: dcSweep({ name: v("name"), levels, outer, inner: axis("inner", innerName), sensor, result: "I_sensor" }), options };
  }

  /** Compile on the server: the plan's identity goes to the strip, its summary into the widget. */
  private async compile(): Promise<typeof this.compiled> {
    try {
      const { definition, options } = this.readForm();
      const plan = await this.ctx.api.compile(definition);
      this.compiled = { plan, definition, options };
      this.stale = false;
      const summary = planSummary(plan);
      this.planBox.textContent = `plan ${plan.plan_id}\n${summary}`;
      this.ctx.bus.emit("plan:compiled", { planId: plan.plan_id, summary });
      return this.compiled;
    } catch (e) {
      this.say(describe(e), true);
      return null;
    }
  }

  /** The strip's Run: what is compiled, compiled again first when the editors changed since. */
  private async runNow(): Promise<void> {
    if (this.run && !TERMINAL.has(this.run.state)) return this.say(`run ${short(this.run.run_id)} is still ${this.run.state}`, true);
    const compiled = this.compiled && !this.stale ? this.compiled : await this.compile();
    if (!compiled) return;
    try {
      const run = await this.ctx.api.startRun({ definition: compiled.definition, options: compiled.options });
      this.setRun(run);
      this.say(`run ${short(run.run_id)} queued`);
      void this.follow(run.run_id);
    } catch (e) {
      this.say(describe(e), true);
    }
  }

  private setRun(run: Run | null): void {
    this.run = run;
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
      if (this.run?.run_id !== runId) return; // a newer run took over, or the widget went away
      this.setRun(run);
      if (TERMINAL.has(run.state)) {
        this.say(`run ${short(runId)} ${run.state}${run.error ? `: ${run.error}` : ""}`, run.state === "failed");
        this.ctx.bus.emit("records:changed", {});
        return;
      }
    }
  }

  private async abort(): Promise<void> {
    if (!this.run || TERMINAL.has(this.run.state)) return this.say("no run to abort", true);
    try {
      this.setRun(await this.ctx.api.abort(this.run.run_id));
      this.say(`run ${short(this.run.run_id)} aborting`);
    } catch (e) {
      this.say(describe(e), true);
    }
  }
}

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.status} ${e.detail}`;
  return e instanceof Error ? e.message : String(e);
}
