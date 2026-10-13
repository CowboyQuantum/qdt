// View selection and the coordinate system shared by data and annotations. Chosen from the Dataset's
// *shape* only — never from its source or producer (rule 8).
import type { Annotation, Dataset } from "./schema/data";
import type { DenseArray, DatasetStore } from "./stream/store";

export type ViewKind =
  /** `stackDim`: a leading dimension the map is averaged over on display (repeated scans). */
  | { kind: "heatmap"; variable: string; rowDim: string; colDim: string; stackDim: string | null }
  | { kind: "trace"; variable: string; xDim: string; latestAlong: string | null };

export function chooseView(dataset: Dataset): ViewKind | null {
  const v = dataset.data_vars[0];
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

/** Map an annotation's points to [x, y] fractions of the heatmap (0..1, y up), or null if not in this view. */
export function annotationPath(
  store: DatasetStore,
  view: Extract<ViewKind, { kind: "heatmap" }>,
  ann: Annotation,
): [number, number][] | null {
  const x = axis(store, view.colDim);
  const y = axis(store, view.rowDim);
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
