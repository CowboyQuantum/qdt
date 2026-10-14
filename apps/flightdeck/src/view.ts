// View selection and the coordinate system shared by data and annotations. Chosen from the Dataset's
// *shape* only — never from its source or producer (rule 8).
import type { Annotation, Dataset } from "./schema/data";
import type { DenseArray, DatasetStore } from "./stream/store";

export type ViewKind =
  /** `stackDim`: a leading dimension the map is averaged over on display (repeated scans). */
  | { kind: "heatmap"; variable: string; rowDim: string; colDim: string; stackDim: string | null }
  | { kind: "trace"; variable: string; xDim: string; latestAlong: string | null };

/** The view for `variable` (default: the first data variable), chosen from its dims and their sizes. */
export function chooseView(dataset: Dataset, variable?: string): ViewKind | null {
  const v = dataset.data_vars.find((x) => x.name === variable) ?? dataset.data_vars[0];
  if (!v) return null;
  const size = (d: string) => dataset.dims.find((x) => x.name === d)!.size;
  if (v.dims.length === 1) return { kind: "trace", variable: v.name, xDim: v.dims[0], latestAlong: null };
  if (v.dims.length === 2) {
    const [a, b] = v.dims as [string, string];
    if (size(a) != null && size(b) != null)
      return { kind: "heatmap", variable: v.name, rowDim: a, colDim: b, stackDim: null };
    if (size(a) == null && size(b) != null) return { kind: "trace", variable: v.name, xDim: b, latestAlong: a };
  }
  if (v.dims.length === 3) {
    const [s, a, b] = v.dims as [string, string, string];
    if (size(a) != null && size(b) != null)
      return { kind: "heatmap", variable: v.name, rowDim: a, colDim: b, stackDim: s };
  }
  return null;
}

/** Variables that can be subtracted from `name` cell by cell: same dims, same unit. */
export function partners(dataset: Dataset, name: string): string[] {
  const v = dataset.data_vars.find((x) => x.name === name);
  if (!v) return [];
  return dataset.data_vars
    .filter((x) => x.name !== name && x.unit === v.unit && x.dims.join() === v.dims.join())
    .map((x) => x.name);
}

/** `a − b` cell by cell into `out` (reused when its length fits); an unwritten (NaN) cell stays NaN.
 * The client-side difference view: any two variables of one Dataset (ADR 0037). */
export function difference(a: DenseArray, b: DenseArray, out: Float64Array | null): DenseArray {
  const n = a.values.length;
  const values = out?.length === n ? out : new Float64Array(n);
  for (let i = 0; i < n; i++) values[i] = Number(a.values[i]) - Number(b.values[i] ?? NaN);
  return { values, shape: a.shape, dims: a.dims };
}

/** Mean over the leading axis of a (stack, rows, cols) array into `out` (rows × cols), for rows
 * [r0, r1) only, ignoring unwritten (NaN) cells; a cell no slice has written stays NaN. */
export function meanAlongLeading(data: DenseArray, r0: number, r1: number, out: Float64Array): void {
  const [n, rows, cols] = data.shape as [number, number, number];
  const plane = rows * cols;
  for (let i = r0 * cols; i < r1 * cols; i++) {
    let sum = 0;
    let count = 0;
    for (let k = 0; k < n; k++) {
      const x = Number(data.values[k * plane + i]!);
      if (x === x) {
        sum += x;
        count++;
      }
    }
    out[i] = count ? sum / count : NaN;
  }
}

/** Coordinate values labelling `dim`, or plain indices if the Dataset defines none. */
export function axis(store: DatasetStore, dim: string): { name: string; unit: string; values: ArrayLike<number> } {
  const c = store.dataset.coords.find((x) => x.dim === dim);
  if (!c) {
    const n = store.dataset.dims.find((d) => d.name === dim)!.size ?? 0;
    return { name: dim, unit: "", values: Float64Array.from({ length: n }, (_, i) => i) };
  }
  return { name: c.name, unit: c.unit, values: store.get(c.name).values as ArrayLike<number> };
}

/** Client-side view options (FINISH_LINE: transforms as toggles, no round trip). */
export type Transform = "raw" | "d_col" | "d_row" | "grad";
export interface ViewOptions {
  /** Draw the row dimension horizontally and the column dimension vertically. */
  swap: boolean;
  transform: Transform;
}
export const DEFAULT_OPTIONS: ViewOptions = { swap: false, transform: "raw" };

/** Transform a (rows × cols) map into `out`: derivative along columns or rows (per index step) or
 * the gradient magnitude; `raw` copies. Pure, NaN-aware; unwritten cells stay NaN. */
export function transformMap(
  values: ArrayLike<number | bigint>,
  rows: number,
  cols: number,
  transform: Transform,
  out: Float64Array,
): Float64Array {
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const i = r * cols + c;
      switch (transform) {
        case "raw":
          out[i] = Number(values[i]);
          break;
        case "d_col":
          out[i] = diffAt(values, i, 1, c, cols);
          break;
        case "d_row":
          out[i] = diffAt(values, i, cols, r, rows);
          break;
        case "grad": {
          const dc = diffAt(values, i, 1, c, cols);
          const dr = diffAt(values, i, cols, r, rows);
          out[i] = Number.isNaN(dc) || Number.isNaN(dr) ? NaN : Math.hypot(dc, dr);
          break;
        }
      }
    }
  }
  return out;
}

/** Central difference at flat index i along an axis of length `len` where `pos` is the index on that
 * axis and `stride` the flat step; one-sided at the ends and next to NaN cells. */
function diffAt(v: ArrayLike<number | bigint>, i: number, stride: number, pos: number, len: number): number {
  const here = Number(v[i]);
  if (Number.isNaN(here)) return NaN; // an unwritten cell stays unwritten
  const prev = pos > 0 ? Number(v[i - stride]) : NaN;
  const next = pos < len - 1 ? Number(v[i + stride]) : NaN;
  const hasPrev = !Number.isNaN(prev);
  const hasNext = !Number.isNaN(next);
  if (hasPrev && hasNext) return (next - prev) / 2;
  if (hasNext) return next - here;
  if (hasPrev) return here - prev;
  return NaN;
}

/** `out[c * rows + r] = values[r * cols + c]`: the map with its axes swapped (cols × rows). */
export function transpose(values: ArrayLike<number | bigint>, rows: number, cols: number, out: Float64Array): Float64Array {
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) out[c * rows + r] = Number(values[r * cols + c]);
  return out;
}

/** Map an annotation's points to [x, y] fractions of the heatmap (0..1, y up), or null if not in this
 * view. With `swap`, the row coordinate is x and the column coordinate is y, as the map is drawn. */
export function annotationPath(
  store: DatasetStore,
  view: Extract<ViewKind, { kind: "heatmap" }>,
  ann: Annotation,
  swap = false,
): [number, number][] | null {
  const x = axis(store, swap ? view.rowDim : view.colDim);
  const y = axis(store, swap ? view.colDim : view.rowDim);
  const xi = ann.coords.indexOf(x.name);
  const yi = ann.coords.indexOf(y.name);
  if (xi < 0 || yi < 0) return null;
  const frac = (vals: ArrayLike<number>, v: number) => {
    const n = vals.length;
    const lo = vals[0]!;
    const hi = vals[n - 1]!;
    // cell centres: index i spans [i, i+1) of n cells
    return n > 1 ? ((v - lo) / (hi - lo)) * ((n - 1) / n) + 0.5 / n : 0.5;
  };
  return ann.points.map((p) => [frac(x.values, p[xi]!), frac(y.values, p[yi]!)]);
}
