// The Levels and Virtual gates widgets' pure parts (ADR 0057, 0085): filters, sort, the set check against
// the stand's limits, editing a limit, click-to-set, and the coupling matrix a stepped axis takes.
import { describe, expect, it } from "vitest";
import type { ChannelLevel } from "../src/schema/api";
import { couplingsFor, parseMatrix } from "../src/widgets/gates";
import { checkLimit, checkSet, describeLimit, filterLevels, limitsOf, nearLimit, NO_FILTERS, setpointFor, sortLevels, withLimit } from "../src/widgets/levels";

const row = (channel: string, extra: Partial<ChannelLevel> = {}): ChannelLevel => ({ channel, instrument: "dot", quantity: "voltage", setpoint: 0, held: null, readback: null, ...extra });
const ROWS = [
  row("P2", { setpoint: 0.95, held: 0.95 }),
  row("P1", { setpoint: 0.1 }),
  row("SG", { setpoint: -0.04, held: -0.04, instrument: "qdac" }),
  row("sensor", { quantity: "current", setpoint: null, readback: 1.2e-9 }),
];
const none = new Set<string>();
const limit = (min_v: number, max_v: number) => ({ min_v, max_v });
/** P2 near the top of its limit, P1 well inside a wide one, SG without one. */
const LIMITS = new Map([
  ["P2", limit(-1, 1)],
  ["P1", limit(-1, 1)],
]);
const NOLIMITS = new Map();

describe("filterLevels", () => {
  it("ANDs across groups and ORs within; text matches channel or instrument", () => {
    expect(filterLevels(ROWS, NO_FILTERS, none, LIMITS).map((r) => r.channel)).toEqual(["P2", "P1", "SG", "sensor"]);
    expect(filterLevels(ROWS, { ...NO_FILTERS, quantities: new Set(["current"]) }, none, LIMITS).map((r) => r.channel)).toEqual(["sensor"]);
    expect(filterLevels(ROWS, { ...NO_FILTERS, instruments: new Set(["qdac", "dot"]) }, none, LIMITS)).toHaveLength(4);
    expect(filterLevels(ROWS, { ...NO_FILTERS, instruments: new Set(["qdac"]), text: "p" }, none, LIMITS)).toHaveLength(0);
    expect(filterLevels(ROWS, { ...NO_FILTERS, text: "QDAC" }, none, LIMITS).map((r) => r.channel)).toEqual(["SG"]);
    expect(filterLevels(ROWS, { ...NO_FILTERS, pinnedOnly: true }, new Set(["P1"]), LIMITS).map((r) => r.channel)).toEqual(["P1"]);
    expect(filterLevels(ROWS, { ...NO_FILTERS, nearLimit: true }, none, LIMITS).map((r) => r.channel)).toEqual(["P2"]);
    expect(filterLevels(ROWS, { ...NO_FILTERS, nearLimit: true }, none, new Map([["P1", limit(0, 0.1)], ["P2", limit(0, 9)]])).map((r) => r.channel)).toEqual(["P1"]);
    expect(filterLevels(ROWS, { ...NO_FILTERS, nearLimit: true }, none, NOLIMITS)).toEqual([]); // no limit, never near one
  });
});

describe("nearLimit", () => {
  it("is within a tenth of the limit's span of either end, never without a limit or a setpoint", () => {
    expect(nearLimit({ setpoint: 0.8 }, limit(-1, 1))).toBe(true);
    expect(nearLimit({ setpoint: -0.95 }, limit(-1, 1))).toBe(true);
    expect(nearLimit({ setpoint: 0.79 }, limit(-1, 1))).toBe(false);
    expect(nearLimit({ setpoint: 0.21 }, limit(0.2, 1.2))).toBe(true); // an asymmetric limit
    expect(nearLimit({ setpoint: 0.5 }, undefined)).toBe(false);
    expect(nearLimit({ setpoint: null }, limit(-1, 1))).toBe(false);
  });
});

