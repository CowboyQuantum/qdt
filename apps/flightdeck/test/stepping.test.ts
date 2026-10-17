// The stepping control's pure parts (ADR 0064, 0066): which sequencer can advance a channel by trigger,
// what the control offers per kind, and the definitions the builders make when the innermost stepped axis
// is triggered (the per-point readout moved into the shot).
import { describe, expect, it } from "vitest";
import type { ExecutionPlan, StandConfig } from "../src/schema/api";
import { captureSweep, companionErrors, dcSweep, stageSweep, steppingFor, triggerFor } from "../src/control/sweeps";
import { formSummary, planSummary } from "../src/widgets/sweep";

/** The simulated stand: the device is its own sequencer and loads lists, so it triggers itself. */
const SIM = {
  stand_id: "simulated-double-dot",
  instruments: [
    { id: "dot", backend: "simulated", capabilities: ["level_source", "level_sense", "sequencer", "triggered_level_source"] },
    { id: "scope", backend: "simulated", capabilities: ["waveform_sense"] },
  ],
  channels: [
    { logical: "P1", instrument: "dot", channel: "P1", quantity: "voltage" },
    { logical: "P2", instrument: "dot", channel: "P2", quantity: "voltage" },
    { logical: "P2_pulse", instrument: "dot", channel: "P2_pulse", quantity: "voltage" },
    { logical: "sensor", instrument: "dot", channel: "sensor", quantity: "current" },
    { logical: "scope1", instrument: "scope", channel: "1", quantity: "voltage" },
  ],
} as StandConfig;

/** A bench-shaped stand: the DAC's list is advanced by the OPX's marker m2 (`trigger_from`), and three DACs
 * that cannot be: no list capability, no marker line, a marker line that is not a sequencer's. */
const BENCH = {
  stand_id: "bench",
  instruments: [
    { id: "opx", backend: "qua", capabilities: ["sequencer", "waveform_source", "waveform_sense"] },
    { id: "dac0", backend: "qdac2", capabilities: ["level_source", "triggered_level_source"], settings: { trigger_from: "m2", trigger_in: "ext1" } },
    { id: "dac1", backend: "qdac2", capabilities: ["level_source"] },
    { id: "dac2", backend: "qdac2", capabilities: ["level_source", "triggered_level_source"] },
    { id: "dac3", backend: "qdac2", capabilities: ["level_source", "triggered_level_source"], settings: { trigger_from: "P1" } },
    { id: "smu", backend: "k2450", capabilities: ["level_source", "level_sense"] },
    { id: "scope0", backend: "infiniivision", capabilities: ["waveform_sense"] },
  ],
  channels: [
    { logical: "P1", instrument: "dac0", channel: "1", quantity: "voltage" },
    { logical: "P2", instrument: "dac0", channel: "2", quantity: "voltage" },
    { logical: "P3", instrument: "dac1", channel: "1", quantity: "voltage" },
    { logical: "P4", instrument: "dac2", channel: "1", quantity: "voltage" },
    { logical: "P5", instrument: "dac3", channel: "1", quantity: "voltage" },
    { logical: "P2_pulse", instrument: "opx", channel: "ao1", quantity: "voltage" },
    { logical: "m2", instrument: "opx", channel: "do2", quantity: "voltage" },
    { logical: "ai1", instrument: "opx", channel: "ai1", quantity: "current" },
    { logical: "opx_in", instrument: "opx", channel: "ai2", quantity: "voltage" },
    { logical: "smu_i", instrument: "smu", channel: "1", quantity: "current" },
    { logical: "scope1", instrument: "scope0", channel: "1", quantity: "voltage" },
  ],
} as StandConfig;

describe("triggerFor", () => {
  it("names the sequencer whose trigger advances a channel, or why none can, as the compiler does", () => {
    expect(triggerFor(SIM, "P1")).toEqual({ sequencer: "dot" }); // the device triggers itself
    expect(triggerFor(BENCH, "P1")).toEqual({ sequencer: "opx" }); // dac0's trigger_from is the OPX's m2
    expect(triggerFor(BENCH, "P3")).toEqual({ reason: "dac1 cannot load a list of levels (no triggered_level_source)" });
    expect(triggerFor(BENCH, "P4")).toEqual({ reason: "dac2 has no settings.trigger_from: no sequencer marker line advances it" });
    expect(triggerFor(BENCH, "P5")).toEqual({ reason: "dac3's trigger_from P1 is not a channel of a sequencer" });
    expect(triggerFor(BENCH, "nope")).toEqual({ reason: "no channel nope on the stand" });
  });
});

