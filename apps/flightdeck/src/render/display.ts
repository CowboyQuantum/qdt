// The display map of a heatmap view, in full: the mean over a stack dimension, then the client-side
// transform, then the axis swap (ADR 0037). Pure apart from reusable scratch buffers, so two plot panes
// over the same store compute byte-identical maps (test/render.test.ts: source equivalence across panes).
import type { DenseArray } from "../stream/store";
import type { TypedArray } from "../stream/decode";
import { meanAlongLeading, transformMap, transpose, type ViewOptions } from "../view";
import { finiteRange, type Range } from "./cpu";

export interface Scratch {
  mean: Float64Array | null;
  derived: Float64Array | null;
  swapped: Float64Array | null;
}

export const scratch = (): Scratch => ({ mean: null, derived: null, swapped: null });

export interface DisplayMap {
  values: TypedArray;
  rows: number;
  cols: number;
  range: Range | null;
}

export function displayMap(data: DenseArray, stacked: boolean, o: ViewOptions, s: Scratch): DisplayMap {
  let map: TypedArray = data.values;
  const [rows, cols] = data.shape.slice(-2) as [number, number];
  if (stacked) {
    if (s.mean?.length !== rows * cols) s.mean = new Float64Array(rows * cols).fill(NaN);
    meanAlongLeading(data, 0, rows, s.mean);
    map = s.mean;
  }
  if (o.transform !== "raw") {
    if (s.derived?.length !== rows * cols) s.derived = new Float64Array(rows * cols);
    map = transformMap(map, rows, cols, o.transform, s.derived);
  }
  let [shownRows, shownCols] = [rows, cols];
  if (o.swap) {
    if (s.swapped?.length !== rows * cols) s.swapped = new Float64Array(rows * cols);
    map = transpose(map, rows, cols, s.swapped);
    [shownRows, shownCols] = [cols, rows];
  }
  return { values: map, rows: shownRows, cols: shownCols, range: finiteRange(map) };
}

/** One column of a display map, bottom row first: the line cut a plot pane draws under its map. */
export function columnCut(map: DisplayMap, fraction: number): Float64Array {
  const c = Math.round(Math.min(1, Math.max(0, fraction)) * (map.cols - 1));
  const out = new Float64Array(map.rows);
  for (let r = 0; r < map.rows; r++) out[r] = Number(map.values[r * map.cols + c]);
  return out;
}
