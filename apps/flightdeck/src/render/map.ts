// 2D map renderers behind one interface, so the #9 benchmark compares like with like (ADR 0012).
// All take the full row-major map plus a dirty row range; row 0 is drawn at the bottom.
import type { TypedArray } from "../stream/decode";
import { CpuMap, type Range } from "./cpu";
import { WebGL2Map } from "./webgl2";

export interface MapRenderer {
  readonly name: string;
  /** Allocate for a rows x cols map. */
  resize(rows: number, cols: number): void;
  /** Upload rows [r0, r1) of the full row-major map `values`. */
  upload(values: TypedArray, r0: number, r1: number): void;
  draw(range: Range): void;
  /** Block until the last draw is complete (benchmarks only). */
  finish(): void;
  /** The drawn canvas as RGBA, top row first (pixel tests). */
  pixels(): Uint8Array;
  readonly shape: [number, number];
}

// regl was benchmarked as a candidate and rejected (ADR 0013; code at d9909b3).
export const RENDERERS = ["webgl2", "cpu"] as const;
export type RendererName = (typeof RENDERERS)[number];

export function createMapRenderer(name: RendererName, canvas: HTMLCanvasElement): MapRenderer {
  if (name === "webgl2") return new WebGL2Map(canvas);
  return new CpuMap(canvas);
}

/** Preferred renderer, falling back to the CPU path when WebGL2 is unavailable. */
export function defaultMapRenderer(canvas: HTMLCanvasElement): MapRenderer {
  try {
    return new WebGL2Map(canvas);
  } catch {
    return new CpuMap(canvas);
  }
}
