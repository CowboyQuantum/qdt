// Colormaps (ADR 0012, 0061). Viridis is a 6th-order polynomial fit, the same formula in the GLSL shader
// and the CPU reference, so the CPU path is a faithful oracle for the GPU path's colours. The others are
// anchor tables sampled into a 256-entry LUT that both renderers read the same way (the GPU as a LINEAR
// 256×1 texture, the CPU by the same linear interpolation), so the oracle holds for them too.
export const VIRIDIS: readonly (readonly [number, number, number])[] = [
  [0.2777273272234177, 0.005407344544966578, 0.3340998053353061],
  [0.1050930431085774, 1.404613529898575, 1.384590162594685],
  [-0.3308618287255563, 0.214847559468213, 0.09509516302823659],
  [-4.634230498983486, -5.799100973351585, -19.33244095627987],
  [6.228269936347081, 14.17993336680509, 56.69055260068105],
  [4.776384997670288, -13.74514537774601, -65.35303263337234],
  [-5.435455855934631, 4.645852612178535, 26.3124352495832],
];

/** NaN (unwritten) cells render as this RGBA. */
export const MISSING: readonly [number, number, number, number] = [40, 40, 40, 255];

/** t in [0, 1] (clamped) -> RGBA bytes. */
export function viridis(t: number): [number, number, number, number] {
  const x = Math.min(1, Math.max(0, t));
  const rgb = [0, 1, 2].map((ch) => {
    let v = 0;
    for (let k = VIRIDIS.length - 1; k >= 0; k--) v = v * x + VIRIDIS[k]![ch]!;
    return Math.round(Math.min(1, Math.max(0, v)) * 255);
  });
  return [rgb[0]!, rgb[1]!, rgb[2]!, 255];
}

export const GLSL_VIRIDIS = `
vec3 viridis(float t) {
  t = clamp(t, 0.0, 1.0);
  ${VIRIDIS.map((c, k) => `const vec3 c${k} = vec3(${c.map((x) => x.toFixed(16)).join(", ")});`).join("\n  ")}
  return clamp(c0 + t*(c1 + t*(c2 + t*(c3 + t*(c4 + t*(c5 + t*c6))))), 0.0, 1.0);
}`;

export const COLORMAPS = ["viridis", "magma", "grey"] as const;
export type Colormap = (typeof COLORMAPS)[number];

/** Evenly spaced anchors (t = 0 … 1) of matplotlib's magma, in RGB bytes; linear between them. */
const MAGMA: readonly (readonly [number, number, number])[] = [
  [0, 0, 4],
  [28, 16, 68],
  [79, 18, 123],
  [129, 37, 129],
  [181, 54, 122],
  [229, 80, 100],
  [251, 135, 97],
  [254, 194, 135],
  [252, 253, 191],
];
const GREY: readonly (readonly [number, number, number])[] = [
  [0, 0, 0],
  [255, 255, 255],
];
const ANCHORS: Record<Exclude<Colormap, "viridis">, readonly (readonly [number, number, number])[]> = { magma: MAGMA, grey: GREY };

/** The 256-entry RGBA table a non-viridis colormap is drawn from, on both renderers. */
export function lut(name: Exclude<Colormap, "viridis">): Uint8Array {
  const anchors = ANCHORS[name];
  const out = new Uint8Array(256 * 4);
  for (let i = 0; i < 256; i++) {
    const x = (i / 255) * (anchors.length - 1);
    const k = Math.min(anchors.length - 2, Math.floor(x));
    const f = x - k;
    for (let ch = 0; ch < 3; ch++) out[i * 4 + ch] = Math.round(anchors[k]![ch]! * (1 - f) + anchors[k + 1]![ch]! * f);
    out[i * 4 + 3] = 255;
  }
  return out;
}

const LUTS = new Map<string, Uint8Array>();
const lutOf = (name: Exclude<Colormap, "viridis">) => {
  let l = LUTS.get(name);
  if (!l) LUTS.set(name, (l = lut(name)));
  return l;
};

/** t in [0, 1] (clamped) → RGBA bytes for `name`: the polynomial for viridis, the LUT with linear
 * interpolation between its entries otherwise (what a LINEAR texture sample does on the GPU). */
export function colormap(name: Colormap, t: number): [number, number, number, number] {
  if (name === "viridis") return viridis(t);
  const l = lutOf(name);
  const x = Math.min(1, Math.max(0, t)) * 255;
  const i = Math.min(254, Math.floor(x));
  const f = x - i;
  const at = (ch: number) => Math.round(l[i * 4 + ch]! * (1 - f) + l[(i + 1) * 4 + ch]! * f);
  return [at(0), at(1), at(2), 255];
}
