// Sweep builders (Step 4b): turn a small form into a `SweepDefinition` the server compiles. Three shapes:
// a *stage* sweep (outer gate stepped by its DC line, inner gate swept by pulses in the sequencer, the
// pulse sequence run per pixel), a *DC* sweep (both axes stepped, a level sensed at every point), and a
// *capture* (a time-resolved record from a WaveformSense channel, optionally at every point of a stepped
// axis; ADR 0047). The first two may drop the outer axis for a 1-D sweep. The innermost stepped axis may be
// *triggered* (ADR 0064, 0066): loaded as a list and advanced by the stage's sequencer, which then reads in the
// shot what was read per point (a DC sweep's sensor as a measure, a capture as a capture op). Pure functions:
// no DOM, no network.
import type { CapturedWaveform, ChannelMap, FixedLevel, StandConfig, SweepAxis, SweepDefinition } from "../schema/api";
import { buildBindings, buildSequence, templateRows, unusedStageAxes, type BindingRow, type OpRow } from "./sequence";

export interface AxisForm {
  /** Logical channel the axis steps or pulses. */
  channel: string;
  start: number;
  stop: number;
  num: number;
  /** Axis (and Dataset dimension) name; defaults to the channel name without a `_pulse` suffix. */
  name?: string;
  /** A virtual gate (ADR 0049): other DC channels moved with this axis, volts per volt. Stepped axes only. */
  couplings?: Readonly<Record<string, number>>;
  /** How a stepped axis advances (ADR 0064): set point by point (default), or loaded as a list and
   * advanced by the stage's sequencer. Only the innermost stepped axis may be triggered. */
  stepping?: Stepping;
}

export type Stepping = NonNullable<SweepAxis["stepping"]>;
export type SweepKind = "stage" | "dc" | "capture";

/** One operating-point row as typed: a DC channel and its level (ADR 0038). */
export interface LevelRow {
  channel: string;
  value: string;
}

/** Operating-point rows → `FixedLevel`s: DC channels the sweep does not touch, one level each. */
export function buildLevels(rows: readonly LevelRow[], dc: readonly ChannelMap[], touched: readonly string[]): { levels: FixedLevel[]; errors: string[] } {
  const errors: string[] = [];
  const levels: FixedLevel[] = [];
  const seen = new Set<string>();
  for (const { channel, value } of rows) {
    const where = `operating point ${channel || "(no channel)"}`;
    const v = value.trim();
    if (!dc.some((c) => c.logical === channel)) errors.push(`${where}: pick a DC channel`);
    else if (touched.includes(channel)) errors.push(`${where}: the sweep already steps or senses ${channel}`);
    else if (seen.has(channel)) errors.push(`${where}: given twice`);
    else if (v === "" || !Number.isFinite(Number(v))) errors.push(`${where}: level must be a number`);
    else levels.push({ channel, value: Number(v) });
    seen.add(channel);
  }
  return { levels, errors };
}

export interface StageSweepForm {
  name: string;
  /** Operating point (ADR 0038): DC levels held for the whole sweep. */
  levels?: readonly FixedLevel[];
  /** Stepped by its DC line; absent for a 1-D sweep. */
  outer?: AxisForm | null;
  /** Pulsed inside the sequencer stage; its channel must be a pulse line of `instrument`. */
  inner: AxisForm;
  /** Sensor channel the stage measures. */
  sensor: string;
  /** Sequencer instrument id (ChannelMap.instrument of the inner channel). */
  instrument: string;
  shots: number;
  /** Pulse step length before the measure, ns. */
  stepNs: number;
  /** Measure (integration) length, ns. */
  measureNs: number;
  /** Data variable name for the measured current. */
  result: string;
  /** The edited pulse sequence (`sequence.ts`); absent → the one-step template from the fields above. */
  sequence?: { rows: readonly OpRow[]; bindings: readonly BindingRow[]; channels: readonly ChannelMap[] };
}

export interface DcSweepForm {
  name: string;
  /** Operating point (ADR 0038): DC levels held for the whole sweep. */
  levels?: readonly FixedLevel[];
  /** Absent for a 1-D sweep. */
  outer?: AxisForm | null;
  inner: AxisForm;
  /** Sensor channel read at every point. */
  sensor: string;
  /** Data variable name for the sensed level. */
  result: string;
  /** With the inner axis triggered (ADR 0064, 0066): the sequencer that advances it reads the sensor in a
   * one-measure shot instead, integrating `measureNs`, `shots` times per point, averaged. */
  shot?: { instrument: string; measureNs: number; shots: number };
}

