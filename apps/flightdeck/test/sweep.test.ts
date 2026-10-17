// The Sweep widget's pure parts (ADR 0056): the plan line for the strip and the next-run line from the form.
import { describe, expect, it } from "vitest";
import type { ExecutionPlan } from "../src/schema/api";
import { formSummary, pacingLines, planSummary } from "../src/widgets/sweep";

describe("planSummary", () => {
  it("names the sweep, its axes and point count, the channels and a stage program", () => {
    const plan = {
      plan_id: "abc",
      definition: { name: "stability" },
      dataset: { dims: [{ name: "P1", size: 48 }, { name: "P2", size: 32 }] },
      channels: [{}, {}, {}],
      stage_program: { ops: [] },
    } as unknown as ExecutionPlan;
    expect(planSummary(plan)).toBe("stability · P1 48 × P2 32 · 1,536 pts · 3 channels · stage program");
    const dc = { ...plan, dataset: { dims: [{ name: "bias", size: 10 }] }, stage_program: null, channels: [{}] } as unknown as ExecutionPlan;
    expect(planSummary(dc)).toBe("stability · bias 10 · 10 pts · 1 channels");
  });
});

describe("formSummary", () => {
  const form = (v: Record<string, string>) => (name: string) => v[name] ?? "";
  it("reads the kind and the axes as the form has them, with no outer axis for 1-D", () => {
    expect(formSummary(form({ name: "stability", kind: "stage", outer_channel: "P1", outer_num: "48", inner_channel: "P2_pulse", inner_num: "48" }))).toBe("stability · stage · P1 48 × P2_pulse 48");
    expect(formSummary(form({ name: "", kind: "dc", outer_channel: "", inner_channel: "bias", inner_num: "100" }))).toBe("sweep · dc · bias 100");
    expect(formSummary(form({ name: "droop", kind: "capture", outer_channel: "", capture_channel: "scope1", capture_num: "1000" }))).toBe("droop · capture · scope1 1000 samples");
  });
});

describe("pacingLines", () => {
  it("says how the server decided each axis advances (ADR 0066), one line per axis", () => {
    const plan = (pacing: unknown) => ({ plan_id: "abc", pacing }) as unknown as ExecutionPlan;
    expect(
      pacingLines(
        plan([
          { axis: "B", pacing: "software" },
          { axis: "P1", pacing: "triggered", lines: ["dac_trigger"] },
          { axis: "P2", pacing: "sequencer" },
        ]),
      ),
    ).toEqual(["B: stepped from the host", "P1: triggered on dac_trigger", "P2: swept in the sequence"]);
    expect(pacingLines(plan([{ axis: "P1", pacing: "triggered" }]))).toEqual(["P1: triggered by the sequencer itself"]);
    expect(pacingLines(plan(undefined))).toEqual([]); // a plan compiled before ADR 0066 says nothing
  });
});
