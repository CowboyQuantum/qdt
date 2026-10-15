import { describe, expect, it } from "vitest";
import type { Dataset } from "../src/schema/data";
import { annotationPath, chooseView, difference, meanAlongLeading, partners, transformMap, transpose } from "../src/view";
import { DatasetStore } from "../src/stream/store";

const dataset = (dims: [string, number | null][], varDims: string[]): Dataset =>
  ({
    dataset_id: "d",
    name: "d",
    dims: dims.map(([name, size]) => ({ name, size })),
    coords: [],
    data_vars: [{ name: "I", dims: varDims, unit: "A", dtype: "float64" }],
  }) as unknown as Dataset;

describe("chooseView", () => {
  it("shows a 2-D map as a plain heatmap", () => {
    const v = chooseView(dataset([["y", 4], ["x", 5]], ["y", "x"]));
    expect(v).toEqual({ kind: "heatmap", variable: "I", rowDim: "y", colDim: "x", stackDim: null });
  });

  it("averages a map stacked along a leading dimension, bounded or not", () => {
    for (const size of [3, null]) {
      const v = chooseView(dataset([["k", size], ["y", 4], ["x", 5]], ["k", "y", "x"]));
      expect(v).toEqual({ kind: "heatmap", variable: "I", rowDim: "y", colDim: "x", stackDim: "k" });
    }
  });
});

describe("meanAlongLeading", () => {
  it("averages only the requested rows and skips unwritten cells", () => {
    // 3 slices of a 2×2 map; slice 2 is half written (an in-progress pass)
    const values = Float64Array.from([1, 2, 3, 4, 3, 4, 5, 6, 5, NaN, NaN, NaN]);
    const out = new Float64Array(4).fill(-1);
    meanAlongLeading({ values, shape: [3, 2, 2], dims: ["k", "y", "x"] }, 0, 1, out);
    expect([...out]).toEqual([3, 3, -1, -1]);
    meanAlongLeading({ values, shape: [3, 2, 2], dims: ["k", "y", "x"] }, 1, 2, out);
    expect([...out]).toEqual([3, 3, 4, 5]);
  });

  it("leaves a cell no slice has written as NaN", () => {
    const out = new Float64Array(1);
    meanAlongLeading({ values: Float64Array.from([NaN, NaN]), shape: [2, 1, 1], dims: ["k", "y", "x"] }, 0, 1, out);
    expect(out[0]).toBeNaN();
  });
});


describe("view options", () => {
  // a 3 × 4 map: value = 10·row + col, so d/d(col) = 1, d/d(row) = 10 everywhere
  const rows = 3;
  const cols = 4;
  const map = Float64Array.from({ length: rows * cols }, (_, i) => 10 * Math.floor(i / cols) + (i % cols));

  it("differentiates along either axis in index units, one-sided at the edges", () => {
    const out = new Float64Array(rows * cols);
    expect([...transformMap(map, rows, cols, "d_col", out)]).toEqual(new Array(rows * cols).fill(1));
    expect([...transformMap(map, rows, cols, "d_row", out)]).toEqual(new Array(rows * cols).fill(10));
    expect([...transformMap(map, rows, cols, "grad", out)].every((v) => Math.abs(v - Math.hypot(1, 10)) < 1e-12)).toBe(true);
    expect([...transformMap(map, rows, cols, "raw", out)]).toEqual([...map]);
  });

  it("keeps unwritten (NaN) cells NaN and steps around them", () => {
    const m = Float64Array.from(map);
    m[5] = NaN; // row 1, col 1
    const out = transformMap(m, rows, cols, "d_col", new Float64Array(rows * cols));
    expect(out[5]).toBeNaN(); // the unwritten cell itself
    expect(out[4]).toBeNaN(); // row 1, col 0: no left neighbour and the right one is unwritten
    expect(out[6]).toBe(1); // row 1, col 2: one-sided to the right, away from the NaN
    expect(out[7]).toBe(1); // row 1, col 3: the right edge, one-sided
  });

  it("transposes so the row dimension runs along x", () => {
    const t = transpose(map, rows, cols, new Float64Array(rows * cols));
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) expect(t[c * rows + r]).toBe(map[r * cols + c]);
  });

  it("swaps the overlay mapping with the map", () => {
    const ds = {
      dataset_id: "d",
      name: "d",
      dims: [{ name: "P1", size: 2 }, { name: "P2", size: 4 }],
      coords: [
        { kind: "linear", name: "P1", dim: "P1", unit: "V", start: 0, stop: 1, num: 2 },
        { kind: "linear", name: "P2", dim: "P2", unit: "V", start: 0, stop: 3, num: 4 },
      ],
      data_vars: [{ name: "I", dims: ["P1", "P2"], unit: "A", dtype: "float64" }],
      source: { kind: "synthetic", label: "", registry_ref: null },
      created_at: "2026-10-13T00:00:00Z",
    } as unknown as Dataset;
    const store = new DatasetStore(ds);
    const view = chooseView(ds)!;
    if (view.kind !== "heatmap") throw new Error("heatmap expected");
    const ann = { annotation_id: "a", dataset_id: "d", kind: "marker", coords: ["P1", "P2"], points: [[1, 3]], label: "", attrs: {} } as never;
    const [plain] = annotationPath(store, view, ann)!;
    const [swapped] = annotationPath(store, view, ann, true)!;
    expect(plain).toEqual([swapped![1], swapped![0]]);
  });
});