describe("limits", () => {
  it("reads a stand state's limits by channel and describes one", () => {
    const m = limitsOf({ limits: [{ channel: "P1", min_v: -0.5, max_v: 0.25 }] });
    expect(describeLimit(m.get("P1"), "V")).toBe("[-0.5, 0.25] V");
    expect(describeLimit(m.get("P2"), "V")).toBe("none");
    expect(limitsOf(null).size).toBe(0);
  });

  it("sets or removes one channel's limit and keeps every other, as the server takes them", () => {
    const now = [
      { channel: "SG", min_v: 0, max_v: 0.5, schema_version: 1 },
      { channel: "P1", min_v: -1, max_v: 1 },
    ];
    expect(withLimit(now, "P2", { min_v: 0, max_v: 0.2 })).toEqual([
      { channel: "P1", min_v: -1, max_v: 1 },
      { channel: "P2", min_v: 0, max_v: 0.2 },
      { channel: "SG", min_v: 0, max_v: 0.5 },
    ]);
    expect(withLimit(now, "P1", { min_v: 0, max_v: 0.1 }).find((l) => l.channel === "P1")).toEqual({ channel: "P1", min_v: 0, max_v: 0.1 });
    expect(withLimit(now, "SG", null)).toEqual([{ channel: "P1", min_v: -1, max_v: 1 }]);
  });

  it("refuses a typed limit without two numbers or with its ends crossed", () => {
    expect(checkLimit("-0.5", "0.5")).toBeNull();
    expect(checkLimit("0.2", "0.2")).toBeNull();
    expect(checkLimit("", "1")).toBe("give both ends as numbers");
    expect(checkLimit("a", "1")).toBe("give both ends as numbers");
    expect(checkLimit("1", "0")).toBe("the highest level is below the lowest");
  });
});

describe("sortLevels", () => {
  it("puts pinned rows first, sorts by the key in the direction, nulls last, and does not mutate", () => {
    expect(sortLevels(ROWS, "channel", 1, none).map((r) => r.channel)).toEqual(["P1", "P2", "sensor", "SG"]); // locale order, not ASCII
    expect(sortLevels(ROWS, "channel", -1, none).map((r) => r.channel)).toEqual(["SG", "sensor", "P2", "P1"]);
    expect(sortLevels(ROWS, "setpoint", 1, none).map((r) => r.channel)).toEqual(["SG", "P1", "P2", "sensor"]);
    expect(sortLevels(ROWS, "setpoint", -1, none).map((r) => r.channel)).toEqual(["P2", "P1", "SG", "sensor"]);
    expect(sortLevels(ROWS, "setpoint", 1, new Set(["sensor"])).map((r) => r.channel)).toEqual(["sensor", "SG", "P1", "P2"]);
    expect(ROWS[0]!.channel).toBe("P2");
  });
});

describe("checkSet", () => {
  it("refuses a non-number and a level beyond the channel's limit; without a limit only the server checks", () => {
    expect(checkSet("0.5", limit(-1, 1))).toBeNull();
    expect(checkSet("-1", limit(-1, 1))).toBeNull();
    expect(checkSet("1.01", limit(-1, 1))).toBe("beyond the stand's limit [-1, 1] V");
    expect(checkSet("0.1", limit(0.2, 1.2))).toBe("beyond the stand's limit [0.2, 1.2] V");
    expect(checkSet("50", undefined)).toBeNull();
    expect(checkSet("", limit(-1, 1))).toBe("not a number");
    expect(checkSet("abc", undefined)).toBe("not a number");
  });
});

describe("setpointFor", () => {
  it("turns a clicked point into levels for the stand's DC channels and names what it skips", () => {
    const dc = [{ logical: "P1" }, { logical: "P2" }];
    const r = setpointFor(
      [
        { name: "P2", value: 0.1 },
        { name: "P1", value: 0.05 },
        { name: "V_sd", value: 0.001 },
      ],
      dc,
    );
    expect(r.levels).toEqual([
      { channel: "P2", value: 0.1 },
      { channel: "P1", value: 0.05 },
    ]);
    expect(r.skipped).toEqual(["V_sd"]);
    expect(setpointFor([{ name: "P1", value: NaN }], dc).skipped).toEqual(["P1"]);
  });
});

describe("virtual gates", () => {
  it("an axis takes its row without the diagonal and without zeros", () => {
    const m = { P1: { P1: 1, P2: -0.18, B1: 0, SG: 0.05 }, P2: { P1: NaN } };
    expect(couplingsFor(m, "P1")).toEqual({ P2: -0.18, SG: 0.05 });
    expect(couplingsFor(m, "P2")).toEqual({});
    expect(couplingsFor(m, "B1")).toEqual({});
  });

  it("parses a stored matrix over the stand's channels only, dropping junk", () => {
    const chans = ["P1", "P2", "SG"];
    expect(parseMatrix(null, chans)).toEqual({});
    expect(parseMatrix("{nope", chans)).toEqual({});
    expect(parseMatrix(JSON.stringify({ P1: { P2: -0.2, P1: 1, X: 3, SG: "a" }, Y: { P1: 1 }, P2: { SG: 0 } }), chans)).toEqual({ P1: { P2: -0.2 } });
  });
});
