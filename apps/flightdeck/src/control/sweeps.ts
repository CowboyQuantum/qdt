// Sweep builders (Step 4b): turn a small form into a `SweepDefinition` the server compiles. Three shapes:
// a *stage* sweep (outer gate stepped by its DC line, inner gate swept by pulses in the sequencer, the
// pulse sequence run per pixel), a *DC* sweep (both axes stepped, a level sensed at every point), and a
// *capture* (a time-resolved record from a WaveformSense channel, optionally at every point of a stepped
// axis; ADR 0047). The first two may drop the outer axis for a 1-D sweep. A DC or capture sweep may read
// *in the shot* instead of per point (ADR 0067): the sensor integrated by its sequencer in a one-measure
// shot, the record captured in a shot from the sequencer's marker; the compiler may then trigger the
// innermost DC axis (ADR 0066). Pure functions: no DOM, no network.
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
  /** A virtual gate (ADR 0049): other DC channels moved with this axis, volts per volt. Stepped axes only. */
  couplings?: Readonly<Record<string, number>>;
  /** How a stepped axis advances (ADR 0066): a preference; the server decides "auto" from the stand's wiring
   * and the compiled plan says what it chose. Only the innermost stepped axis of a sweep with a shot (a stage
   * sweep, or a DC or capture sweep read in the shot) can be triggered. */
  stepping?: Stepping;
}

export type Stepping = "auto" | "software" | "triggered";
/** Where a DC or capture sweep reads (ADR 0067): at every point by the host, or in the sequencer's shot. */
export type Readout = "point" | "shot";

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
  /** Where the sensor is read (ADR 0067): "point" (the default), sensed by the host at every point; "shot",
   * integrated by `shot.instrument`, the sequencer whose input it is, in a one-measure shot, `shots` times
   * per point and averaged. */
  readout?: Readout;
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
  ...(a.stepping && a.stepping !== "auto" ? { stepping: a.stepping } : {}),
});

/** A forced trigger needs a shot to play it (ADR 0066): read per point, a DC or capture sweep is stepped from
 * the host; read in the shot, only its innermost stepped axis can be triggered. */
function checkPacing(axes: readonly (AxisForm | null | undefined)[], innermost: AxisForm | null | undefined, kind: string, readout: Readout): string[] {
  return axes.flatMap((a) => {
    if (a?.stepping !== "triggered") return [];
    if (readout === "point") return [`${axisName(a)}: read per point, a ${kind} sweep is stepped from the host; read in the shot to let the sequencer trigger it`];
    return a === innermost ? [] : [`${axisName(a)}: only the innermost stepped axis can be triggered`];
  });
}

const isWholeAtLeast = (v: number, min: number) => Number.isInteger(v) && v >= min;

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
  if (f.inner.stepping && f.inner.stepping !== "auto") errors.push(`${inner}: a stage axis is swept in the sequence; stepping applies to the stepped axis`);
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
  if (built.sequence && !body.some((op) => op.op === "measure" || op.op === "capture")) errors.push("the sequence measures or captures nothing");
  // the server's rule (ADR 0060): a shot capture's scope is armed per stepped point, so a stage with a capture
  // has no pulsed axis; this sweep always pulses one, so the error shows here instead of at compile
  if (body.some((op) => op.op === "capture")) errors.push("a capture in the shot needs a stage without a pulsed axis (ADR 0060), which the Sweep widget does not build yet; the capture kind records per point");
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

/** Axes stepped on DC lines, the sensor read at every point (e.g. Coulomb diamonds: gate × bias), or in the
 * shot (ADR 0067): a one-measure shot on the sensor's sequencer, so the compiler may trigger the inner axis. */
