// The Levels and Virtual gates widgets' pure parts (ADR 0057): filters, sort, the set check, click-to-set,
// and the coupling matrix a stepped axis takes.
import { describe, expect, it } from "vitest";
import type { ChannelLevel } from "../src/schema/api";
import { couplingsFor, parseMatrix } from "../src/widgets/gates";
import { checkSet, filterLevels, nearLimit, NO_FILTERS, setpointFor, sortLevels } from "../src/widgets/levels";

const row = (channel: string, extra: Partial<ChannelLevel> = {}): ChannelLevel => ({ channel, instrument: "dot", quantity: "voltage", setpoint: 0, held: null, readback: null, ...extra });
const ROWS = [
  row("P2", { setpoint: 0.95, held: 0.95 }),
  row("P1", { setpoint: 0.1 }),
  row("SG", { setpoint: -0.04, held: -0.04, instrument: "qdac" }),
  row("sensor", { quantity: "current", setpoint: null, readback: 1.2e-9 }),
];
const none = new Set<string>();

describe("filterLevels", () => {
  it("ANDs across groups and ORs within; text matches channel or instrument", () => {
    expect(filterLevels(ROWS, NO_FILTERS, none, 1).map((r) => r.channel)).toEqual(["P2", "P1", "SG", "sensor"]);
    expect(filterLevels(ROWS, { ...NO_FILTERS, quantities: new Set(["current"]) }, none, 1).map((r) => r.channel)).toEqual(["sensor"]);
    expect(filterLevels(ROWS, { ...NO_FILTERS, instruments: new Set(["qdac", "dot"]) }, none, 1)).toHaveLength(4);
    expect(filterLevels(ROWS, { ...NO_FILTERS, instruments: new Set(["qdac"]), text: "p" }, none, 1)).toHaveLength(0);
    expect(filterLevels(ROWS, { ...NO_FILTERS, text: "QDAC" }, none, 1).map((r) => r.channel)).toEqual(["SG"]);
    expect(filterLevels(ROWS, { ...NO_FILTERS, pinnedOnly: true }, new Set(["P1"]), 1).map((r) => r.channel)).toEqual(["P1"]);
    expect(filterLevels(ROWS, { ...NO_FILTERS, nearLimit: true }, none, 1).map((r) => r.channel)).toEqual(["P2"]);
    expect(filterLevels(ROWS, { ...NO_FILTERS, nearLimit: true }, none, 0.1).map((r) => r.channel)).toEqual(["P2", "P1"]);
  });
});

describe("nearLimit", () => {
  it("is within 90 % of the limit, either sign, never for a null setpoint", () => {
    expect(nearLimit({ setpoint: 0.9 }, 1)).toBe(true);
    expect(nearLimit({ setpoint: -0.95 }, 1)).toBe(true);
    expect(nearLimit({ setpoint: 0.89 }, 1)).toBe(false);
    expect(nearLimit({ setpoint: null }, 1)).toBe(false);
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
  it("refuses a non-number and a level beyond the limit", () => {
    expect(checkSet("0.5", 1)).toBeNull();
    expect(checkSet("-1", 1)).toBeNull();
    expect(checkSet("1.01", 1)).toBe("beyond the limit of ±1");
    expect(checkSet("", 1)).toBe("not a number");
    expect(checkSet("abc", 1)).toBe("not a number");
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
