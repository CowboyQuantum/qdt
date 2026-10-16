// Pulse-sequence editor model (Step 4b): rows of text a form edits → a `PulseSequence` and the stage's
// `SymbolBinding`s. A form over the schema, not a timeline (ADR 0035): one row per primitive in time
// order, one text cell per field. A value cell holds a number, a symbol name, or an affine of one
// (`v_P2 + 0.002`, `-v_P2`, `0.5*v_P2 - 1e-3`, ADR 0037); a symbol is bound below the table to an axis or
// a constant. A `difference` row subtracts two earlier measures per shot (chopped readout, ADR 0037). A
// `capture` row opens a scope window in the shot (ADR 0060). Pure functions: no DOM, no network. They refuse what the server's
// validators would refuse (PulseSequence, SequencerStage), so errors show while typing.
import type { Affine, Call, ChannelMap, PulseSequence, Symbol as PulseSymbol, SymbolBinding } from "../schema/api";

// Every primitive of the generated schema except `call`: a primitive added to PulseSequence by ADR
// appears here by itself, and the coverage check below fails tsc until the form has its columns.
type Primitive = Exclude<PulseSequence["body"][number], Call>;
export type OpKind = NonNullable<Primitive["op"]>;
type OpOf<K extends OpKind> = Extract<Primitive, { op?: K }>;
type FieldOf<K extends OpKind> = Exclude<keyof OpOf<K>, "op" | "schema_version">;

/** The editable fields of each primitive, in column order. `call`/segments are not edited here. */
export const OP_FIELDS = {
  step: ["channel", "level", "duration"],
  ramp: ["channel", "start", "stop", "duration"],
  wait: ["duration"],
  drive: ["channel", "frequency", "phase", "amplitude", "duration"],
  measure: ["channel", "duration", "result"],
  capture: ["channel", "duration", "num", "result"],
  difference: ["result", "a", "b"],
} as const satisfies { [K in OpKind]: readonly FieldOf<K>[] };

// Compile-time check against the generated types: every required field of every primitive has a column.
type RequiredOf<T> = { [P in keyof T]-?: undefined extends T[P] ? never : P }[keyof T];
type Uncovered = { [K in OpKind]: Exclude<RequiredOf<OpOf<K>>, (typeof OP_FIELDS)[K][number]> }[OpKind];
const _allCovered: [Uncovered] extends [never] ? true : Uncovered = true;
void _allCovered;

export type FieldName = (typeof OP_FIELDS)[OpKind][number];
export const OP_KINDS = Object.keys(OP_FIELDS) as OpKind[];

/** One primitive as the form holds it: field → the text typed. Missing optional fields use defaults. */
export interface OpRow {
  op: OpKind;
  fields: Partial<Record<FieldName, string>>;
}

/** What a symbol takes, as typed: an axis name, or a number (a constant in the symbol's unit). */
export interface BindingRow {
  symbol: string;
  target: string;
}

const VALUE_FIELDS = new Set<FieldName>(["level", "start", "stop", "frequency", "phase", "amplitude"]);
const LEVEL_FIELDS = new Set<FieldName>(["level", "start", "stop", "amplitude"]);
const IDENT = /^[A-Za-z_][A-Za-z0-9_]*$/;
const QUANTITY_UNIT: Record<ChannelMap["quantity"], string> = { voltage: "V", current: "A" };
const DEFAULTS: Partial<Record<FieldName, string>> = { phase: "0" };

/** Unit of a field's value: the channel's quantity unit for levels, else fixed by the field. */
export function fieldUnit(field: FieldName, channel: ChannelMap | undefined): string {
  if (field === "duration") return "ns";
  if (field === "frequency") return "Hz";
  if (field === "phase") return "rad";
  if (LEVEL_FIELDS.has(field)) return channel ? QUANTITY_UNIT[channel.quantity] : "";
  return "";
}

const NUM = String.raw`(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?`;
const AFFINE = new RegExp(String.raw`^(?:([+-]?${NUM})\s*\*\s*|(-)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:([+-])\s*(${NUM}))?$`);

/** A value cell: a finite number, a symbol name, or `[scale *] symbol [± offset]` (also `-symbol`).
 * A bare name stays a `Symbol`, so sequences without offsets serialize exactly as before. */
export function parseValue(text: string, unit: string): number | PulseSymbol | Affine {
  const t = text.trim();
  if (t !== "" && Number.isFinite(Number(t))) return Number(t);
  const m = AFFINE.exec(t);
  if (!m) throw new Error(t === "" ? "empty" : `"${t}" is neither a number, a symbol name, nor "symbol + offset"`);
  const [, scaleText, minus, name, sign, offsetText] = m;
  const symbol: PulseSymbol = { name: name!, unit };
  const scale = scaleText !== undefined ? Number(scaleText) : minus ? -1 : 1;
  const offset = offsetText !== undefined ? (sign === "-" ? -1 : 1) * Number(offsetText) : 0;
  if (scale === 1 && offset === 0) return symbol;
  return { symbol, ...(scale !== 1 ? { scale } : {}), ...(offset !== 0 ? { offset } : {}) };
}

