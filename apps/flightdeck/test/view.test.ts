import { describe, expect, it } from "vitest";
import type { Dataset } from "../src/schema/data";
import { chooseView, meanAlongLeading } from "../src/view";

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
