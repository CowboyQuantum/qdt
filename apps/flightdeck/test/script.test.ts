// The Script widget's lint (ADR 0059): the allow-list and the bracket/quote balance, nothing more.
import { describe, expect, it } from "vitest";
import { ALLOWED_API, DEFAULT_SCRIPT, lintScript } from "../src/widgets/script";

describe("lintScript", () => {
  it("passes the default script and the allowed calls", () => {
    expect(lintScript(DEFAULT_SCRIPT)).toEqual([]);
    expect(ALLOWED_API.map((a) => a.name)).toEqual(["sweep", "levels", "run", "wait", "analyze", "device"]);
    expect(lintScript("x = qdt.device()\nqdt.levels({'P1': 0.1})")).toEqual([]);
  });

  it("names a call outside the allow-list, with its line", () => {
    const p = lintScript("a = qdt.sweep(axes=[])\nqdt.format_disk()\n");
    expect(p).toHaveLength(1);
    expect(p[0]!.line).toBe(2);
    expect(p[0]!.message).toMatch(/qdt\.format_disk is not an allowed call/);
    expect(lintScript("qdt.run")[0]!.message).toMatch(/used without a call/);
  });

  it("checks brackets and quotes across lines, ignoring comments and strings", () => {
    expect(lintScript("qdt.sweep(\n  axes=[(1, 2)],\n)")).toEqual([]);
    expect(lintScript("qdt.sweep(axes=[1, 2)")).toEqual([
      { line: 1, message: "unexpected )" },
      { line: 1, message: "1 unclosed (" },
      { line: 1, message: "1 unclosed [" },
    ]);
    expect(lintScript("# qdt.nope( is only a comment )\nx = 'a ( string'")).toEqual([]);
    expect(lintScript("x = 'unterminated")).toEqual([{ line: 1, message: "unclosed ' quote" }]);
    expect(lintScript("qdt.run(x))")).toEqual([{ line: 1, message: "unexpected )" }]);
  });
});