/** The symbol a value depends on (bare or inside an affine), if any. */
export function symbolOf(v: number | PulseSymbol | Affine): PulseSymbol | null {
  if (typeof v === "number") return null;
  return "symbol" in v ? v.symbol : v;
}

/** The symbol name a cell's text refers to, if it parses as one (for showing its binding). */
export function symbolInText(text: string): string | null {
  try {
    return symbolOf(parseValue(text, ""))?.name ?? null;
  } catch {
    return null;
  }
}

export interface SequenceBuild {
  sequence: PulseSequence | null;
  /** Symbol name → unit, in first-use order. */
  symbols: Map<string, string>;
  errors: string[];
}

/** Rows → a `PulseSequence` against the stand's channels; `sequence` is null when there are errors. */
export function buildSequence(name: string, rows: readonly OpRow[], channels: readonly ChannelMap[]): SequenceBuild {
  const byName = new Map(channels.map((c) => [c.logical, c]));
  const errors: string[] = [];
  const symbols = new Map<string, string>();
  const results = new Set<string>();
  const measured = new Set<string>(); // measure results so far, in time order
  const body: Primitive[] = [];
  if (!rows.length) errors.push("the sequence needs at least one op");
  rows.forEach((row, i) => {
    const where = `op ${i + 1} (${row.op})`;
    const text = (f: FieldName) => row.fields[f] ?? DEFAULTS[f] ?? "";
    const channel = OP_FIELDS[row.op].includes("channel" as never) ? byName.get(text("channel")) : undefined;
    const op: Record<string, unknown> = { op: row.op };
    for (const field of OP_FIELDS[row.op] as readonly FieldName[]) {
      const t = text(field);
      if (field === "channel") {
        if (!channel) errors.push(`${where}: ${t ? `unknown channel "${t}"` : "needs a channel"}`);
        else if (row.op === "measure" && channel.quantity !== "current") errors.push(`${where}: measures a current channel, not "${t}"`);
        else if (row.op === "capture" && channel.quantity !== "voltage") errors.push(`${where}: captures a voltage (scope) channel, not "${t}"`);
        else if (row.op !== "measure" && row.op !== "capture" && channel.quantity !== "voltage") errors.push(`${where}: drives a voltage channel, not "${t}"`);
        op.channel = t;
      } else if (field === "result") {
        if (!IDENT.test(t)) errors.push(`${where}: result needs a name`);
        else if (results.has(t)) errors.push(`${where}: result "${t}" is already a result in this shot`);
        results.add(t);
        op.result = t;
      } else if (field === "num") {
        const n = Number(t.trim());
        if (t.trim() === "" || !Number.isInteger(n) || n < 2) errors.push(`${where}: num is a whole number of samples ≥ 2`);
        op.num = n;
      } else if (field === "a" || field === "b") {
        if (!measured.has(t)) errors.push(`${where}: ${field} must name a measure earlier in the shot${measured.size ? ` (${[...measured].join(", ")})` : ""}`);
        else if (field === "b" && t === text("a")) errors.push(`${where}: subtracts "${t}" from itself`);
        op[field] = t;
      } else {
        const unit = fieldUnit(field, channel);
        let v: number | PulseSymbol | Affine;
        try {
          v = parseValue(t, unit);
        } catch (e) {
          errors.push(`${where}: ${field} ${(e as Error).message}`);
          continue;
        }
        if (typeof v === "number" && field === "duration" && (!Number.isInteger(v) || v < 0)) {
          errors.push(`${where}: duration is a whole number of ns ≥ 0`);
        }
        if (field === "duration" && typeof v !== "number" && "symbol" in v) {
          errors.push(`${where}: a duration takes a number or a bare symbol, not "${t}"`);
        }
        if (row.op === "capture" && field === "duration" && (typeof v !== "number" || v < 1)) {
          errors.push(`${where}: a capture window is a fixed number of ns ≥ 1, never a symbol (ADR 0060)`);
        }
        const sym = symbolOf(v);
        if (sym) {
          const had = symbols.get(sym.name);
          if (had !== undefined && had !== unit) errors.push(`${where}: symbol "${sym.name}" is used in ${had || "no unit"} and ${unit || "no unit"}`);
          else symbols.set(sym.name, unit);
        }
        if (VALUE_FIELDS.has(field) || field === "duration") op[field] = v;
      }
    }
    if (row.op === "measure" && typeof op.result === "string") measured.add(op.result);
    body.push(op as unknown as Primitive);
  });
  if (!name.trim()) errors.push("the sequence needs a name");
  const sequence = errors.length ? null : ({ name: name.trim(), body } as PulseSequence);
  return { sequence, symbols, errors };
}

