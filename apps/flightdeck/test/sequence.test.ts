import { describe, expect, it } from "vitest";
import {
  buildBindings,
  buildSequence,
  fieldUnit,
  moveRow,
  newRow,
  OP_KINDS,
  parseValue,
  syncBindings,
  templateRows,
  type OpRow,
} from "../src/control/sequence";
import { dcSweep, stageSweep } from "../src/control/sweeps";
import type { ChannelMap } from "../src/schema/api";

const channels: ChannelMap[] = [
  { logical: "P1", instrument: "dot", channel: "P1", quantity: "voltage" },
  { logical: "P2_pulse", instrument: "dot", channel: "P2_pulse", quantity: "voltage" },
  { logical: "bias_pulse", instrument: "dot", channel: "bias_pulse", quantity: "voltage" },
  { logical: "sensor", instrument: "dot", channel: "sensor", quantity: "current" },
];

const template = templateRows({ channel: "P2_pulse", symbol: "v_P2", sensor: "sensor", stepNs: 500, measureNs: 2000, result: "I_sensor" });

describe("value cells", () => {
  it("reads a number or a symbol name, and nothing else", () => {
    expect(parseValue(" 0.12 ", "V")).toBe(0.12);
    expect(parseValue("-1e-3", "V")).toBe(-1e-3);
    expect(parseValue("v_P2", "V")).toEqual({ name: "v_P2", unit: "V" });
    expect(() => parseValue("", "V")).toThrow(/empty/);
    expect(() => parseValue("2 V", "V")).toThrow(/neither/);
  });

  it("takes the unit from the channel for levels and from the field otherwise", () => {
    expect(fieldUnit("level", channels[0])).toBe("V");
    expect(fieldUnit("amplitude", channels[3])).toBe("A");
    expect(fieldUnit("duration", channels[0])).toBe("ns");
    expect(fieldUnit("frequency", undefined)).toBe("Hz");
    expect(fieldUnit("phase", undefined)).toBe("rad");
  });
});

describe("sequence rows → PulseSequence", () => {
  it("builds the one-step template the stage sweep used to hard-code", () => {
    const b = buildSequence("read", template, channels);
    expect(b.errors).toEqual([]);
    expect(b.sequence).toEqual({
      name: "read",
      body: [
        { op: "step", channel: "P2_pulse", level: { name: "v_P2", unit: "V" }, duration: 500 },
        { op: "measure", channel: "sensor", duration: 2000, result: "I_sensor" },
      ],
    });
    expect([...b.symbols]).toEqual([["v_P2", "V"]]);
  });

  it("builds every primitive the form offers, prefilled valid", () => {
    const rows = OP_KINDS.map((k) => newRow(k, channels));
    rows[4] = { op: "measure", fields: { ...rows[4]!.fields, result: "I_a" } };
    const b = buildSequence("all", rows, channels);
    expect(b.errors).toEqual([]);
    expect(b.sequence!.body.map((op) => op.op)).toEqual(["step", "ramp", "wait", "drive", "measure"]);
    expect(b.sequence!.body[3]).toMatchObject({ frequency: 1e9, phase: 0 });
  });

  it("builds a pulsed readout: ramp in, wait, two measures, symbols in level and duration", () => {
    const rows: OpRow[] = [
      { op: "ramp", fields: { channel: "P2_pulse", start: "0", stop: "v_P2", duration: "t_ramp" } },
      { op: "wait", fields: { duration: "200" } },
      { op: "measure", fields: { channel: "sensor", duration: "1000", result: "I_before" } },
      { op: "step", fields: { channel: "bias_pulse", level: "v_kick", duration: "100" } },
      { op: "measure", fields: { channel: "sensor", duration: "1000", result: "I_after" } },
    ];
    const b = buildSequence("pulsed", rows, channels);
    expect(b.errors).toEqual([]);
    expect([...b.symbols]).toEqual([
      ["v_P2", "V"],
      ["t_ramp", "ns"],
      ["v_kick", "V"],
    ]);
  });

  it("refuses what PulseSequence's validator refuses, naming the op", () => {
    const errs = (rows: OpRow[]) => buildSequence("x", rows, channels).errors.join(" | ");
    expect(errs([])).toMatch(/at least one op/);
    expect(errs([{ op: "step", fields: { channel: "nope", level: "0", duration: "1" } }])).toMatch(/op 1 \(step\): unknown channel "nope"/);
    expect(errs([{ op: "measure", fields: { channel: "P1", duration: "1", result: "I" } }])).toMatch(/measures a current channel/);
    expect(errs([{ op: "step", fields: { channel: "sensor", level: "0", duration: "1" } }])).toMatch(/drives a voltage channel/);
    expect(errs([{ op: "wait", fields: { duration: "1.5" } }])).toMatch(/whole number of ns/);
    expect(errs([{ op: "wait", fields: { duration: "" } }])).toMatch(/duration empty/);
    const twice: OpRow = { op: "measure", fields: { channel: "sensor", duration: "1", result: "I" } };
    expect(errs([twice, twice])).toMatch(/op 2 \(measure\): result "I" is already measured/);
    // the same symbol in a level (V) and a duration (ns)
    expect(errs([{ op: "step", fields: { channel: "P1", level: "x", duration: "x" } }])).toMatch(/symbol "x" is used in V and ns/);
    expect(buildSequence("x", [{ op: "wait", fields: { duration: "1.5" } }], channels).sequence).toBeNull();
  });
});

