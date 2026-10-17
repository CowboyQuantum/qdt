import { describe, expect, it } from "vitest";
import { ApiClient, ApiError, apiBase, describeDetail } from "../src/api/client";
import { check, defaults, overrides, parse } from "../src/control/methods";
import { tuneupLines } from "../src/widgets/tuneup";
import { setpointFor } from "../src/widgets/levels";
import { captureSweep, dcSweep, stageSweep, standChannels } from "../src/control/sweeps";
import type { MethodSpec, StandConfig } from "../src/schema/api";

const stand: StandConfig = {
  stand_id: "simulated-double-dot",
  instruments: [
    { id: "dot", backend: "simulated", capabilities: ["level_source", "level_sense", "sequencer"] },
    { id: "scope", backend: "simulated", capabilities: ["waveform_sense"] },
  ],
  channels: [
    { logical: "P1", instrument: "dot", channel: "P1", quantity: "voltage" },
    { logical: "P2", instrument: "dot", channel: "P2", quantity: "voltage" },
    { logical: "SG", instrument: "dot", channel: "SG", quantity: "voltage" },
    { logical: "P2_pulse", instrument: "dot", channel: "P2_pulse", quantity: "voltage" },
    { logical: "bias", instrument: "dot", channel: "bias", quantity: "voltage" },
    { logical: "sensor", instrument: "dot", channel: "sensor", quantity: "current" },
    { logical: "scope1", instrument: "scope", channel: "1", quantity: "voltage" },
  ],
} as StandConfig;

describe("sweep builders", () => {
  it("passes a stage sweep's stepping preference to its stepped axis, and leaves 'auto' unsaid (ADR 0066)", () => {
    const base = {
      name: "stability",
      inner: { channel: "P2_pulse", start: 0.03, stop: 0.18, num: 48 },
      sensor: "sensor",
      instrument: "dot",
      shots: 1,
      stepNs: 500,
      measureNs: 2000,
      result: "I_sensor",
    };
    const outer = { channel: "P1", start: 0.03, stop: 0.18, num: 48 };
    for (const stepping of ["software", "triggered"] as const) {
      expect(stageSweep({ ...base, outer: { ...outer, stepping } }).axes![0]!.stepping).toBe(stepping);
    }
    expect("stepping" in stageSweep({ ...base, outer: { ...outer, stepping: "auto" } }).axes![0]!).toBe(false);
    expect("stepping" in stageSweep({ ...base, outer }).axes![0]!).toBe(false);
    expect(() => stageSweep({ ...base, outer, inner: { ...base.inner, stepping: "software" } })).toThrow(/a stage axis is swept in the sequence/);
  });

  it("refuses a forced trigger where every point is read from the host", () => {
    const triggered = { channel: "P1", start: 0, stop: 1, num: 5, stepping: "triggered" as const };
    expect(() => dcSweep({ name: "dc", inner: triggered, sensor: "sensor", result: "I" })).toThrow(/read per point, a DC sweep is stepped from the host/);
    expect(() => captureSweep({ name: "c", outer: triggered, channel: "scope1", startS: 0, stopS: 1e-3, num: 100, records: 1, result: "trace" })).toThrow(/read per point, a capture sweep is stepped from the host/);
    expect(dcSweep({ name: "dc", inner: { ...triggered, stepping: "software" }, sensor: "sensor", result: "I" }).axes![0]!.stepping).toBe("software");
  });

  it("builds a stage sweep like qdt_sim.scenarios.stability", () => {
    const d = stageSweep({
      name: "stability",
      outer: { channel: "P1", start: 0.03, stop: 0.18, num: 48 },
      inner: { channel: "P2_pulse", start: 0.03, stop: 0.18, num: 48 },
      sensor: "sensor",
      instrument: "dot",
      shots: 3,
      stepNs: 500,
      measureNs: 2000,
      result: "I_sensor",
    });
    expect(d.axes!.map((a) => a.name)).toEqual(["P1", "P2"]);
    expect(d.axes![1]!.channel).toBe("P2_pulse");
    expect(d.stage!.axes).toEqual(["P2"]);
    expect(d.stage!.bindings).toEqual([{ symbol: "v_P2", axis: "P2" }]);
    expect(d.stage!.sequence!.body.map((op) => op.op)).toEqual(["step", "measure"]);
    expect(d.stage!.shots).toBe(3);
    expect(d.stage!.reduce).toEqual({ I_sensor: "mean" });
    expect(d.sensed).toEqual([]);
  });

  it("builds a DC sweep like qdt_sim.scenarios.diamonds", () => {
    const d = dcSweep({
      name: "diamonds",
      outer: { channel: "SG", start: -0.2, stop: 0.2, num: 64 },
      inner: { channel: "bias", start: -1.5e-3, stop: 1.5e-3, num: 64, name: "V_sd" },
      sensor: "sensor",
      result: "I_sensor",
    });
    expect(d.axes!.map((a) => a.name)).toEqual(["SG", "V_sd"]);
    expect(d.sensed).toEqual([{ name: "I_sensor", channel: "sensor" }]);
    expect(d.stage).toBeNull();
  });

  it("refuses what the server would refuse, before the request", () => {
    const outer = { channel: "P1", start: 0, stop: 1, num: 4 };
    expect(() => stageSweep({ name: "x", outer, inner: { ...outer }, sensor: "sensor", instrument: "dot", shots: 1, stepNs: 1, measureNs: 1, result: "I" })).toThrow(
      /different names/,
    );
    expect(() => dcSweep({ name: "x", outer, inner: { channel: "SG", start: 0, stop: 1, num: 0 }, sensor: "sensor", result: "I" })).toThrow(/positive integer/);
    expect(() => dcSweep({ name: "x", outer, inner: { channel: "SG", start: NaN, stop: 1, num: 2 }, sensor: "", result: "I" })).toThrow(/must be numbers.*sensor/);
  });

  it("classifies a stand's channels for the selects", () => {
    const c = standChannels(stand);
    expect(c.dc.map((x) => x.logical)).toEqual(["P1", "P2", "SG", "bias"]);
    expect(c.pulse.map((x) => x.logical)).toEqual(["P2_pulse"]);
    expect(c.sensors.map((x) => x.logical)).toEqual(["sensor"]);
    expect(c.waveforms.map((x) => x.logical)).toEqual(["scope1"]); // a scope channel is not a DC line
  });

  it("builds a capture, alone or at every point of a stepped axis (ADR 0047)", () => {
    const alone = captureSweep({ name: "droop", channel: "scope1", startS: -1e-3, stopS: 9e-3, num: 1000, records: 2, result: "trace" });
    expect(alone.axes).toEqual([]);
    expect(alone.captured).toEqual([{ name: "trace", channel: "scope1", start_s: -1e-3, stop_s: 9e-3, num: 1000, records: 2 }]);
    expect(alone.sensed).toEqual([]);
    expect(alone.stage).toBeNull();
    const stepped = captureSweep({ name: "stepped", outer: { channel: "P1", start: 0, stop: 1, num: 3 }, channel: "scope1", startS: 0, stopS: 1e-3, num: 100, records: 1, result: "trace" });
    expect(stepped.axes!.map((a) => a.name)).toEqual(["P1"]);
    const base = { name: "x", channel: "scope1", startS: 0, stopS: 1e-3, num: 100, records: 1, result: "trace" };
    expect(() => captureSweep({ ...base, stopS: 0 })).toThrow(/stop must be after start/);
    expect(() => captureSweep({ ...base, num: 1 })).toThrow(/at least 2/);
    expect(() => captureSweep({ ...base, records: 0 })).toThrow(/records/);
    expect(() => captureSweep({ ...base, channel: "" })).toThrow(/WaveformSense channel/);
    expect(() => captureSweep({ ...base, result: "time" })).toThrow(/dimension name/);
    expect(() => captureSweep({ ...base, outer: { channel: "scope1", start: 0, stop: 1, num: 3 } })).toThrow(/not both/);
  });
});

