// Sweep builders (Step 4b): turn a small form into a `SweepDefinition` the server compiles. Two shapes
// cover the Step 4 demos: a *stage* sweep (outer gate stepped by its DC line, inner gate swept by pulses
// in the sequencer, one measure per pixel) and a *DC* sweep (both axes stepped, a level sensed at every
// point). Pure functions: no DOM, no network.
import type { ChannelMap, StandConfig, SweepDefinition } from "../schema/api";

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
  outer: AxisForm;
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
}

export interface DcSweepForm {
  name: string;
  outer: AxisForm;
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

/** Outer gate on its DC line, inner gate pulsed by the sequencer: `step(inner, v) ; measure(sensor)`. */
export function stageSweep(f: StageSweepForm): SweepDefinition {
  const errors = [...checkAxis(f.outer), ...checkAxis(f.inner)];
  if (axisName(f.outer) === axisName(f.inner)) errors.push("outer and inner axes need different names");
  if (!f.sensor) errors.push("stage needs a sensor channel");
  if (!f.instrument) errors.push("stage needs a sequencer instrument");
  if (!Number.isInteger(f.shots) || f.shots < 1) errors.push("shots must be a positive integer");
  if (errors.length) throw new Error(errors.join("; "));
  const inner = axisName(f.inner);
  const symbol = `v_${inner}`;
  return {
    name: f.name || "sweep",
    axes: [axis(f.outer), axis(f.inner)],
    sensed: [],
    stage: {
      instrument: f.instrument,
      axes: [inner],
      sequence: {
        name: `read ${f.sensor} at a ${f.inner.channel} level`,
        body: [
          { op: "step", channel: f.inner.channel, level: { name: symbol, unit: "V" }, duration: f.stepNs },
          { op: "measure", channel: f.sensor, duration: f.measureNs, result: f.result },
        ],
      },
      bindings: [{ symbol, axis: inner }],
      shots: f.shots,
      reduce: f.shots > 1 ? { [f.result]: "mean" } : {},
    },
    repeats: 1,
  } as SweepDefinition;
}

/** Both axes stepped on DC lines, the sensor read at every point (e.g. Coulomb diamonds: gate × bias). */
export function dcSweep(f: DcSweepForm): SweepDefinition {
  const errors = [...checkAxis(f.outer), ...checkAxis(f.inner)];
  if (axisName(f.outer) === axisName(f.inner)) errors.push("outer and inner axes need different names");
  if (!f.sensor) errors.push("a DC sweep needs a sensor channel");
  if (errors.length) throw new Error(errors.join("; "));
  return {
    name: f.name || "sweep",
    axes: [axis(f.outer), axis(f.inner)],
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
