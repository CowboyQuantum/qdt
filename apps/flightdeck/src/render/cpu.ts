// CPU reference renderer for a 2D map: the oracle for snapshot tests and the fallback without WebGL2.
// Orientation: outer (row) index 0 at the bottom, inner (column) index 0 at the left.
import type { TypedArray } from "../stream/decode";
import { MISSING, viridis } from "./colormap";

export interface Range {
  min: number;
  max: number;
}

/** Finite min/max of `values`, or null when nothing finite has arrived yet. */
export function finiteRange(values: TypedArray): Range | null {
  let min = Infinity;
  let max = -Infinity;
  for (let i = 0; i < values.length; i++) {
    const v = Number(values[i]);
    if (v < min) min = v;
    if (v > max) max = v;
  }
  return min <= max ? { min, max } : null;
}

export function renderRGBA(values: TypedArray, shape: [number, number], range: Range): Uint8ClampedArray {
  const [rows, cols] = shape;
  const out = new Uint8ClampedArray(rows * cols * 4);
  const span = range.max - range.min || 1;
  for (let r = 0; r < rows; r++) {
    const y = rows - 1 - r; // image row 0 is the top
    for (let c = 0; c < cols; c++) {
      const v = Number(values[r * cols + c]);
      const px = Number.isNaN(v) ? MISSING : viridis((v - range.min) / span);
      out.set(px, (y * cols + c) * 4);
    }
  }
  return out;
}