const spec: MethodSpec = {
  name: "m",
  version: "1",
  title: "M",
  description: "",
  applies_to: "map_2d",
  parameters: [
    { name: "smooth_px", kind: "float", default: 1.0, unit: "px", minimum: 0, maximum: null, description: "" },
    { name: "min_segment_px", kind: "int", default: 6, unit: "px", minimum: 2, maximum: null, description: "" },
    { name: "variable", kind: "str", default: "", unit: "", minimum: null, maximum: null, description: "" },
    { name: "fast", kind: "bool", default: false, unit: "", minimum: null, maximum: null, description: "" },
  ],
  estimates: [],
} as MethodSpec;

describe("method parameter forms", () => {
  it("starts from the spec's defaults and sends only the overrides", () => {
    expect(defaults(spec)).toEqual({ smooth_px: 1, min_segment_px: 6, variable: "", fast: false });
    expect(overrides(spec, { ...defaults(spec), smooth_px: 1.5 })).toEqual({ smooth_px: 1.5 });
  });

  it("parses typed input by kind", () => {
    expect(parse(spec.parameters![0]!, " 2.5 ")).toBe(2.5);
    expect(parse(spec.parameters![1]!, "8")).toBe(8);
    expect(() => parse(spec.parameters![1]!, "8.5")).toThrow(/integer/);
    expect(() => parse(spec.parameters![0]!, "abc")).toThrow(/number/);
    expect(parse(spec.parameters![2]!, "I_sensor")).toBe("I_sensor");
    expect(parse(spec.parameters![3]!, true)).toBe(true);
    expect(parse(spec.parameters![3]!, "on")).toBe(true);
  });

  it("checks bounds and names the way the server does", () => {
    expect(check(spec, { smooth_px: -1 })).toEqual(["smooth_px: -1 is below the minimum 0"]);
    expect(check(spec, { min_segment_px: 1, nope: 1 })).toEqual(["m has no parameter nope", "min_segment_px: 1 is below the minimum 2"]);
    expect(check(spec, defaults(spec))).toEqual([]);
  });
});

