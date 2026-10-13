// Method parameter forms (Step 4b): a `MethodSpec` from GET /methods says what a curated method takes;
// these pure functions turn that into form defaults, parse what the user typed, and check it the way the
// server will, so a bad value is caught before the request.
import type { MethodSpec, ParameterSpec } from "../schema/api";

export type ParamValue = string | number | boolean;
export type ParamValues = Record<string, ParamValue>;

export function defaults(spec: MethodSpec): ParamValues {
  return Object.fromEntries((spec.parameters ?? []).map((p) => [p.name, p.default]));
}

/** Parse one form field (text or checkbox state) into the parameter's kind; throws on a bad value. */
export function parse(p: ParameterSpec, raw: string | boolean): ParamValue {
  switch (p.kind) {
    case "bool":
      return typeof raw === "boolean" ? raw : raw === "true" || raw === "on";
    case "str":
      return String(raw);
    case "int": {
      const s = String(raw).trim();
      if (!/^[+-]?\d+$/.test(s)) throw new Error(`${p.name}: expected an integer`);
      return Number(s);
    }
    case "float": {
      const n = Number(String(raw).trim());
      if (String(raw).trim() === "" || !Number.isFinite(n)) throw new Error(`${p.name}: expected a number`);
      return n;
    }
  }
}

/** Errors the server would return for `values`, as one line each; empty when all is well. */
export function check(spec: MethodSpec, values: ParamValues): string[] {
  const errors: string[] = [];
  const known = new Set((spec.parameters ?? []).map((p) => p.name));
  for (const k of Object.keys(values)) if (!known.has(k)) errors.push(`${spec.name} has no parameter ${k}`);
  for (const p of spec.parameters ?? []) {
    const v = values[p.name];
    if (v === undefined) continue;
    if ((p.kind === "int" || p.kind === "float") && typeof v === "number") {
      if (p.kind === "int" && !Number.isInteger(v)) errors.push(`${p.name}: expected an integer`);
      if (p.minimum != null && v < p.minimum) errors.push(`${p.name}: ${v} is below the minimum ${p.minimum}`);
      if (p.maximum != null && v > p.maximum) errors.push(`${p.name}: ${v} is above the maximum ${p.maximum}`);
    } else if (p.kind === "bool" && typeof v !== "boolean") errors.push(`${p.name}: expected true or false`);
    else if (p.kind === "str" && typeof v !== "string") errors.push(`${p.name}: expected text`);
  }
  return errors;
}

/** Only the values that differ from the defaults: what the request needs to carry. */
export function overrides(spec: MethodSpec, values: ParamValues): ParamValues {
  const d = defaults(spec);
  return Object.fromEntries(Object.entries(values).filter(([k, v]) => d[k] !== v));
}