export function dcSweep(f: DcSweepForm): SweepDefinition {
  const readout = f.readout ?? "point";
  const errors = checkAxes(f.outer, f.inner);
  errors.push(...checkPacing([f.outer, f.inner], f.inner, "DC", readout));
  if (!f.sensor) errors.push("a DC sweep needs a sensor channel");
  const axes = f.outer ? [axis(f.outer), axis(f.inner)] : [axis(f.inner)];
  errors.push(...checkResults([f.result], axes.map((a) => a.name)));
  if (f.sensor && axes.some((a) => a.channel === f.sensor)) errors.push("a channel is a stepped axis or the sensed level, not both");
  if (readout === "shot") {
    if (!f.shot?.instrument) errors.push("read in the shot, the sensor needs the sequencer whose input it is");
    else {
      if (!isWholeAtLeast(f.shot.measureNs, 1)) errors.push("the integration is a whole number of ns ≥ 1");
      if (!isWholeAtLeast(f.shot.shots, 1)) errors.push("shots must be a positive integer");
    }
    // the compiler's rule (ADR 0066): a stage with no axis of its own records once per point only where the
    // program owns the axis, so a forced host stepping cannot read in the shot
    if (f.inner.stepping === "software") errors.push(`${axisName(f.inner)}: read in the shot, the inner axis must be left to the stand or triggered; stepped from the host the measure has no axis to land on`);
  }
  if (errors.length) throw new Error(errors.join("; "));
  const common = { name: f.name || "sweep", axes, ...(f.levels?.length ? { levels: [...f.levels] } : {}), repeats: 1 };
  if (readout === "shot") {
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
  /** Records per point (a `record` dimension when > 1; in the shot, one record per shot). */
  records: number;
  /** Data variable name for the record. */
  result: string;
  /** Where the record is taken (ADR 0067): "point" (the default), the scope armed by the host at every point;
   * "shot", a capture op in a shot of `shot.instrument` from its marker, then a wait of `paceNs` before the
   * next point (the scope re-arms; ADR 0063, 0065). In the shot a record starts at its marker: start is 0. */
  readout?: Readout;
  shot?: { instrument: string; paceNs: number };
}

/** One WaveformSense channel armed per point of an optional stepped axis (ADR 0047): the shape of L2-3; or
 * captured in a shot from the sequencer's marker (ADR 0060, 0067), the shape of L2-4's staircase. */
export function captureSweep(f: CaptureForm): SweepDefinition {
  const readout = f.readout ?? "point";
  const errors = f.outer ? checkAxis(f.outer) : [];
  errors.push(...checkPacing([f.outer], f.outer, "capture", readout));
  if (f.outer && RESERVED_CAPTURE.has(axisName(f.outer))) errors.push(`"${axisName(f.outer)}" is a reserved dimension name`);
  if (!f.channel) errors.push("a capture needs a WaveformSense channel");
  if (f.outer && f.outer.channel === f.channel) errors.push("a channel is a stepped axis or the captured one, not both");
  if (!Number.isFinite(f.startS) || !Number.isFinite(f.stopS)) errors.push("start and stop must be numbers (s)");
  else if (!(f.stopS > f.startS)) errors.push("stop must be after start");
  if (!Number.isInteger(f.num) || f.num < 2) errors.push("samples must be an integer of at least 2");
  if (!Number.isInteger(f.records) || f.records < 1) errors.push("records must be a positive integer");
  const axes = f.outer ? [axis(f.outer)] : [];
  if (RESERVED_CAPTURE.has(f.result) || axes.some((a) => a.name === f.result || a.name === `${f.result}_time`)) errors.push(`"${f.result}" clashes with a dimension name`);
  const durationNs = Math.round(f.stopS * 1e9);
  if (readout === "shot") {
    if (!f.shot?.instrument) errors.push("captured in the shot, the record needs the sequencer that plays the shot");
    else if (!isWholeAtLeast(f.shot.paceNs, 0)) errors.push("the wait after each record is a whole number of ns ≥ 0");
    if (f.startS !== 0) errors.push("in the shot a record starts at its marker: start must be 0");
    if (!(durationNs >= 1)) errors.push("the window (stop) must be at least 1 ns");
  }
  if (errors.length) throw new Error(errors.join("; "));
  const common = { name: f.name || "capture", axes, ...(f.levels?.length ? { levels: [...f.levels] } : {}), sensed: [], repeats: 1 };
  if (readout === "shot") {
    const shot = f.shot!;
    // the record moves into the shot (ADR 0060): one per shot, `records` shots per point, every one kept
    return {
      ...common,
      stage: {
        instrument: shot.instrument,
        axes: [],
        sequence: {
          name: f.outer ? `capture ${f.channel} at each ${axisName(f.outer)} point` : `capture ${f.channel}`,
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

type Instrument = StandConfig["instruments"][number];
const isSequencer = (i: Instrument | undefined) => !!i && (i.capabilities as readonly string[]).includes("sequencer");

/** The sequencer that reads `sensor` in the shot (ADR 0067): the instrument whose input it is, which must be
 * a sequencer; else why the sensor can only be sensed per point. Pure. */
export function sensorSequencer(stand: StandConfig, sensor: string): { sequencer: string } | { reason: string } {
  const c = stand.channels.find((x) => x.logical === sensor);
  if (!c) return { reason: `no channel ${sensor || "(none)"} on the stand` };
  const instrument = stand.instruments.find((i) => i.id === c.instrument);
  if (!isSequencer(instrument)) return { reason: `${sensor} is read by ${c.instrument}, which is not a sequencer: it can only be sensed per point` };
  return { sequencer: c.instrument };
}

/** The sequencer that plays a capture's shot (ADR 0063, 0067): the one whose marker channel the scope names in
 * `settings.trigger_from`, else the stand's only sequencer; else why the record can only be taken per point.
 * A scope on a sequencer's own input cannot be captured in the shot yet (ADR 0060). Pure. */
export function captureSequencer(stand: StandConfig, channel: string): { sequencer: string } | { reason: string } {
  const c = stand.channels.find((x) => x.logical === channel);
  if (!c) return { reason: `no channel ${channel || "(none)"} on the stand` };
  const scope = stand.instruments.find((i) => i.id === c.instrument);
  if (isSequencer(scope)) return { reason: `${channel} is an input of the sequencer ${c.instrument}; a capture in the shot needs a scope of its own (ADR 0060)` };
  const line = scope?.settings?.trigger_from;
  if (line !== undefined && line !== "") {
    const marker = stand.channels.find((x) => x.logical === String(line));
    const sequencer = marker && stand.instruments.find((i) => i.id === marker.instrument);
    if (!isSequencer(sequencer)) return { reason: `${c.instrument}'s trigger_from ${String(line)} is not a channel of a sequencer` };
    return { sequencer: sequencer!.id };
  }
  const sequencers = stand.instruments.filter(isSequencer);
  if (sequencers.length === 1) return { sequencer: sequencers[0]!.id };
  return { reason: sequencers.length ? `the stand has ${sequencers.length} sequencers and ${c.instrument} names none in trigger_from` : "the stand has no sequencer to play the shot" };
}
