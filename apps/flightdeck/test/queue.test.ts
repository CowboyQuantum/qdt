// The Queue widget's pure parts (ADR 0086) and the Virtual gates widget's draft check (ADR 0085): what
// one step up or down means, what a row says, and when the matrix being edited differs from the stand's.
import { describe, expect, it } from "vitest";
import type { QueuedRun } from "../src/schema/api";
import { sameMatrix } from "../src/widgets/gates";
import { describeEntry, queueSummary, stepTarget } from "../src/widgets/queue";

const entry = (id: string, extra: Partial<QueuedRun> = {}): QueuedRun =>
  ({ queue_id: id, stand_id: "s", state: "queued", position: 0, submitted_by: "local", submitted_at: "2026-10-27T12:00:00Z", request: { definition: { name: id } }, ...extra }) as QueuedRun;

const QUEUE = {
  paused: false,
  entries: [
    entry("r", { state: "running", position: null, run_id: "ab".repeat(16) }),
    entry("a", { position: 0 }),
    entry("b", { position: 1 }),
    entry("c", { position: 2 }),
    entry("d", { state: "done", position: null, record_id: "cd".repeat(16) }),
  ],
};

describe("stepTarget", () => {
  it("moves a waiting entry one place among the waiting ones, and nowhere at either end", () => {
    expect(stepTarget(QUEUE, "b", -1)).toBe(0);
    expect(stepTarget(QUEUE, "b", 1)).toBe(2);
    expect(stepTarget(QUEUE, "a", -1)).toBeNull();
    expect(stepTarget(QUEUE, "c", 1)).toBeNull();
    expect(stepTarget(QUEUE, "r", 1)).toBeNull(); // running: it has left the queue
    expect(stepTarget(QUEUE, "d", -1)).toBeNull();
    expect(stepTarget(QUEUE, "nope", 1)).toBeNull();
  });
});

describe("describeEntry and queueSummary", () => {
  it("say what each entry is and became, and what the queue holds", () => {
    expect(describeEntry(entry("a", { position: 0 }))).toBe("runs next");
    expect(describeEntry(entry("c", { position: 2 }))).toBe("waiting, 2 ahead");
    expect(describeEntry(entry("r", { state: "running", position: null, run_id: "ab".repeat(16) }))).toBe("running as run abababab");
    expect(describeEntry(entry("r", { state: "running", position: null }))).toBe("starting");
    expect(describeEntry(entry("d", { state: "done", position: null, record_id: "cd".repeat(16) }))).toBe("done → record cdcdcdcd");
    expect(describeEntry(entry("f", { state: "failed", position: null, message: "not started: P1 would reach 0.3" }))).toBe("failed: not started: P1 would reach 0.3");
    expect(queueSummary(QUEUE)).toBe("1 running, 3 waiting");
    expect(queueSummary({ paused: true, entries: [entry("a")] })).toBe("paused · 1 waiting");
  });
});

describe("sameMatrix", () => {
  it("compares couplings with zeros and the diagonal implicit", () => {
    expect(sameMatrix({}, {})).toBe(true);
    expect(sameMatrix({ P1: { P2: -0.2 } }, { P1: { P2: -0.2, SG: 0 }, P2: {} })).toBe(true);
    expect(sameMatrix({ P1: { P2: -0.2 } }, { P1: { P2: -0.21 } })).toBe(false);
    expect(sameMatrix({ P1: { P2: -0.2 } }, {})).toBe(false);
    expect(sameMatrix({ P1: { P1: 1 } }, {})).toBe(true);
  });
});
