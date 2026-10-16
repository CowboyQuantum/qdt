import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { COLORMAPS, colormap, lut, viridis } from "../src/render/colormap";
import { finiteRange, renderRGBA } from "../src/render/cpu";
import { columnCut, displayMap, scratch } from "../src/render/display";
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

describe("the other colormaps (ADR 0061)", () => {
  it("magma and grey run from dark to light through a 256-entry LUT the CPU and the GPU read alike", () => {
    expect(COLORMAPS).toEqual(["viridis", "magma", "grey"]);
    expect(colormap("grey", 0)).toEqual([0, 0, 0, 255]);
    expect(colormap("grey", 1)).toEqual([255, 255, 255, 255]);
    expect(colormap("grey", 0.5).slice(0, 3)).toEqual([128, 128, 128]);
    expect(colormap("magma", 0)).toEqual([0, 0, 4, 255]);
    expect(colormap("magma", 1)).toEqual([252, 253, 191, 255]);
    const mid = colormap("magma", 0.5);
    expect(mid[0]).toBeGreaterThan(150); // the warm middle of magma
    expect(colormap("magma", -1)).toEqual(colormap("magma", 0)); // clamped
    expect(colormap("viridis", 0.5)).toEqual(viridis(0.5));
    const table = lut("grey");
    expect(table.length).toBe(1024);
    for (let i = 1; i < 256; i++) expect(table[i * 4]!).toBeGreaterThanOrEqual(table[(i - 1) * 4]!); // monotone
    // the CPU path samples the LUT the way a LINEAR texture does: between entries
    expect(colormap("grey", 100.4 / 255).slice(0, 3)).toEqual([100, 100, 100]);
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
    // the default colormap is viridis: the same bytes as asking for it by name
    expect(sha256(new Uint8Array(renderRGBA(map.values, map.shape as [number, number], range, "viridis").buffer) as never)).toBe(sha256(new Uint8Array(rgba.buffer) as never));
  });

  it("draws unwritten (NaN) cells in the missing colour, row 0 at the bottom", () => {
    const values = Float32Array.of(0, 1, NaN, 2); // rows: [0, 1], [NaN, 2]
    const rgba = renderRGBA(values, [2, 2], { min: 0, max: 2 });
    expect(Array.from(rgba.subarray(0, 4))).toEqual([40, 40, 40, 255]); // top-left = row 1, col 0 = NaN
    expect(Array.from(rgba.subarray(8, 12))).toEqual(viridis(0)); // bottom-left = row 0, col 0
  });
});

describe("source equivalence across plot panes (ADR 0055)", () => {
  it("two panes over the same store, each with its own scratch, compute byte-identical display maps and images", async () => {
    const s = await store("synthetic_map_64");
    const data = s.get("signal");
    for (const options of [
      { transform: "raw", swap: false },
      { transform: "grad", swap: true },
      { transform: "d_row", swap: false },
    ] as const) {
      const a = displayMap(data, false, options, scratch());
      const b = displayMap(data, false, options, scratch());
      expect(a.rows).toBe(b.rows);
      expect(a.cols).toBe(b.cols);
      expect(sha256(a.values)).toBe(sha256(b.values));
      expect(a.range).toEqual(b.range);
      expect(sha256(new Uint8Array(renderRGBA(a.values, [a.rows, a.cols], a.range!).buffer) as never)).toBe(
        sha256(new Uint8Array(renderRGBA(b.values, [b.rows, b.cols], b.range!).buffer) as never),
      );
    }
    const raw = displayMap(data, false, { transform: "raw", swap: false }, scratch());
    expect(raw.values).toBe(data.values); // the raw path uploads the store's own buffer
  });

  it("the cut is one column of the display map, bottom row first, at the clamped fraction", () => {
    const values = Float64Array.of(1, 2, 3, 4, 5, 6); // rows [1 2 3] [4 5 6]
    const map = { values, rows: 2, cols: 3, range: { min: 1, max: 6 } };
    expect(Array.from(columnCut(map, 0))).toEqual([1, 4]);
    expect(Array.from(columnCut(map, 0.5))).toEqual([2, 5]);
    expect(Array.from(columnCut(map, 1))).toEqual([3, 6]);
    expect(Array.from(columnCut(map, 7))).toEqual([3, 6]);
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
  // The one permitted read is `dataset.source.registry_ref`, for display only (ADR 0027): a record id,
  // not a producer. Anything else on `.source` (kind, label, the object itself) stays forbidden.
  const FORBIDDEN = /dataset\.source\b(?!\.registry_ref\b)|\.source\.(kind|label)/;

  it("no Flight Deck source reads a Dataset's producer (`.source`) to make decisions", () => {
    const files = readdirSync(new URL("../src", import.meta.url), { recursive: true, encoding: "utf8" })
      .filter((f) => f.endsWith(".ts") && !f.startsWith("schema"));
    for (const f of files) {
      const text = readFileSync(new URL(`../src/${f.replaceAll("\\", "/")}`, import.meta.url), "utf8");
      expect(text, f).not.toMatch(FORBIDDEN);
    }
  });

  it("the guard still catches every read except the registry ref", () => {
    for (const bad of ["dataset.source.kind", "dataset.source", "const { kind } = dataset.source;", "s.source.label"])
      expect(bad).toMatch(FORBIDDEN);
    expect("store.dataset.source.registry_ref").not.toMatch(FORBIDDEN);
  });
});