describe("steppingFor", () => {
  const form = (f: Partial<{ outer: string; inner: string; sensor: string; capture: string }>) => ({ outer: "", inner: "", sensor: "", capture: "", ...f });

  it("applies to the innermost stepped axis of the kind: a stage or capture sweep's outer axis, a DC sweep's inner one", () => {
    expect(steppingFor(SIM, "stage", form({ outer: "P1", inner: "P2_pulse", sensor: "sensor" }))).toEqual({ axis: "outer", channel: "P1", sequencer: "dot" });
    expect(steppingFor(SIM, "dc", form({ outer: "P1", inner: "P2", sensor: "sensor" }))).toEqual({ axis: "inner", channel: "P2", sequencer: "dot" });
    expect(steppingFor(SIM, "capture", form({ outer: "P1", capture: "scope1" }))).toEqual({ axis: "outer", channel: "P1", sequencer: "dot" });
    expect(steppingFor(SIM, "stage", form({ inner: "P2_pulse" }))).toMatchObject({ axis: null, reason: expect.stringMatching(/pick an outer channel/) });
    expect(steppingFor(SIM, "capture", form({ capture: "scope1" }))).toMatchObject({ axis: null });
  });

  it("refuses what the stand cannot run: an untriggerable channel, a sensor or scope on the wrong instrument, two sequencers", () => {
    expect(steppingFor(BENCH, "dc", form({ inner: "P3", sensor: "ai1" })).reason).toMatch(/dac1 cannot load a list/);
    expect(steppingFor(BENCH, "dc", form({ inner: "P2", sensor: "smu_i" })).reason).toBe("triggered, the sensor is read in the shot by opx, and smu_i is not one of its inputs");
    expect(steppingFor(BENCH, "dc", form({ inner: "P2", sensor: "ai1" }))).toEqual({ axis: "inner", channel: "P2", sequencer: "opx" });
    expect(steppingFor(BENCH, "capture", form({ outer: "P1", capture: "opx_in" })).reason).toMatch(/a scope of its own/);
    expect(steppingFor(BENCH, "capture", form({ outer: "P1", capture: "scope1" })).sequencer).toBe("opx");
    expect(steppingFor(BENCH, "stage", form({ outer: "P1", inner: "P2_pulse" })).sequencer).toBe("opx");
    // a pulsed axis on another sequencer than the one that advances the DAC
    const two = { ...SIM, channels: [...SIM.channels, { logical: "Q_pulse", instrument: "awg", channel: "1", quantity: "voltage" }], instruments: [...SIM.instruments, { id: "awg", backend: "simulated", capabilities: ["sequencer"] }] } as StandConfig;
    expect(steppingFor(two, "stage", form({ outer: "P1", inner: "Q_pulse" })).reason).toBe("P1 is advanced by dot, but the pulsed axis runs on awg");
  });

  it("checks the triggered axis's virtual-gate companions: lists too, on the same sequencer", () => {
    expect(companionErrors(SIM, { P2: -0.2 }, "dot")).toEqual([]);
    expect(companionErrors(BENCH, { P2: 0.1 }, "opx")).toEqual([]);
    expect(companionErrors(BENCH, { P3: 0.1 }, "opx")).toEqual(["the triggered axis moves P3 as a virtual gate, but dac1 cannot load a list of levels (no triggered_level_source)"]);
    expect(companionErrors(SIM, undefined, "dot")).toEqual([]);
  });
});

