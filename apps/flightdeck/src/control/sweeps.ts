// Sweep builders (Step 4b): turn a small form into a `SweepDefinition` the server compiles. Three shapes:
// a *stage* sweep (outer gate stepped by its DC line, inner gate swept by pulses in the sequencer, the
// pulse sequence run per pixel), a *DC* sweep (both axes stepped, a level sensed at every point), and a
// *capture* (a time-resolved record from a WaveformSense channel, optionally at every point of a stepped
// axis; ADR 0047). The first two may drop the outer axis for a 1-D sweep. Pure functions: no DOM, no network.
import type { CapturedWaveform, ChannelMap, FixedLevel, StandConfig, SweepDefinition } from "../schema/api";
import { buildBindings, buildSequence, templateRows, unusedStageAxes, type BindingRow, type OpRow } from "./sequence";

export interface AxisForm {
  /** Logical channel the axis steps or pulses. */
  channel: string;
  start: number;
  stop: number;
  num: number;
  /** Axis (and Dataset dimension) name; defaults to the channel name without a `_pulse` suffix. */
  name?: string;
}

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

const axis = (a: AxisForm) => ({ name: axisName(a), channel: a.channel, start: a.start, stop: a.stop, num: a.num });

const RESERVED = new Set(["repeat", "shot"]);

function checkAxes(outer: AxisForm | null | undefined, inner: AxisForm): string[] {
  const errors = [...(outer ? checkAxis(outer) : []), ...checkAxis(inner)];
  if (outer && axisName(outer) === axisName(inner)) errors.push("outer and inner axes need different names");
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
  const results = body.flatMap((op) => (op.op === "measure" || op.op === "difference" ? [op.result] : []));
  if (built.sequence && !body.some((op) => op.op === "measure")) errors.push("the sequence measures nothing");
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
      reduce: f.shots > 1 ? Object.fromEntries(results.map((r) => [r, "mean"])) : {},
    },
    repeats: 1,
  } as SweepDefinition;
}

/** Axes stepped on DC lines, the sensor read at every point (e.g. Coulomb diamonds: gate × bias). */
export function dcSweep(f: DcSweepForm): SweepDefinition {
  const errors = checkAxes(f.outer, f.inner);
  if (!f.sensor) errors.push("a DC sweep needs a sensor channel");
  const axes = f.outer ? [axis(f.outer), axis(f.inner)] : [axis(f.inner)];
  errors.push(...checkResults([f.result], axes.map((a) => a.name)));
  if (f.sensor && axes.some((a) => a.channel === f.sensor)) errors.push("a channel is a stepped axis or the sensed level, not both");
  if (errors.length) throw new Error(errors.join("; "));
  return {
    name: f.name || "sweep",
    axes,
    ...(f.levels?.length ? { levels: [...f.levels] } : {}),
    sensed: [{ name: f.result, channel: f.sensor }],
    stage: null,
    repeats: 1,
  } as SweepDefinition;
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
  const captured: CapturedWaveform = { name: f.result, channel: f.channel, start_s: f.startS, stop_s: f.stopS, num: f.num, records: f.records };
  return {
    name: f.name || "capture",
    axes,
    ...(f.levels?.length ? { levels: [...f.levels] } : {}),
    sensed: [],
    captured: [captured],
    stage: null,
    repeats: 1,
  } as SweepDefinition;
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