export function axisName(a: AxisForm): string {
  return a.name ?? a.channel.replace(/_pulse$/, "");
}

export function checkAxis(a: AxisForm): string[] {
  const errors: string[] = [];
  if (!a.channel) errors.push("axis needs a channel");
  if (!Number.isFinite(a.start) || !Number.isFinite(a.stop)) errors.push(`${axisName(a) || "axis"}: start and stop must be numbers`);
  if (!Number.isInteger(a.num) || a.num < 1) errors.push(`${axisName(a) || "axis"}: num must be a positive integer`);
  return errors;
}

const axis = (a: AxisForm) => ({
  name: axisName(a),
  channel: a.channel,
  start: a.start,
  stop: a.stop,
  num: a.num,
  ...(a.couplings && Object.keys(a.couplings).length ? { couplings: { ...a.couplings } } : {}),
  // "software" is the default and is never sent, so definitions without a triggered axis keep their hash
  ...(a.stepping === "triggered" ? { stepping: "triggered" as const } : {}),
});

const RESERVED = new Set(["repeat", "shot"]);

function checkAxes(outer: AxisForm | null | undefined, inner: AxisForm): string[] {
  const errors = [...(outer ? checkAxis(outer) : []), ...checkAxis(inner)];
  if (outer && axisName(outer) === axisName(inner)) errors.push("outer and inner axes need different names");
  for (const a of outer ? [outer, inner] : [inner]) {
    for (const [other, v] of Object.entries(a.couplings ?? {})) {
      if (other === a.channel) errors.push(`${axisName(a)}: a gate cannot couple to itself`);
      if (!Number.isFinite(v)) errors.push(`${axisName(a)}: coupling to ${other} must be a number`);
    }
  }
  for (const a of outer ? [outer, inner] : [inner]) if (RESERVED.has(axisName(a))) errors.push(`"${axisName(a)}" is a reserved dimension name`);
  return errors;
}

function checkResults(results: readonly string[], axisNames: readonly string[]): string[] {
  return results.flatMap((r) =>
    RESERVED.has(r) ? [`"${r}" is a reserved dimension name`] : axisNames.includes(r) ? [`result "${r}" has an axis's name`] : [],
  );
}

/** Outer gate on its DC line (if any), inner gate pulsed by the sequencer; per pixel the edited sequence,
 * or the template `step(inner, v_<inner>) ; measure(sensor)`. */
export function stageSweep(f: StageSweepForm): SweepDefinition {
  const errors = checkAxes(f.outer, f.inner);
  if (!f.instrument) errors.push("stage needs a sequencer instrument");
  if (!Number.isInteger(f.shots) || f.shots < 1) errors.push("shots must be a positive integer");
  const inner = axisName(f.inner);
  if (f.inner.couplings && Object.keys(f.inner.couplings).length) errors.push(`${inner}: a stage axis expresses its couplings in the pulse sequence, not as a virtual gate`);
  if (f.inner.stepping === "triggered") errors.push(`${inner}: the pulsed axis is swept by the sequencer, not triggered; the outer DC axis can be`);
  const axes = f.outer ? [axis(f.outer), axis(f.inner)] : [axis(f.inner)];
  const axisNames = axes.map((a) => a.name);
  const symbol = `v_${inner}`;
  const rows = f.sequence?.rows ?? templateRows({ channel: f.inner.channel, symbol, sensor: f.sensor, stepNs: f.stepNs, measureNs: f.measureNs, result: f.result });
  const channels = f.sequence?.channels ?? [
    { logical: f.inner.channel, instrument: f.instrument, channel: f.inner.channel, quantity: "voltage" },
    { logical: f.sensor, instrument: f.instrument, channel: f.sensor, quantity: "current" },
  ];
  const built = buildSequence(`read ${f.sensor} at a ${f.inner.channel} level`, rows, channels);
  errors.push(...built.errors);
  const bound = buildBindings(f.sequence?.bindings ?? [{ symbol, target: inner }], axisNames);
  errors.push(...bound.errors);
  if (!bound.errors.length) errors.push(...unusedStageAxes(bound.bindings, [inner]));
  const body = built.sequence?.body ?? [];
  const results = body.flatMap((op) => (op.op === "measure" || op.op === "difference" || op.op === "capture" ? [op.result] : []));
  const captures = body.flatMap((op) => (op.op === "capture" ? [op.result] : []));
  if (built.sequence && !body.some((op) => op.op === "measure" || op.op === "capture")) errors.push("the sequence measures or captures nothing");
  // the server's rule (ADR 0060): the scope is armed per stepped point, so a shot with a capture has no
  // pulsed axis; this sweep always pulses one
  if (captures.length) errors.push("a capture in the shot needs a stage without a pulsed axis (ADR 0060): use the capture kind, whose triggered stepping puts the record in the shot");
  errors.push(...checkResults(results, axisNames));
  if (errors.length) throw new Error(errors.join("; "));
  return {
    name: f.name || "sweep",
    axes,
    ...(f.levels?.length ? { levels: [...f.levels] } : {}),
    sensed: [],
    stage: {
      instrument: f.instrument,
      axes: [inner],
      sequence: built.sequence!,
      bindings: bound.bindings,
      shots: f.shots,
      // a capture keeps every shot: the executor never averages a record (ADR 0018, 0060)
      reduce: f.shots > 1 ? Object.fromEntries(results.filter((r) => !captures.includes(r)).map((r) => [r, "mean"])) : {},
    },
    repeats: 1,
  } as SweepDefinition;
}

