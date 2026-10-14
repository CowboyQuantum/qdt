// Sweep builders (Step 4b): turn a small form into a `SweepDefinition` the server compiles. Two shapes
// cover the Step 4 demos: a *stage* sweep (outer gate stepped by its DC line, inner gate swept by pulses
// in the sequencer, the pulse sequence run per pixel) and a *DC* sweep (both axes stepped, a level sensed
// at every point). Either may drop the outer axis for a 1-D sweep. Pure functions: no DOM, no network.
import type { ChannelMap, StandConfig, SweepDefinition } from "../schema/api";
import { buildBindings, buildSequence, templateRows, type BindingRow, type OpRow } from "./sequence";

export interface AxisForm {
  /** Logical channel the axis steps or pulses. */
  channel: string;
  start: number;
  stop: number;
  num: number;
  /** Axis (and Dataset dimension) name; defaults to the channel name without a `_pulse` suffix. */
  name?: string;
}

export interface StageSweepForm {
  name: string;
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
  const results = built.sequence ? built.sequence.body.flatMap((op) => (op.op === "measure" ? [op.result] : [])) : [];
  if (built.sequence && !results.length) errors.push("the sequence measures nothing");
  errors.push(...checkResults(results, axisNames));
  if (errors.length) throw new Error(errors.join("; "));
  return {
    name: f.name || "sweep",
    axes,
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
    sensed: [{ name: f.result, channel: f.sensor }],
    stage: null,
    repeats: 1,
  } as SweepDefinition;
}

export interface StandChannels {
  /** Voltage channels stepped by a level source (DC lines). */
  dc: ChannelMap[];
  /** Voltage channels a sequencer pulses (the stand's `_pulse` convention). */
  pulse: ChannelMap[];
  /** Current channels: sensors. */
  sensors: ChannelMap[];
}

/** Classify a stand's channels for the form's selects. */
export function standChannels(stand: StandConfig): StandChannels {
  const sequencers = new Set(stand.instruments.filter((i) => i.capabilities.includes("sequencer")).map((i) => i.id));
  const out: StandChannels = { dc: [], pulse: [], sensors: [] };
  for (const c of stand.channels) {
    if (c.quantity === "current") out.sensors.push(c);
    else if (c.logical.endsWith("_pulse") && sequencers.has(c.instrument)) out.pulse.push(c);
    else out.dc.push(c);
  }
  return out;
}
