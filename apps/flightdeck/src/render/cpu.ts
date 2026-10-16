// CPU reference renderer for a 2D map: the oracle for snapshot tests and the fallback without WebGL2.
// Orientation: outer (row) index 0 at the bottom, inner (column) index 0 at the left.
import type { TypedArray } from "../stream/decode";
import { MISSING, viridis } from "./colormap";
import type { MapRenderer } from "./map";

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

/** Canvas-2D map renderer: CPU colour mapping of dirty rows into an ImageData (the #9 lower bound and the
 * fallback without WebGL2). A range change re-maps the whole image on the next draw. */
export class CpuMap implements MapRenderer {
  readonly name = "cpu";
  private image: ImageData | null = null;
  private values: TypedArray | null = null;
  private mapped: Range | null = null;
  private rows = 0;
  private cols = 0;

  constructor(private readonly canvas: HTMLCanvasElement) {}

  resize(rows: number, cols: number): void {
    [this.rows, this.cols] = [rows, cols];
    this.canvas.width = cols;
    this.canvas.height = rows;
    this.image = new ImageData(cols, rows);
    this.mapped = null;
  }

  upload(values: TypedArray, r0: number, r1: number): void {
    this.values = values;
    if (this.mapped) this.mapRows(r0, r1, this.mapped);
  }

  draw(range: Range): void {
    if (!this.image || !this.values) return;
    if (!this.mapped || this.mapped.min !== range.min || this.mapped.max !== range.max) {
      this.mapped = range;
      this.mapRows(0, this.rows, range);
    }
    this.canvas.getContext("2d")!.putImageData(this.image, 0, 0);
  }

  finish(): void {}

  dispose(): void {}

  pixels(): Uint8Array {
    const { width: w, height: h } = this.canvas;
    return new Uint8Array(this.canvas.getContext("2d")!.getImageData(0, 0, w, h).data.buffer);
  }

  get shape(): [number, number] {
    return [this.rows, this.cols];
  }

  private mapRows(r0: number, r1: number, range: Range): void {
    const rgba = renderRGBA(this.values!.subarray(r0 * this.cols, r1 * this.cols) as TypedArray, [r1 - r0, this.cols], range);
    // renderRGBA puts its row 0 at the bottom of its block; place the block so map row r0 lands at y = rows-1-r0
    this.image!.data.set(rgba, (this.rows - r1) * this.cols * 4);
  }
}