/** Axes stepped on DC lines, the sensor read at every point (e.g. Coulomb diamonds: gate × bias). With the
 * inner axis triggered (ADR 0064, 0066) the sequencer that advances it reads the sensor in a one-measure shot:
 * the readout the executor would make per point, moved into the shot. */
export function dcSweep(f: DcSweepForm): SweepDefinition {
  const errors = checkAxes(f.outer, f.inner);
  if (!f.sensor) errors.push("a DC sweep needs a sensor channel");
  const axes = f.outer ? [axis(f.outer), axis(f.inner)] : [axis(f.inner)];
  errors.push(...checkResults([f.result], axes.map((a) => a.name)));
  if (f.sensor && axes.some((a) => a.channel === f.sensor)) errors.push("a channel is a stepped axis or the sensed level, not both");
  if (f.outer?.stepping === "triggered") errors.push(`${axisName(f.outer)}: only the innermost stepped axis (here the inner one) can be triggered`);
  const triggered = f.inner.stepping === "triggered";
  if (triggered) {
    if (!f.shot?.instrument) errors.push(`${axisName(f.inner)}: a triggered axis needs the sequencer that advances it and reads the sensor in the shot`);
    else {
      if (!Number.isInteger(f.shot.measureNs) || f.shot.measureNs < 1) errors.push("the integration is a whole number of ns ≥ 1");
      if (!Number.isInteger(f.shot.shots) || f.shot.shots < 1) errors.push("shots must be a positive integer");
    }
  }
  if (errors.length) throw new Error(errors.join("; "));
  const common = { name: f.name || "sweep", axes, ...(f.levels?.length ? { levels: [...f.levels] } : {}), repeats: 1 };
  if (triggered) {
    const shot = f.shot!;
    return {
      ...common,
      sensed: [],
      stage: {
        instrument: shot.instrument,
        axes: [],
        sequence: { name: `read ${f.sensor} at each ${axisName(f.inner)} point`, body: [{ op: "measure", channel: f.sensor, duration: shot.measureNs, result: f.result }] },
        bindings: [],
        shots: shot.shots,
        reduce: shot.shots > 1 ? { [f.result]: "mean" } : {},
      },
    } as SweepDefinition;
  }
  return { ...common, sensed: [{ name: f.result, channel: f.sensor }], stage: null } as SweepDefinition;
}

export interface CaptureForm {
  name: string;
  /** Operating point (ADR 0038): DC levels held for the whole capture. */
  levels?: readonly FixedLevel[];
  /** Stepped by its DC line, one record set per point; absent for a single capture. */
  outer?: AxisForm | null;
  /** WaveformSense channel that is armed. */
  channel: string;
  /** Time window relative to the trigger, seconds. */
  startS: number;
  stopS: number;
  /** Samples per record. */
  num: number;
  /** Records per point (a `record` dimension when > 1). */
  records: number;
  /** Data variable name for the record. */
  result: string;
  /** With the outer axis triggered (ADR 0064, 0066): the sequencer that advances it, and how long the shot
   * waits after the record before the next point (the scope re-arms; ADR 0063, 0065). The capture then sits
   * in the shot, one record per shot (`records` shots per point), starting at the marker. */
  shot?: { instrument: string; paceNs: number };
}

