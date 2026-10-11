import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { viridis } from "../src/render/colormap";
import { finiteRange, renderRGBA } from "../src/render/cpu";
import { ReplaySource } from "../src/sources/replay";
import { consume } from "../src/sources/source";
import { annotationPath, chooseView } from "../src/view";
import { oracle, recording, sha256 } from "./helpers";

async function store(name: string) {
  const stores = await consume(new ReplaySource(recording(name), name));
  return stores.get(oracle(name).dataset_id)!;
}

describe("colormap", () => {
  it("matches matplotlib viridis at the ends and middle (within fit error)", () => {
    // reference: matplotlib viridis; the 6th-order polynomial fit is within ~4/255
    const close = (a: number[], b: number[]) => a.every((x, i) => Math.abs(x - b[i]!) <= 5);
    const ref: [number, number[]][] = [
      [0, [68, 1, 84]],
      [0.25, [59, 82, 139]],
      [0.5, [33, 145, 140]],
      [0.75, [94, 201, 98]],
      [1, [253, 231, 37]],
    ];
    for (const [t, rgb] of ref) expect(close(viridis(t).slice(0, 3), rgb), `t=${t}`).toBe(true);
  });
});

describe("CPU reference render (oracle for the WebGL path)", () => {
  it("renders the map fixture to a stable image", async () => {
    const s = await store("synthetic_map_64");
    const map = s.get("signal");
    const range = finiteRange(map.values)!;
    const rgba = renderRGBA(map.values, map.shape as [number, number], range);
    expect(rgba.length).toBe(64 * 64 * 4);
    expect(sha256(new Uint8Array(rgba.buffer) as never)).toMatchSnapshot();
  });

  it("draws unwritten (NaN) cells in the missing colour, row 0 at the bottom", () => {
    const values = Float32Array.of(0, 1, NaN, 2); // rows: [0, 1], [NaN, 2]
    const rgba = renderRGBA(values, [2, 2], { min: 0, max: 2 });
    expect(Array.from(rgba.subarray(0, 4))).toEqual([40, 40, 40, 255]); // top-left = row 1, col 0 = NaN
    expect(Array.from(rgba.subarray(8, 12))).toEqual(viridis(0)); // bottom-left = row 0, col 0
  });
});

describe("view selection (by shape only — rule 8)", () => {
  it("maps 2D bounded data to a heatmap and record streams to a latest-record trace", async () => {
    expect(chooseView((await store("synthetic_map_64")).dataset)).toMatchObject({ kind: "heatmap" });
    expect(chooseView((await store("synthetic_records_8")).dataset)).toMatchObject({
      kind: "trace",
      latestAlong: "record",
    });
  });

  it("places the fixture annotation inside the map in data coordinates", async () => {
    const s = await store("synthetic_map_64");
    const view = chooseView(s.dataset)!;
    if (view.kind !== "heatmap") throw new Error("expected heatmap");
    const path = annotationPath(s, view, s.annotations.get("transition-0")!)!;
    expect(path).toHaveLength(2);
    for (const [x, y] of path) for (const f of [x, y]) expect(f >= 0 && f <= 1).toBe(true);
  });
});

describe("rule 8 boundary", () => {
  it("no Flight Deck source reads a Dataset's producer (`.source`) to make decisions", () => {
    const files = readdirSync(new URL("../src", import.meta.url), { recursive: true, encoding: "utf8" })
      .filter((f) => f.endsWith(".ts") && !f.startsWith("schema"));
    for (const f of files) {
      const text = readFileSync(new URL(`../src/${f.replaceAll("\\", "/")}`, import.meta.url), "utf8");
      expect(text, f).not.toMatch(/dataset\.source\b|\.source\.(kind|label)/);
    }
  });
});