describe("variables and the difference view (ADR 0037)", () => {
  const ds = {
    dataset_id: "d",
    name: "d",
    dims: [{ name: "y", size: 2 }, { name: "x", size: 3 }],
    coords: [],
    data_vars: [
      { name: "I_on", dims: ["y", "x"], unit: "A", dtype: "float64" },
      { name: "I_off", dims: ["y", "x"], unit: "A", dtype: "float64" },
      { name: "dI", dims: ["y", "x"], unit: "A", dtype: "float64" },
      { name: "V", dims: ["y", "x"], unit: "V", dtype: "float64" },
      { name: "line", dims: ["x"], unit: "A", dtype: "float64" },
    ],
  } as unknown as Dataset;

  it("views the chosen variable, the first one by default or for an unknown name", () => {
    expect(chooseView(ds)).toMatchObject({ kind: "heatmap", variable: "I_on" });
    expect(chooseView(ds, "dI")).toMatchObject({ kind: "heatmap", variable: "dI" });
    expect(chooseView(ds, "line")).toMatchObject({ kind: "trace", variable: "line" });
    expect(chooseView(ds, "nope")).toMatchObject({ variable: "I_on" });
  });

  it("offers partners with the same dims and unit only", () => {
    expect(partners(ds, "I_on")).toEqual(["I_off", "dI"]);
    expect(partners(ds, "line")).toEqual([]);
    expect(partners(ds, "nope")).toEqual([]);
  });

  it("subtracts cell by cell, keeps unwritten cells NaN, and reuses its buffer", () => {
    const a = { values: Float64Array.from([1, 2, NaN, 4]), shape: [2, 2], dims: ["y", "x"] };
    const b = { values: Float64Array.from([0.5, 3, 1, NaN]), shape: [2, 2], dims: ["y", "x"] };
    const out = new Float64Array(4);
    const d = difference(a, b, out);
    expect(d.values).toBe(out);
    expect([...d.values]).toEqual([0.5, -1, NaN, NaN]);
    expect(d.shape).toEqual([2, 2]);
    expect(difference(a, b, null).values).not.toBe(out);
  });
});

describe("chooseView on records (ADR 0047)", () => {
  const records = (recordSize: number | null): Dataset =>
    ({
      dataset_id: "d",
      name: "d",
      dims: [{ name: "record", size: recordSize }, { name: "time", size: 100 }],
      coords: [{ kind: "linear", name: "time", dim: "time", unit: "s", start: 0, stop: 1, num: 100 }],
      data_vars: [{ name: "trace", dims: ["record", "time"], unit: "V", dtype: "float64" }],
    }) as unknown as Dataset;

  it("shows a bounded (record, time) variable as a trace of the latest record, like an unbounded one", () => {
    for (const size of [4, null]) {
      expect(chooseView(records(size))).toEqual({ kind: "trace", variable: "trace", xDim: "time", latestAlong: "record" });
    }
  });

  it("keeps a map over two coordinated dims a heatmap, even one whose inner axis is time", () => {
    const ds = records(4);
    (ds.coords as unknown[]).push({ kind: "linear", name: "record", dim: "record", unit: "V", start: 0, stop: 1, num: 4 });
    expect(chooseView(ds)).toMatchObject({ kind: "heatmap", rowDim: "record", colDim: "time" });
  });
});