describe("api client", () => {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fake = (body: unknown, status = 200) => async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  };

  it("posts schema objects as JSON and returns the response", async () => {
    calls.length = 0;
    const api = new ApiClient("http://x", fake({ run_id: "r", state: "queued" }));
    const run = await api.startRun({ definition: {} as never, options: { seed: 1 } });
    expect(run.state).toBe("queued");
    expect(calls[0]!.url).toBe("http://x/runs");
    expect(calls[0]!.init?.method).toBe("POST");
    expect(JSON.parse(calls[0]!.init!.body as string)).toEqual({ definition: {}, options: { seed: 1 } });
  });

  it("aborts a run by id", async () => {
    calls.length = 0;
    const run = await new ApiClient("http://x", fake({ run_id: "r 1", state: "aborted" })).abort("r 1");
    expect(run.state).toBe("aborted");
    expect(calls[0]!.url).toBe("http://x/runs/r%201/abort");
    expect(calls[0]!.init?.method).toBe("POST");
  });

  it("encodes record filters as a query string and skips empty ones", async () => {
    calls.length = 0;
    await new ApiClient("http://x", fake([])).records({ campaign: "demo", device_id: "" });
    expect(calls[0]!.url).toBe("http://x/records?campaign=demo");
  });

  it("turns an error response into an ApiError with the server's detail", async () => {
    const api = new ApiClient("http://x", fake({ detail: "no record 'abc'" }, 404));
    await expect(api.record("abc")).rejects.toMatchObject({ status: 404, detail: "no record 'abc'" } satisfies Partial<ApiError>);
  });

  it("turns a 422 validation list into its messages, not the echoed request", async () => {
    const detail = [{ type: "value_error", loc: ["body"], msg: "Value error, stage axis 'P2' is not bound to any symbol or parameter", input: { huge: true } }];
    const api = new ApiClient("http://x", fake({ detail }, 422));
    await expect(api.compile({} as never)).rejects.toMatchObject({ status: 422, detail: "stage axis 'P2' is not bound to any symbol or parameter" });
    expect(describeDetail([{ loc: ["body", "axes", 0, "num"], msg: "Input should be greater than or equal to 1" }])).toBe("axes.0.num: Input should be greater than or equal to 1");
  });

  it("takes the base from ?api= or defaults to the local server", () => {
    expect(apiBase(new URLSearchParams(""))).toBe("http://127.0.0.1:8700");
    expect(apiBase(new URLSearchParams("api=http://lab:9000/"))).toBe("http://lab:9000");
  });
});

describe("tune-up state (ADR 0050)", () => {
  const node = (node_id: string, deps: string[] = []) => ({ node_id, depends_on: deps, description: "" }) as never;
  const outcome = (node_id: string, status: string, outputs = {}, message = "") => ({ node_id, status, outputs, message }) as never;
  it("gives each node its status so far, its message, and an accepted node's outputs", () => {
    const nodes = [node("charge-lattice"), node("virtual-lattice", ["charge-lattice"])];
    const running = { state: "running", current_node: "virtual-lattice", nodes, outcomes: [outcome("charge-lattice", "accepted", { c_21: -0.22251, m_11: 1.05 })] } as never;
    expect(tuneupLines(running)).toEqual([
      { node: "charge-lattice", status: "accepted", message: "", outputs: "c_21=-0.2225 m_11=1.050" },
      { node: "virtual-lattice", status: "running", message: "", outputs: "" },
    ]);
    const stopped = { state: "stopped", current_node: null, nodes, outcomes: [outcome("charge-lattice", "rejected", {}, "ratios")] } as never;
    expect(tuneupLines(stopped).map((l) => l.status)).toEqual(["rejected", "not run"]);
    const queued = { state: "queued", current_node: null, nodes, outcomes: [] } as never;
    expect(tuneupLines(queued).map((l) => l.status)).toEqual(["waiting", "waiting"]);
  });
});

describe("click-to-set (ADR 0053)", () => {
  it("turns a clicked point into levels for the stand's DC channels and names what it skips", () => {
    const dc = standChannels(stand).dc;
    const { levels, skipped } = setpointFor([{ name: "P1", value: 0.05 }, { name: "P2", value: 0.1 }, { name: "V_sd", value: 1e-3 }, { name: "SG", value: NaN }], dc);
    expect(levels).toEqual([{ channel: "P1", value: 0.05 }, { channel: "P2", value: 0.1 }]);
    expect(skipped).toEqual(["V_sd", "SG"]);
  });
});
