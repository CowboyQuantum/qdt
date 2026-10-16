// The History widget's pure parts (ADR 0055): the search filter and the "shown in" lookup.
import { describe, expect, it } from "vitest";
import type { MeasurementRecord } from "../src/schema/api";
import { filterRecords, shownIn } from "../src/widgets/history";

const rec = (id: string, name: string, started: string, extra: Partial<MeasurementRecord> = {}): MeasurementRecord =>
  ({ record_id: id, definition_name: name, started_at: started, device_id: "sim-double-dot", outcome: "completed", ...extra }) as MeasurementRecord;

const RECORDS = [
  rec("a1", "stability", "2026-10-15T10:00:00"),
  rec("b2", "droop", "2026-10-15T11:00:00", { outcome: "aborted" }),
  rec("c3", "stability", "2026-10-15T09:00:00", { campaign: "cooldown 11" }),
];

describe("filterRecords", () => {
  it("returns newest first and matches name, campaign, outcome and id, case-insensitively", () => {
    expect(filterRecords(RECORDS, "").map((r) => r.record_id)).toEqual(["b2", "a1", "c3"]);
    expect(filterRecords(RECORDS, "STAB").map((r) => r.record_id)).toEqual(["a1", "c3"]);
    expect(filterRecords(RECORDS, "cooldown").map((r) => r.record_id)).toEqual(["c3"]);
    expect(filterRecords(RECORDS, "aborted").map((r) => r.record_id)).toEqual(["b2"]);
    expect(filterRecords(RECORDS, "b2")).toHaveLength(1);
    expect(filterRecords(RECORDS, "nothing")).toEqual([]);
    expect(RECORDS[0]!.record_id).toBe("a1"); // the input is untouched
  });
});

describe("shownIn", () => {
  it("names the plot panes whose announced registry ref is the record, in pane order", () => {
    const panes = [
      { id: "p1", label: "Plot 1" },
      { id: "p2", label: "Plot 2" },
      { id: "p3", label: "Plot 3" },
    ];
    const views = new Map<string, string | null>([
      ["p1", null],
      ["p2", "a1"],
      ["p3", "a1"],
    ]);
    expect(shownIn("a1", views, panes)).toEqual(["Plot 2", "Plot 3"]);
    expect(shownIn("b2", views, panes)).toEqual([]);
    expect(shownIn("a1", views, [])).toEqual([]);
  });
});