describe("symbol bindings", () => {
  it("keeps what was typed and binds a new v_<axis> symbol to its axis", () => {
    const rows = syncBindings(["v_P2", "t_ramp", "v_kick"], [{ symbol: "t_ramp", target: "40" }, { symbol: "gone", target: "P1" }], ["P1", "P2"]);
    expect(rows).toEqual([
      { symbol: "v_P2", target: "P2" },
      { symbol: "t_ramp", target: "40" },
      { symbol: "v_kick", target: "" },
    ]);
  });

  it("an axis name binds to the axis, a number to a constant, anything else is an error", () => {
    const { bindings, errors } = buildBindings(
      [
        { symbol: "v_P2", target: "P2" },
        { symbol: "t_ramp", target: "40" },
        { symbol: "v_kick", target: "" },
      ],
      ["P1", "P2"],
    );
    expect(bindings).toEqual([
      { symbol: "v_P2", axis: "P2" },
      { symbol: "t_ramp", value: 40 },
    ]);
    expect(errors).toEqual(['symbol "v_kick" needs an axis (P1, P2) or a number']);
  });
});

describe("row moves", () => {
  it("swaps neighbours and leaves the ends alone", () => {
    expect(moveRow(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
    expect(moveRow(["a", "b", "c"], 2, 1)).toEqual(["a", "b", "c"]);
  });
});

describe("stage sweeps with an edited sequence; 1-D sweeps", () => {
  const base = {
    name: "pulsed",
    outer: { channel: "P1", start: 0.03, stop: 0.18, num: 8 },
    inner: { channel: "P2_pulse", start: 0.03, stop: 0.18, num: 8 },
    sensor: "sensor",
    instrument: "dot",
    shots: 4,
    stepNs: 500,
    measureNs: 2000,
    result: "I_sensor",
  };
  const rows: OpRow[] = [
    { op: "step", fields: { channel: "P2_pulse", level: "v_P2", duration: "500" } },
    { op: "step", fields: { channel: "bias_pulse", level: "v_kick", duration: "100" } },
    { op: "measure", fields: { channel: "sensor", duration: "1000", result: "I_a" } },
    { op: "measure", fields: { channel: "sensor", duration: "1000", result: "I_b" } },
  ];

  it("puts the edited sequence and its bindings on the stage and reduces every result", () => {
    const bindings = [
      { symbol: "v_P2", target: "P2" },
      { symbol: "v_kick", target: "1e-4" },
    ];
    const d = stageSweep({ ...base, sequence: { rows, bindings, channels } });
    expect(d.stage!.sequence!.body).toHaveLength(4);
    expect(d.stage!.bindings).toEqual([
      { symbol: "v_P2", axis: "P2" },
      { symbol: "v_kick", value: 1e-4 },
    ]);
    expect(d.stage!.reduce).toEqual({ I_a: "mean", I_b: "mean" });
  });

  it("a symbol may take the stepped outer axis's value", () => {
    const d = stageSweep({ ...base, sequence: { rows, bindings: [{ symbol: "v_P2", target: "P2" }, { symbol: "v_kick", target: "P1" }], channels } });
    expect(d.stage!.bindings![1]).toEqual({ symbol: "v_kick", axis: "P1" });
  });

  it("collects sequence, binding and result errors into one message", () => {
    const bad: OpRow[] = [
      { op: "step", fields: { channel: "P2_pulse", level: "v_P2", duration: "500" } },
      { op: "measure", fields: { channel: "sensor", duration: "1000", result: "P1" } },
    ];
    expect(() => stageSweep({ ...base, sequence: { rows: bad, bindings: [{ symbol: "v_P2", target: "" }], channels } })).toThrow(
      /symbol "v_P2" needs an axis.*result "P1" has an axis's name/,
    );
    expect(() => stageSweep({ ...base, sequence: { rows: [{ op: "wait", fields: { duration: "10" } }], bindings: [], channels } })).toThrow(/measures nothing/);
  });

  it("drops the outer axis for a 1-D stage sweep", () => {
    const d = stageSweep({ ...base, outer: null, shots: 1 });
    expect(d.axes!.map((a) => a.name)).toEqual(["P2"]);
    expect(d.stage!.axes).toEqual(["P2"]);
    expect(d.stage!.reduce).toEqual({});
  });

  it("drops the outer axis for a 1-D DC sweep, and keeps the sensor off the axes", () => {
    const d = dcSweep({ name: "trace", outer: null, inner: { channel: "SG", start: -0.2, stop: 0.2, num: 32 }, sensor: "sensor", result: "I_sensor" });
    expect(d.axes!.map((a) => a.name)).toEqual(["SG"]);
    expect(() => dcSweep({ name: "x", inner: { channel: "sensor", start: 0, stop: 1, num: 2 }, sensor: "sensor", result: "I" })).toThrow(/not both/);
    expect(() => dcSweep({ name: "x", inner: { channel: "SG", start: 0, stop: 1, num: 2, name: "repeat" }, sensor: "sensor", result: "I" })).toThrow(/reserved/);
  });
});

describe("new rows", () => {
  it("pulse a sequencer's _pulse line by default and measure the sensor", () => {
    expect(newRow("ramp", channels).fields.channel).toBe("P2_pulse");
    expect(newRow("measure", channels).fields.channel).toBe("sensor");
    expect(newRow("step", channels.filter((c) => !c.logical.endsWith("_pulse"))).fields.channel).toBe("P1");
  });
});
