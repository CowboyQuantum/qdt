// The Script widget, a placeholder (ADR 0059): a measurement script as text beside the API it may call,
// and a "stage" button that only validates (calls outside the allowed list, unbalanced brackets or
// quotes) and reports. Nothing here runs anything; a server-side sandbox that executes a staged script
// is its own ADR (Step 6b open decision), and until then the widget says so in its report.
import { h } from "../workspace/dom";
import { safeStorage } from "../workspace/layout";
import type { Widget } from "../workspace/widget";

/** The calls a measurement script may make, as data: the panel beside the editor and the lint's allow-list. */
export const ALLOWED_API: readonly { name: string; signature: string; doc: string }[] = [
  { name: "sweep", signature: "qdt.sweep(axes=[(channel, start, stop, num), ...], stage=..., shots=...)", doc: "a SweepDefinition, the same object the Sweep widget builds" },
  { name: "levels", signature: "qdt.levels({channel: value, ...})", doc: "hold an operating point for what follows (ADR 0053)" },
  { name: "run", signature: "qdt.run(sweep)", doc: "a Run on the server; returns its handle" },
  { name: "wait", signature: "qdt.wait(run)", doc: "block until the run ends; returns its MeasurementRecord" },
  { name: "analyze", signature: "qdt.analyze(record, method=..., **parameters)", doc: "a curated method on a record; returns its AnalysisResult" },
  { name: "device", signature: "qdt.device()", doc: "the device the stand is wired to" },
];

export const DEFAULT_SCRIPT = `# Measurement script — staged for review; nothing runs until a sandbox exists (ADR 0059).
# Only the calls listed beside this editor are available.

sweep = qdt.sweep(
    axes=[("P1", 0.03, 0.18, 48), ("P2", 0.03, 0.18, 48)],
    stage="charge_sense", shots=1,
)
run = qdt.run(sweep)
rec = qdt.wait(run)
qdt.analyze(rec, method="detect_transitions")
`;

export interface Problem {
  line: number;
  message: string;
}

const OPENERS = new Set(["(", "[", "{"]);
const CLOSER: Record<string, string> = { ")": "(", "]": "[", "}": "{" };

/** What "stage" checks: every `qdt.<name>(` is on the allow-list; a `qdt.<name>` without a call is flagged;
 * brackets (as a stack, across lines) and quotes (per line) balance, with comments and strings ignored.
 * Pure; a placeholder for a real parser, which comes with the sandbox. */
export function lintScript(text: string, allowed: readonly string[] = ALLOWED_API.map((a) => a.name)): Problem[] {
  const problems: Problem[] = [];
  const stack: { ch: string; line: number }[] = [];
  const lines = text.split("\n");
  lines.forEach((raw, i) => {
    const line = i + 1;
    const code = stripComment(raw);
    for (const m of code.matchAll(/\bqdt\.([A-Za-z_]\w*)\s*\(/g)) {
      const name = m[1]!;
      if (!allowed.includes(name)) problems.push({ line, message: `qdt.${name} is not an allowed call (allowed: ${allowed.join(", ")})` });
    }
    for (const m of code.matchAll(/\bqdt\.([A-Za-z_]\w*)\b(?!\s*\()/g)) {
      problems.push({ line, message: `qdt.${m[1]} is used without a call` });
    }
    let quote: string | null = null;
    for (const ch of code) {
      if (quote) {
        if (ch === quote) quote = null;
        continue;
      }
      if (ch === '"' || ch === "'") quote = ch;
      else if (OPENERS.has(ch)) stack.push({ ch, line });
      else if (ch in CLOSER) {
        if (stack.length && stack[stack.length - 1]!.ch === CLOSER[ch]) stack.pop();
        else problems.push({ line, message: `unexpected ${ch}` });
      }
    }
    if (quote) problems.push({ line, message: `unclosed ${quote} quote` });
  });
  for (const open of OPENERS) {
    const n = stack.filter((s) => s.ch === open).length;
    if (n) problems.push({ line: lines.length, message: `${n} unclosed ${open}` });
  }
  return problems;
}

function stripComment(line: string): string {
  let quote: string | null = null;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]!;
    if (quote) {
      if (ch === quote) quote = null;
    } else if (ch === '"' || ch === "'") quote = ch;
    else if (ch === "#") return line.slice(0, i);
  }
  return line;
}

const KEY = "flightdeck.script.v1";

export const scriptWidget: Widget = {
  id: "script",
  label: "Script",
  sub: "a measurement script, staged for review; nothing runs yet",
  single: true,
  mount(body, head, ctx) {
    let text = DEFAULT_SCRIPT;
    try {
      text = safeStorage()?.getItem(KEY) ?? DEFAULT_SCRIPT;
    } catch {
      /* no storage */
    }
    const editor = h("textarea", { name: "script", value: text, spellcheck: false, attrs: { "aria-label": "Measurement script" } });
    const report = h("div", { className: "lint", attrs: { "data-report": "", "aria-live": "polite" } });
    const stage = h("button", { type: "button", text: "stage", title: "Validate the script against the allowed API; nothing runs", attrs: { "data-stage": "" } });
    stage.addEventListener("click", () => {
      const problems = lintScript(editor.value);
      report.className = `lint${problems.length ? " bad" : ""}`;
      report.replaceChildren(
        ...(problems.length
          ? problems.map((p) => h("div", { text: `line ${p.line}: ${p.message}` }))
          : [h("div", { text: "staged: every call is allowed and the brackets balance. Execution waits for the sandbox (ADR 0059); nothing was run." })]),
      );
      ctx.bus.emit("say", { text: problems.length ? `script: ${problems.length} problem${problems.length > 1 ? "s" : ""}` : "script staged; nothing runs without a sandbox", error: problems.length > 0 });
    });
    editor.addEventListener("input", () => {
      try {
        safeStorage()?.setItem(KEY, editor.value);
      } catch {
        /* no storage */
      }
    });
    head.append(stage);
    body.append(
      h(
        "div",
        { className: "code" },
        editor,
        h(
          "div",
          { className: "api" },
          h("h4", { text: "allowed API" }),
          ...ALLOWED_API.map((a) => h("code", { text: a.signature, title: a.doc })),
          report,
        ),
      ),
    );
    return () => {
      body.replaceChildren();
      head.replaceChildren();
    };
  },
};
