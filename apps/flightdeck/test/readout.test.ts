// The readout choices' pure parts (ADR 0067, from the builders of #64): which sequencer reads a sensor or plays a
// capture's shot, and the definitions the builders make when a DC or capture sweep reads in the shot. Pacing stays
// the compiler's (ADR 0066): the builders pass the stepping preference through and refuse only what cannot run.
import { describe, expect, it } from "vitest";
import type { StandConfig } from "../src/schema/api";
import { captureSequencer, captureSweep, dcSweep, sensorSequencer } from "../src/control/sweeps";
import { formSummary } from "../src/widgets/sweep";

/** The simulated stand: the device is its own sequencer, and the scope an instrument of its own. */
const SIM = {
  stand_id: "simulated-double-dot",
  instruments: [
    { id: "dot", backend: "simulated", capabilities: ["level_source", "level_sense", "sequencer", "triggered_level_source"] },
    { id: "scope", backend: "simulated", capabilities: ["waveform_sense"] },
  ],
  channels: [
    { logical: "P1", instrument: "dot", channel: "P1", quantity: "voltage" },
    { logical: "P2", instrument: "dot", channel: "P2", quantity: "voltage" },
    { logical: "sensor", instrument: "dot", channel: "sensor", quantity: "current" },
    { logical: "scope1", instrument: "scope", channel: "1", quantity: "voltage" },
  ],
} as StandConfig;

/** A bench-shaped stand: the OPX is the sequencer, the scope names the OPX's do1 as its trigger line, an SMU
 * senses current, and a second sequencer and an unwired scope make the ambiguous cases. */
const BENCH = {
  stand_id: "bench",
  instruments: [
    { id: "opx", backend: "qua", capabilities: ["sequencer", "waveform_source", "waveform_sense"] },
    { id: "smu", backend: "keithley2400", capabilities: ["level_source", "level_sense"] },
    { id: "scope0", backend: "infiniivision", capabilities: ["waveform_sense"], settings: { trigger_from: "scope_trigger" } },
    { id: "scope9", backend: "infiniivision", capabilities: ["waveform_sense"], settings: { trigger_from: "smu_i" } },
  ],
  channels: [
    { logical: "ai1", instrument: "opx", channel: "ai1", quantity: "current" },
    { logical: "opx_in", instrument: "opx", channel: "ai2", quantity: "voltage" },
    { logical: "scope_trigger", instrument: "opx", channel: "do1", quantity: "voltage" },
    { logical: "smu_i", instrument: "smu", channel: "out_i", quantity: "current" },
    { logical: "scope1", instrument: "scope0", channel: "1", quantity: "voltage" },
    { logical: "scope9_1", instrument: "scope9", channel: "1", quantity: "voltage" },
  ],
} as StandConfig;

describe("which sequencer reads in the shot", () => {
  it("a sensor is read by the sequencer whose input it is, or only per point", () => {
    expect(sensorSequencer(SIM, "sensor")).toEqual({ sequencer: "dot" });
    expect(sensorSequencer(BENCH, "ai1")).toEqual({ sequencer: "opx" });
    expect(sensorSequencer(BENCH, "smu_i")).toEqual({ reason: "smu_i is read by smu, which is not a sequencer: it can only be sensed per point" });
    expect(sensorSequencer(BENCH, "")).toEqual({ reason: "no channel (none) on the stand" });
  });

  it("a capture's shot runs on the sequencer that triggers the scope, else on the stand's only sequencer", () => {
    expect(captureSequencer(SIM, "scope1")).toEqual({ sequencer: "dot" }); // no trigger line: the only sequencer
    expect(captureSequencer(BENCH, "scope1")).toEqual({ sequencer: "opx" }); // trigger_from is the OPX's do1
    expect(captureSequencer(BENCH, "scope9_1")).toEqual({ reason: "scope9's trigger_from smu_i is not a channel of a sequencer" });
    expect(captureSequencer(BENCH, "opx_in")).toMatchObject({ reason: expect.stringMatching(/an input of the sequencer opx; a capture in the shot needs a scope of its own/) });
    const two = { ...SIM, instruments: [...SIM.instruments, { id: "awg", backend: "simulated", capabilities: ["sequencer"] }] } as StandConfig;
    expect(captureSequencer(two, "scope1")).toEqual({ reason: "the stand has 2 sequencers and scope names none in trigger_from" });
  });
});

