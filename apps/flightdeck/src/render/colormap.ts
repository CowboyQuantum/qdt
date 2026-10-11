// Viridis via a 6th-order polynomial fit — the same formula in the GLSL shader and the CPU reference,
// so the CPU path is a faithful oracle for the GPU path's colours.
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
