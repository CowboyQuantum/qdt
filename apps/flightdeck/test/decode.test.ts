import { describe, expect, it } from "vitest";
import { ReplaySource } from "../src/sources/replay";
import { consume } from "../src/sources/source";
import { decodeChunk, decodeText, payloadShapes } from "../src/stream/decode";
import { parseRecording } from "../src/stream/recording";
import { DatasetStore } from "../src/stream/store";
import type { Dataset } from "../src/schema/data";
import { expectMatchesOracle, FIXTURE_NAMES, oracle, recording } from "./helpers";

describe.each(FIXTURE_NAMES)("fixture %s", (name) => {
  it("decodes to the Python reference content bit-for-bit", async () => {
    const stores = await consume(new ReplaySource(recording(name), name));
    const o = oracle(name);
    expect([...stores.keys()]).toEqual([o.dataset_id]);
    expectMatchesOracle(stores.get(o.dataset_id)!, o);
  });
});

function mapDataset(): Dataset {
  const first = parseRecording(recording("synthetic_map_64"))[0] as string;
  const msg = decodeText(first);
  if (msg.type !== "dataset") throw new Error("expected dataset");
  return msg.dataset;
}

describe("payloadShapes (port of Dataset.payload_shapes)", () => {
  const ds = mapDataset();
  const chunk = (region: [string, number, number][], variables = ["signal"]) => ({
    dataset_id: ds.dataset_id,
    seq: 0,
    region: region.map(([dim, start, stop]) => ({ dim, start, stop, schema_version: 1 })) as never,
    variables: variables as never,
    explicit_coords: [],
    produced_at: "2026-10-11T00:00:00Z",
    final: false,
    schema_version: 1,
  });

  it("follows the variable's dim order, not the region's", () => {
    const shapes = payloadShapes(ds, chunk([["gate_inner", 0, 64], ["gate_outer", 3, 5]]));
    expect(shapes.get("signal")).toEqual([2, 64]);
  });

  it.each([
    [[["gate_outer", 0, 1], ["gate_inner", 0, 65]], ["signal"], /exceeds/],
    [[["gate_outer", 0, 1]], ["signal"], /spans/],
    [[["gate_outer", 0, 1], ["gate_inner", 0, 8]], ["nope"], /unknown variable/],
    [[["gate_outer", 0, 1], ["other", 0, 1]], ["signal"], /unknown dimension/],
  ] as const)("rejects %j / %j", (region, vars, err) => {
    expect(() => payloadShapes(ds, chunk(region as never, vars as never))).toThrow(err);
  });
});

describe("decodeChunk", () => {
  it("rejects a payload whose dtype disagrees with the definition", () => {
    const ds = mapDataset();
    const wrong = { ...ds, data_vars: [{ ...ds.data_vars[0]!, dtype: "float64" as const }] } as Dataset;
    const firstChunk = parseRecording(recording("synthetic_map_64")).find((m) => typeof m !== "string")!;
    expect(() => decodeChunk(firstChunk as Uint8Array, wrong)).toThrow(/expected Float64Array/);
  });
});

describe("recordings", () => {
  it("rejects non-recordings and truncated files", () => {
    expect(() => parseRecording(new TextEncoder().encode("not a recording"))).toThrow(/not a qdt/);
    const good = recording("synthetic_map_64");
    expect(() => parseRecording(good.subarray(0, good.length - 10))).toThrow(/truncated/);
  });
});

describe("DatasetStore", () => {
  const ds = (): Dataset =>
    ({
      dataset_id: "g",
      name: "growing",
      schema_version: 1,
      dims: [
        { name: "record", size: null, schema_version: 1 },
        { name: "t", size: 3, schema_version: 1 },
      ],
      coords: [],
      data_vars: [{ name: "v", dims: ["record", "t"], unit: "", dtype: "float64", schema_version: 1 }],
      attrs: {},
      source: { kind: "synthetic", label: "", registry_ref: null, schema_version: 1 },
      created_at: "2026-10-11T00:00:00Z",
    }) as Dataset;
  const frame = (k: number) => ({
    chunk: {
      dataset_id: "g",
      seq: k,
      region: [
        { dim: "record", start: k, stop: k + 1, schema_version: 1 },
        { dim: "t", start: 0, stop: 3, schema_version: 1 },
      ] as never,
      variables: ["v"] as never,
      explicit_coords: [],
      produced_at: "2026-10-11T00:00:00Z",
      final: false,
      schema_version: 1,
    },
    arrays: { v: { values: Float64Array.of(k, k + 0.5, -k), shape: [1, 3] } },
  });

  it("grows an unbounded leading dimension and keeps earlier rows", () => {
    const store = new DatasetStore(ds());
    for (let k = 0; k < 50; k++) store.apply(frame(k));
    const v = store.get("v");
    expect(v.shape).toEqual([50, 3]);
    expect(Array.from(v.values.subarray(0, 3) as Float64Array)).toEqual([0, 0.5, -0]);
    expect(Array.from(v.values.subarray(49 * 3) as Float64Array)).toEqual([49, 49.5, -49]);
  });

  it("rejects out-of-order chunks", () => {
    const store = new DatasetStore(ds());
    expect(() => store.apply(frame(1))).toThrow(/out-of-order/);
  });
});