describe("a DC sweep read in the shot", () => {
  const P1 = { channel: "P1", start: 0.03, stop: 0.18, num: 6 };
  const P2 = { channel: "P2", start: 0.03, stop: 0.18, num: 8 };
  const shot = { instrument: "dot", measureNs: 2000, shots: 3 };

  it("integrates the sensor in a one-measure shot, shots averaged, and leaves pacing to the stand", () => {
    const d = dcSweep({ name: "map", outer: P1, inner: P2, sensor: "sensor", result: "I_sensor", readout: "shot", shot });
    expect(d.sensed).toEqual([]);
    expect(d.axes!.map((a) => a.stepping)).toEqual([undefined, undefined]); // auto: the compiler decides
    expect(d.stage).toEqual({
      instrument: "dot",
      axes: [],
      sequence: { name: "read sensor at each P2 point", body: [{ op: "measure", channel: "sensor", duration: 2000, result: "I_sensor" }] },
      bindings: [],
      shots: 3,
      reduce: { I_sensor: "mean" },
    });
    expect(dcSweep({ name: "map", inner: P2, sensor: "sensor", result: "I", readout: "shot", shot: { ...shot, shots: 1 } }).stage!.reduce).toEqual({});
    // a forced trigger is passed to the inner axis, the innermost stepped one
    expect(dcSweep({ name: "map", inner: { ...P2, stepping: "triggered" }, sensor: "sensor", result: "I", readout: "shot", shot }).axes![0]!.stepping).toBe("triggered");
  });

  it("refuses what cannot run: no sequencer, a bad integration, a trigger on the outer axis", () => {
    const base = { name: "map", inner: P2, sensor: "sensor", result: "I", readout: "shot" as const };
    expect(() => dcSweep(base)).toThrow(/needs the sequencer whose input it is/);
    expect(() => dcSweep({ ...base, shot: { ...shot, measureNs: 0 } })).toThrow(/integration/);
    expect(() => dcSweep({ ...base, outer: { ...P1, stepping: "triggered" }, shot })).toThrow(/P1: only the innermost stepped axis can be triggered/);
  });

  it("stepped from the host, it still reads in the shot: one measure per point (ADR 0068)", () => {
    const d = dcSweep({ name: "map", inner: { ...P2, stepping: "software" }, sensor: "sensor", result: "I", readout: "shot", shot });
    expect(d.axes![0]!.stepping).toBe("software");
    expect(d.stage!.axes).toEqual([]);
  });

  it("read per point, it is the sensed sweep of before, and a forced trigger is refused", () => {
    const plain = dcSweep({ name: "map", outer: P1, inner: P2, sensor: "sensor", result: "I" });
    expect(plain.sensed).toEqual([{ name: "I", channel: "sensor" }]);
    expect(plain.stage).toBeNull();
    expect(() => dcSweep({ name: "map", inner: { ...P2, stepping: "triggered" }, sensor: "sensor", result: "I" })).toThrow(/read per point, a DC sweep is stepped from the host; read in the shot/);
  });
});

describe("a capture recorded in the shot", () => {
  const P1 = { channel: "P1", start: 0.03, stop: 0.18, num: 6 };
  const base = { name: "staircase", channel: "scope1", startS: 0, stopS: 2e-3, num: 200, records: 3, result: "trace", readout: "shot" as const };

  it("moves the record into a shot from its marker, one per shot, then a wait", () => {
    const d = captureSweep({ ...base, outer: P1, shot: { instrument: "dot", paceNs: 50_000_000 } });
    expect(d.captured ?? []).toEqual([]);
    expect(d.axes!.map((a) => a.stepping)).toEqual([undefined]); // auto: the compiler decides
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
    expect(captureSweep({ ...base, shot: { instrument: "dot", paceNs: 0 } }).stage!.sequence).toEqual({
      name: "capture scope1",
      body: [{ op: "capture", channel: "scope1", duration: 2_000_000, num: 200, result: "trace" }],
    });
  });

  it("refuses a start before the marker, a missing sequencer and a negative wait", () => {
    expect(() => captureSweep({ ...base, startS: -1e-3, shot: { instrument: "dot", paceNs: 0 } })).toThrow(/start must be 0/);
    expect(() => captureSweep({ ...base, outer: P1 })).toThrow(/needs the sequencer that plays the shot/);
    expect(() => captureSweep({ ...base, shot: { instrument: "dot", paceNs: -1 } })).toThrow(/wait after each record/);
  });

  it("per point, it is the capture of ADR 0047, and a forced trigger is refused", () => {
    const point = { ...base, readout: "point" as const, outer: P1 };
    expect(captureSweep(point).captured).toHaveLength(1);
    expect(() => captureSweep({ ...point, outer: { ...P1, stepping: "triggered" } })).toThrow(/read per point, a capture sweep is stepped from the host/);
  });
});

describe("the next-run line says where a DC or capture sweep reads", () => {
  const values = (v: Record<string, string>) => (n: string) => v[n] ?? "";
  it("marks a sweep read in the shot", () => {
    const common = { name: "x", outer_channel: "P1", outer_num: "6", inner_channel: "P2", inner_num: "8", capture_channel: "scope1", capture_num: "200" };
    expect(formSummary(values({ ...common, kind: "dc", readout: "shot" }))).toBe("x · dc in the shot · P1 6 × P2 8");
    expect(formSummary(values({ ...common, kind: "capture", readout: "shot" }))).toBe("x · capture in the shot · P1 6 × scope1 200 samples");
    expect(formSummary(values({ ...common, kind: "dc", readout: "point" }))).toBe("x · dc · P1 6 × P2 8");
    expect(formSummary(values({ ...common, kind: "stage", readout: "shot", inner_channel: "P2_pulse" }))).toBe("x · stage · P1 6 × P2_pulse 8");
  });
});