/** One WaveformSense channel armed per point of an optional stepped axis (ADR 0047): the shape of L2-3. */
export function captureSweep(f: CaptureForm): SweepDefinition {
  const errors = f.outer ? checkAxis(f.outer) : [];
  if (f.outer && RESERVED_CAPTURE.has(axisName(f.outer))) errors.push(`"${axisName(f.outer)}" is a reserved dimension name`);
  if (!f.channel) errors.push("a capture needs a WaveformSense channel");
  if (f.outer && f.outer.channel === f.channel) errors.push("a channel is a stepped axis or the captured one, not both");
  if (!Number.isFinite(f.startS) || !Number.isFinite(f.stopS)) errors.push("start and stop must be numbers (s)");
  else if (!(f.stopS > f.startS)) errors.push("stop must be after start");
  if (!Number.isInteger(f.num) || f.num < 2) errors.push("samples must be an integer of at least 2");
  if (!Number.isInteger(f.records) || f.records < 1) errors.push("records must be a positive integer");
  const axes = f.outer ? [axis(f.outer)] : [];
  if (RESERVED_CAPTURE.has(f.result) || axes.some((a) => a.name === f.result || a.name === `${f.result}_time`)) errors.push(`"${f.result}" clashes with a dimension name`);
  if (errors.length) throw new Error(errors.join("; "));
  const triggered = f.outer?.stepping === "triggered";
  const durationNs = Math.round(f.stopS * 1e9);
  if (triggered) {
    if (!f.shot?.instrument) errors.push(`${axisName(f.outer!)}: a triggered axis needs the sequencer that advances it and plays the shot`);
    else if (!Number.isInteger(f.shot.paceNs) || f.shot.paceNs < 0) errors.push("the wait between records is a whole number of ns ≥ 0");
    if (f.startS !== 0) errors.push("in the shot the record starts at the capture, its marker: start must be 0");
    if (!(durationNs >= 1)) errors.push("the window (stop) must be at least 1 ns");
  }
  if (errors.length) throw new Error(errors.join("; "));
  const common = { name: f.name || "capture", axes, ...(f.levels?.length ? { levels: [...f.levels] } : {}), sensed: [], repeats: 1 };
  if (triggered) {
    const shot = f.shot!;
    // the record moves into the shot (ADR 0060, 0064): one per shot, `records` shots per point, kept
    return {
      ...common,
      stage: {
        instrument: shot.instrument,
        axes: [],
        sequence: {
          name: `capture ${f.channel} at each ${axisName(f.outer!)} point`,
          body: [
            { op: "capture", channel: f.channel, duration: durationNs, num: f.num, result: f.result },
            ...(shot.paceNs > 0 ? [{ op: "wait", duration: shot.paceNs }] : []),
          ],
        },
        bindings: [],
        shots: f.records,
      },
    } as SweepDefinition;
  }
  const captured: CapturedWaveform = { name: f.result, channel: f.channel, start_s: f.startS, stop_s: f.stopS, num: f.num, records: f.records };
  return { ...common, captured: [captured], stage: null } as SweepDefinition;
}

const RESERVED_CAPTURE = new Set([...RESERVED, "record", "time"]);

export interface StandChannels {
  /** Voltage channels stepped by a level source (DC lines). */
  dc: ChannelMap[];
  /** Voltage channels a sequencer pulses (the stand's `_pulse` convention). */
  pulse: ChannelMap[];
  /** Current channels: sensors. */
  sensors: ChannelMap[];
  /** Channels a WaveformSense instrument can capture a record on (ADR 0047). */
  waveforms: ChannelMap[];
}

/** Classify a stand's channels for the form's selects. A channel on an instrument that only captures
 * (a scope) is a waveform, not a DC line; a pulse line stays a pulse line. */
export function standChannels(stand: StandConfig): StandChannels {
  const having = (cap: string) => new Set(stand.instruments.filter((i) => i.capabilities.includes(cap as never)).map((i) => i.id));
  const sequencers = having("sequencer");
  const capturing = having("waveform_sense");
  const setting = having("level_source");
  const out: StandChannels = { dc: [], pulse: [], sensors: [], waveforms: [] };
  for (const c of stand.channels) {
    const pulse = c.logical.endsWith("_pulse") && sequencers.has(c.instrument);
    if (capturing.has(c.instrument) && !pulse) out.waveforms.push(c);
    if (c.quantity === "current") out.sensors.push(c);
    else if (pulse) out.pulse.push(c);
    else if (setting.has(c.instrument) || !capturing.has(c.instrument)) out.dc.push(c);
  }
  return out;
}