/** Bindings for `symbols`, keeping what the user had typed; a new `v_<axis>` symbol defaults to that axis. */
export function syncBindings(symbols: Iterable<string>, previous: readonly BindingRow[], axes: readonly string[]): BindingRow[] {
  const had = new Map(previous.map((b) => [b.symbol, b.target]));
  return [...symbols].map((symbol) => {
    const old = had.get(symbol);
    if (old !== undefined) return { symbol, target: old };
    const axis = axes.find((a) => `v_${a}` === symbol);
    return { symbol, target: axis ?? "" };
  });
}

/** Binding rows → `SymbolBinding`s: an axis name binds to that axis, a number to a constant. */
export function buildBindings(rows: readonly BindingRow[], axes: readonly string[]): { bindings: SymbolBinding[]; errors: string[] } {
  const errors: string[] = [];
  const bindings: SymbolBinding[] = [];
  for (const { symbol, target } of rows) {
    const t = target.trim();
    if (axes.includes(t)) bindings.push({ symbol, axis: t });
    else if (t !== "" && Number.isFinite(Number(t))) bindings.push({ symbol, value: Number(t) });
    else errors.push(`symbol "${symbol}" needs an axis (${axes.join(", ") || "none"}) or a number`);
  }
  return { bindings, errors };
}

/** Measure result names in row order (what a difference row may subtract). */
export function measuredResults(rows: readonly OpRow[]): string[] {
  return rows.flatMap((r) => (r.op === "measure" && r.fields.result ? [r.fields.result] : []));
}

/** Mirrors SweepDefinition's rule: each stage axis is swept inside the sequence, so some symbol bound
 * to it must appear in a level. Typing a number over the template's `v_<axis>` breaks this. */
export function unusedStageAxes(bindings: readonly SymbolBinding[], stageAxes: readonly string[]): string[] {
  return stageAxes
    .filter((a) => !bindings.some((b) => b.axis === a))
    .map((a) => `the inner axis ${a} is not used: put v_${a} (or another symbol bound to ${a}) in a level`);
}

/** The one-step template: hold `channel` at the axis symbol, then measure. Stage sweeps start here. */
export function templateRows(t: { channel: string; symbol: string; sensor: string; stepNs: number; measureNs: number; result: string }): OpRow[] {
  return [
    { op: "step", fields: { channel: t.channel, level: t.symbol, duration: String(t.stepNs) } },
    { op: "measure", fields: { channel: t.sensor, duration: String(t.measureNs), result: t.result } },
  ];
}

/** A fresh row of `op`, prefilled from the stand (and, for a difference, the last two measure results)
 * so it is valid as soon as it is added. */
export function newRow(op: OpKind, channels: readonly ChannelMap[], measured: readonly string[] = []): OpRow {
  // a sequencer pulses its `_pulse` lines (the stand convention, `standChannels`); any voltage line otherwise
  const voltages = channels.filter((c) => c.quantity === "voltage");
  const voltage = (voltages.find((c) => c.logical.endsWith("_pulse")) ?? voltages[0])?.logical ?? "";
  const sensor = channels.find((c) => c.quantity === "current")?.logical ?? "";
  switch (op) {
    case "step":
      return { op, fields: { channel: voltage, level: "0", duration: "100" } };
    case "ramp":
      return { op, fields: { channel: voltage, start: "0", stop: "0", duration: "100" } };
    case "wait":
      return { op, fields: { duration: "100" } };
    case "drive":
      return { op, fields: { channel: voltage, frequency: "1e9", phase: "0", amplitude: "0", duration: "100" } };
    case "measure":
      return { op, fields: { channel: sensor, duration: "1000", result: "I_sensor" } };
    case "capture": {
      // a scope channel by the stand convention, else any voltage line
      const scope = (voltages.find((c) => /scope/i.test(c.logical)) ?? voltages[0])?.logical ?? "";
      return { op, fields: { channel: scope, duration: "1000000", num: "200", result: "trace" } };
    }
    case "difference":
      return { op, fields: { result: "dI", a: measured.at(-2) ?? "", b: measured.at(-1) ?? "" } };
  }
}

/** Move row `i` by `delta` (−1 up, +1 down); a copy, unchanged at the ends. */
export function moveRow<T>(rows: readonly T[], i: number, delta: number): T[] {
  const j = i + delta;
  const out = [...rows];
  if (j < 0 || j >= rows.length) return out;
  [out[i], out[j]] = [out[j]!, out[i]!];
  return out;
}