describe("builders with a triggered axis", () => {
  const P1 = { channel: "P1", start: 0.03, stop: 0.18, num: 6 };
  const P2 = { channel: "P2", start: 0.03, stop: 0.18, num: 8 };

  it("a stage sweep: the outer DC axis triggered, the pulsed axis and the sequence unchanged", () => {
    const base = { name: "s", inner: { channel: "P2_pulse", start: 0, stop: 0.1, num: 4 }, sensor: "sensor", instrument: "dot", shots: 1, stepNs: 500, measureNs: 2000, result: "I" };
    const d = stageSweep({ ...base, outer: { ...P1, stepping: "triggered" } });
    expect(d.axes!.map((a) => a.stepping)).toEqual(["triggered", undefined]);
    expect(d.stage!.axes).toEqual(["P2"]);
    expect(() => stageSweep({ ...base, inner: { ...base.inner, stepping: "triggered" } })).toThrow(/pulsed axis is swept by the sequencer, not triggered/);
    // software is the default and never sent: a definition without a triggered axis keeps its hash
    expect("stepping" in stageSweep({ ...base, outer: P1 }).axes![0]!).toBe(false);
  });

  it("a DC sweep: the inner axis triggered, the sensor read in a one-measure shot, shots averaged", () => {
    const d = dcSweep({ name: "map", outer: P1, inner: { ...P2, stepping: "triggered" }, sensor: "sensor", result: "I_sensor", shot: { instrument: "dot", measureNs: 2000, shots: 3 } });
    expect(d.axes!.map((a) => a.stepping)).toEqual([undefined, "triggered"]);
    expect(d.sensed).toEqual([]);
    expect(d.stage).toEqual({
      instrument: "dot",
      axes: [],
      sequence: { name: "read sensor at each P2 point", body: [{ op: "measure", channel: "sensor", duration: 2000, result: "I_sensor" }] },
      bindings: [],
      shots: 3,
      reduce: { I_sensor: "mean" },
    });
    expect(dcSweep({ name: "map", inner: { ...P2, stepping: "triggered" }, sensor: "sensor", result: "I", shot: { instrument: "dot", measureNs: 2000, shots: 1 } }).stage!.reduce).toEqual({});
    expect(() => dcSweep({ name: "map", inner: { ...P2, stepping: "triggered" }, sensor: "sensor", result: "I" })).toThrow(/needs the sequencer that advances it/);
    expect(() => dcSweep({ name: "map", outer: { ...P1, stepping: "triggered" }, inner: P2, sensor: "sensor", result: "I" })).toThrow(/only the innermost stepped axis/);
    expect(() => dcSweep({ name: "map", inner: { ...P2, stepping: "triggered" }, sensor: "sensor", result: "I", shot: { instrument: "dot", measureNs: 0, shots: 1 } })).toThrow(/integration/);
    // untriggered, the sensor is still sensed per point and there is no stage
    const plain = dcSweep({ name: "map", outer: P1, inner: P2, sensor: "sensor", result: "I" });
    expect(plain.sensed).toEqual([{ name: "I", channel: "sensor" }]);
    expect(plain.stage).toBeNull();
  });

  it("a capture: the outer axis triggered, the record moved into the shot from its marker, then a pacing wait", () => {
    const base = { name: "staircase", channel: "scope1", startS: 0, stopS: 2e-3, num: 200, records: 3, result: "trace" };
    const d = captureSweep({ ...base, outer: { ...P1, stepping: "triggered" }, shot: { instrument: "dot", paceNs: 50_000_000 } });
    expect(d.captured ?? []).toEqual([]);
    expect(d.axes!.map((a) => a.stepping)).toEqual(["triggered"]);
    expect(d.stage).toEqual({
      instrument: "dot",
      axes: [],
      sequence: {
        name: "capture scope1 at each P1 point",
        body: [
          { op: "capture", channel: "scope1", duration: 2_000_000, num: 200, result: "trace" },
          { op: "wait", duration: 50_000_000 },
        ],
      },
      bindings: [],
      shots: 3,
    });
    expect(captureSweep({ ...base, outer: { ...P1, stepping: "triggered" }, shot: { instrument: "dot", paceNs: 0 } }).stage!.sequence!.body).toHaveLength(1);
    expect(() => captureSweep({ ...base, startS: -1e-3, outer: { ...P1, stepping: "triggered" }, shot: { instrument: "dot", paceNs: 0 } })).toThrow(/start must be 0/);
    expect(() => captureSweep({ ...base, outer: { ...P1, stepping: "triggered" } })).toThrow(/needs the sequencer that advances it/);
    // untriggered, it is the per-point capture of ADR 0047
    expect(captureSweep({ ...base, outer: P1 }).captured).toHaveLength(1);
  });
});

describe("the next-run line and the plan summary name the triggered axis", () => {
  const values = (v: Record<string, string>) => (n: string) => v[n] ?? "";
  it("marks the innermost stepped axis of the kind", () => {
    const common = { name: "x", outer_channel: "P1", outer_num: "6", inner_channel: "P2", inner_num: "8", capture_channel: "scope1", capture_num: "200", stepping: "triggered" };
    expect(formSummary(values({ ...common, kind: "dc" }))).toBe("x · dc · P1 6 × P2 8 (triggered)");
    expect(formSummary(values({ ...common, kind: "stage", inner_channel: "P2_pulse" }))).toBe("x · stage · P1 6 (triggered) × P2_pulse 8");
    expect(formSummary(values({ ...common, kind: "capture" }))).toBe("x · capture · P1 6 (triggered) × scope1 200 samples");
    expect(formSummary(values({ ...common, kind: "dc", stepping: "software" }))).toBe("x · dc · P1 6 × P2 8");
  });

  it("the plan summary says which axis the sequencer advances", () => {
    const plan = {
      plan_id: "abc",
      definition: { name: "map", axes: [{ name: "P1", stepping: undefined }, { name: "P2", stepping: "triggered" }] },
      dataset: { dims: [{ name: "P1", size: 6 }, { name: "P2", size: 8 }] },
      channels: [{}, {}],
      stage_program: { ops: [] },
    } as unknown as ExecutionPlan;
    expect(planSummary(plan)).toBe("map · P1 6 × P2 8 · 48 pts · 2 channels · stage program · P2 triggered");
  });
});