const hasCapability = (i: StandConfig["instruments"][number], cap: string) => (i.capabilities as readonly string[]).includes(cap);

/** The sequencer whose trigger can advance `channel` as a loaded list (ADR 0064), or why none can: its
 * instrument must load lists (`triggered_level_source`) and either be a sequencer itself (the simulated device
 * triggers itself) or name a sequencer's channel as `settings.trigger_from`, the marker line wired to its
 * trigger input. Mirrors the compiler, so the control can say why before a compile. Pure. */
export function triggerFor(stand: StandConfig, channel: string): { sequencer: string } | { reason: string } {
  const c = stand.channels.find((x) => x.logical === channel);
  if (!c) return { reason: `no channel ${channel} on the stand` };
  const instrument = stand.instruments.find((i) => i.id === c.instrument);
  if (!instrument) return { reason: `no instrument ${c.instrument} on the stand` };
  if (!hasCapability(instrument, "triggered_level_source")) return { reason: `${instrument.id} cannot load a list of levels (no triggered_level_source)` };
  if (hasCapability(instrument, "sequencer")) return { sequencer: instrument.id };
  const line = instrument.settings?.trigger_from;
  if (line === undefined || line === "") return { reason: `${instrument.id} has no settings.trigger_from: no sequencer marker line advances it` };
  const lineChannel = stand.channels.find((x) => x.logical === String(line));
  const sequencer = lineChannel && stand.instruments.find((i) => i.id === lineChannel.instrument);
  if (!sequencer || !hasCapability(sequencer, "sequencer")) return { reason: `${instrument.id}'s trigger_from ${String(line)} is not a channel of a sequencer` };
  return { sequencer: sequencer.id };
}

/** What the stepping control offers (ADR 0066): the form's axis it applies to (the innermost stepped axis of
 * the kind: a stage or capture sweep's outer axis, a DC sweep's inner one), and the sequencer that would
 * advance it, or why it cannot be triggered. Pure. */
export interface SteppingChoice {
  axis: "outer" | "inner" | null;
  channel: string;
  sequencer?: string;
  reason?: string;
}

export function steppingFor(
  stand: StandConfig,
  kind: SweepKind,
  form: { outer: string; inner: string; sensor: string; capture: string },
): SteppingChoice {
  const axis = kind === "dc" ? (form.inner ? "inner" : null) : form.outer ? "outer" : null;
  if (!axis) return { axis, channel: "", reason: "a triggered axis is a stepped DC axis: pick an outer channel" };
  const channel = axis === "inner" ? form.inner : form.outer;
  const t = triggerFor(stand, channel);
  if ("reason" in t) return { axis, channel, reason: t.reason };
  const instrumentOf = (logical: string) => stand.channels.find((c) => c.logical === logical)?.instrument;
  if (kind === "stage") {
    const pulsed = instrumentOf(form.inner);
    if (pulsed && pulsed !== t.sequencer) return { axis, channel, reason: `${channel} is advanced by ${t.sequencer}, but the pulsed axis runs on ${pulsed}` };
  }
  if (kind === "dc" && form.sensor && instrumentOf(form.sensor) !== t.sequencer) {
    return { axis, channel, reason: `triggered, the sensor is read in the shot by ${t.sequencer}, and ${form.sensor} is not one of its inputs` };
  }
  if (kind === "capture" && form.capture && instrumentOf(form.capture) === t.sequencer) {
    return { axis, channel, reason: `a capture in the shot runs on a scope of its own, not on the sequencer's input ${form.capture} (ADR 0060)` };
  }
  return { axis, channel, sequencer: t.sequencer };
}

/** Why a triggered axis's virtual-gate companions (ADR 0049) cannot follow it: they are loaded as lists too
 * and must be advanced by the same sequencer (ADR 0064). Empty when they can. Pure. */
export function companionErrors(stand: StandConfig, couplings: Readonly<Record<string, number>> | undefined, sequencer: string): string[] {
  return Object.keys(couplings ?? {}).flatMap((ch) => {
    const t = triggerFor(stand, ch);
    if ("reason" in t) return [`the triggered axis moves ${ch} as a virtual gate, but ${t.reason}`];
    return t.sequencer === sequencer ? [] : [`the triggered axis moves ${ch} as a virtual gate, but ${ch} is advanced by ${t.sequencer}, not ${sequencer}`];
  });
}
