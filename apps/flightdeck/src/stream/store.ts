// Dense, growing client-side copy of one Dataset, assembled from frames (port of qdt_lab.stream.assemble).
// Unwritten cells are NaN (float) or 0 (integer). Unbounded dimensions grow as frames reach them.
import type { Dataset, IndexSlice } from "../schema/data";
import { ARRAY_TYPES, type Frame, type TypedArray } from "./decode";

export interface DenseArray {
  values: TypedArray;
  shape: number[];
  dims: string[];
}

/** Backing storage; `cap` exceeds `shape` only on the leading axis, so a prefix view stays row-major. */
interface Backing {
  buf: TypedArray;
  cap: number[];
  shape: number[];
  dims: string[];
}

export interface Update {
  seq: number;
  region: IndexSlice[];
  final: boolean;
  /** Producer timestamp (ISO 8601) of the chunk, for latency display. */
  producedAt: string;
}

/** numpy.linspace, bit-for-bit: start + i * step, with the last value exactly `stop`. */
export function linspace(start: number, stop: number, num: number): Float64Array {
  const out = new Float64Array(num);
  const step = num > 1 ? (stop - start) / (num - 1) : 0;
  for (let i = 0; i < num; i++) out[i] = i * step + start;
  if (num > 1) out[num - 1] = stop;
  return out;
}

function product(shape: number[]): number {
  return shape.reduce((a, b) => a * b, 1);
}

function allocate(dtype: keyof typeof ARRAY_TYPES, shape: number[]): TypedArray {
  const a = new ARRAY_TYPES[dtype](product(shape));
  if (a instanceof Float32Array || a instanceof Float64Array) a.fill(NaN);
  return a;
}

/** Copy `src` (dense, shape `srcShape`) into `dst` (dense, shape `dstShape`) at `offset`, row by row. */
function writeBlock(dst: TypedArray, dstShape: number[], offset: number[], src: TypedArray, srcShape: number[]) {
  const n = srcShape.length;
  const rowLen = srcShape[n - 1]!;
  const rows = product(srcShape.slice(0, -1));
  const idx = new Array<number>(n - 1).fill(0);
  for (let r = 0; r < rows; r++) {
    let d = 0;
    for (let k = 0; k < n; k++) d = d * dstShape[k]! + (offset[k]! + (k < n - 1 ? idx[k]! : 0));
    (dst as Float64Array).set((src as Float64Array).subarray(r * rowLen, (r + 1) * rowLen), d);
    for (let k = n - 2; k >= 0; k--) {
      if (++idx[k]! < srcShape[k]!) break;
      idx[k] = 0;
    }
  }
}

export class DatasetStore {
  readonly dataset: Dataset;
  readonly annotations = new Map<string, import("../schema/data").Annotation>();
  private readonly arrays = new Map<string, Backing>();
  private readonly sizes = new Map<string, number>();
  private readonly listeners = new Set<(u: Update) => void>();
  private readonly annotationListeners = new Set<(a: import("../schema/data").Annotation) => void>();
  lastSeq = -1;
  complete = false;

  constructor(dataset: Dataset) {
    this.dataset = dataset;
    for (const d of dataset.dims) this.sizes.set(d.name, d.size ?? 0);
    for (const v of dataset.data_vars) {
      const shape = v.dims.map((d) => this.sizes.get(d)!);
      this.arrays.set(v.name, { buf: allocate(v.dtype, shape), cap: shape, shape, dims: [...v.dims] });
    }
    for (const c of dataset.coords) {
      const size = this.sizes.get(c.dim)!;
      let values: TypedArray;
      if (c.kind === "linear") values = linspace(c.start, c.stop, c.num);
      else if (c.kind === "indexed") values = Float64Array.from(c.values);
      else values = allocate(c.dtype, [size]);
      this.arrays.set(c.name, { buf: values, cap: [values.length], shape: [values.length], dims: [c.dim] });
    }
  }

  /** Current contents as a dense row-major view (no copy). */
  get(name: string): DenseArray {
    const a = this.backing(name);
    return { values: a.buf.subarray(0, product(a.shape)) as TypedArray, shape: a.shape, dims: a.dims };
  }

  private backing(name: string): Backing {
    const a = this.arrays.get(name);
    if (!a) throw new Error(`no array ${name}`);
    return a;
  }

  names(): string[] {
    return [...this.arrays.keys()];
  }

  onUpdate(listener: (u: Update) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Add or replace an annotation (re-sending an id replaces it, ADR 0010) and tell the listeners:
   * overlays may arrive long after the last chunk (an analysis of a finished run, Step 4b). */
  addAnnotation(annotation: import("../schema/data").Annotation): void {
    this.annotations.set(annotation.annotation_id, annotation);
    for (const l of this.annotationListeners) l(annotation);
  }

  onAnnotation(listener: (a: import("../schema/data").Annotation) => void): () => void {
    this.annotationListeners.add(listener);
    return () => this.annotationListeners.delete(listener);
  }

  apply(frame: Frame): void {
    const { chunk } = frame;
    if (chunk.seq !== this.lastSeq + 1) {
      throw new Error(`out-of-order chunk: got seq ${chunk.seq} after ${this.lastSeq}`);
    }
    for (const s of chunk.region) if (s.stop > this.sizes.get(s.dim)!) this.grow(s.dim, s.stop);
    const start = new Map(chunk.region.map((s) => [s.dim, s.start]));
    for (const [name, { values, shape }] of Object.entries(frame.arrays)) {
      const dst = this.backing(name);
      writeBlock(dst.buf, dst.cap, dst.dims.map((d) => start.get(d)!), values, shape);
    }
    this.lastSeq = chunk.seq;
    this.complete = chunk.final;
    const update = { seq: chunk.seq, region: chunk.region, final: chunk.final, producedAt: chunk.produced_at };
    for (const l of this.listeners) l(update);
  }

  /** Grow an unbounded dimension to `min`. On the leading axis capacity doubles (amortised O(1) per
   * record); elsewhere the array is re-laid out at the exact size. */
  private grow(dim: string, min: number): void {
    const bounded = this.dataset.dims.find((d) => d.name === dim)!.size != null;
    if (bounded) throw new Error(`region exceeds bounded dimension ${dim}`);
    this.sizes.set(dim, min);
    for (const a of this.arrays.values()) {
      const k = a.dims.indexOf(dim);
      if (k < 0) continue;
      const shape = a.shape.map((n, i) => (i === k ? min : n));
      if (k === 0 && min <= a.cap[0]!) {
        a.shape = shape;
        continue;
      }
      const cap = shape.map((n, i) => (i === 0 && k === 0 ? Math.max(n, 2 * a.cap[0]!, 8) : n));
      const dtype = Object.entries(ARRAY_TYPES).find(([, T]) => a.buf instanceof T)![0];
      const buf = allocate(dtype as keyof typeof ARRAY_TYPES, cap);
      if (product(a.shape) > 0) {
        writeBlock(buf, cap, a.shape.map(() => 0), a.buf.subarray(0, product(a.shape)) as TypedArray, a.shape);
      }
      a.buf = buf;
      a.cap = cap;
      a.shape = shape;
    }
  }
}
