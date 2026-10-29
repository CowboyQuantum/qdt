// The Device widget's pure model (ADR 0089, #164): a device's gates seen from above, to scale, each
// coloured by the DC level it sits at. The layout is the stand server's (`GET /device/layout`); the
// levels are `sittingLevels` over `GET /levels/state` (the held level, else the setpoint). Nothing here
// touches the DOM: the widget turns these numbers into SVG.
import { colormap, type Colormap } from "../render/colormap";
import type { DeviceLayout } from "../schema/api";

/** A rectangle in the layout's nanometres, y up. */
export interface Box {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

/** The voltage range the colours span. */
export interface Range {
  lo: number;
  hi: number;
}

/** How one gate is drawn: its level (null when no channel or no level), fill and text colours, and
 * where its label goes. */
export interface GatePaint {
  name: string;
  role: string;
  channel: string | null;
  level: number | null;
  fill: string | null;
  ink: string;
  path: string;
  centre: [number, number];
  /** Label along the gate's long side: true for a gate taller than it is wide. */
  vertical: boolean;
  /** The gate's extent in nanometres: [width, height]. */
  size: [number, number];
}

/** A label that fits inside its gate: the lines to write and the font size in nanometres. */
export interface LabelFit {
  lines: string[];
  fontNm: number;
}

/** The fullest label that fits inside a gate of `size` nm drawn at `pxPerNm`, at no more than `maxPx`
 * and no less than `minPx` on screen: the name and level, else the name alone, else none (the legend
 * and the tooltip still carry both). A gate taller than wide writes along its height. Pure. */
export function labelFit(size: readonly [number, number], vertical: boolean, name: string, level: string, pxPerNm: number, maxPx = 12, minPx = 7): LabelFit | null {
  if (!(pxPerNm > 0)) return null;
  const along = (vertical ? size[1] : size[0]) * pxPerNm * 0.9;
  const across = (vertical ? size[0] : size[1]) * pxPerNm * 0.9;
  const tries = vertical ? [[`${name}  ${level}`], [name]] : [[name, level], [`${name}  ${level}`], [name]];
  for (const lines of tries) {
    const chars = Math.max(...lines.map((l) => l.length));
    const px = Math.min(maxPx, across / (lines.length * 1.25), along / (chars * 0.62));
    if (px >= minPx) return { lines, fontNm: px / pxPerNm };
  }
  return null;
}

/** Every gate, the channel and the sensor island, in nanometres, grown by `margin` on each side. Pure. */
export function layoutBounds(layout: DeviceLayout, margin = 20): Box {
  const xs: number[] = [];
  const ys: number[] = [];
  for (const g of layout.gates) for (const [x, y] of g.polygon_nm) xs.push(x), ys.push(y);
  for (const r of [layout.channel_nm, layout.sensor_nm]) if (r) xs.push(r[0], r[1]), ys.push(r[2], r[3]);
  return { x0: Math.min(...xs) - margin, x1: Math.max(...xs) + margin, y0: Math.min(...ys) - margin, y1: Math.max(...ys) + margin };
}

/** The colour range over these levels; a single level (or all equal) is widened to ±0.05 V so it
 * still maps to the middle of the colormap. Null when there is no level. Pure. */
export function levelRange(levels: readonly number[]): Range | null {
  const finite = levels.filter((v) => Number.isFinite(v));
  if (!finite.length) return null;
  const lo = Math.min(...finite);
  const hi = Math.max(...finite);
  return hi - lo > 1e-9 ? { lo, hi } : { lo: lo - 0.05, hi: hi + 0.05 };
}

/** A level's place in the range, clamped to [0, 1]. Pure. */
export function rangeFraction(v: number, r: Range): number {
  return Math.min(1, Math.max(0, (v - r.lo) / (r.hi - r.lo)));
}

/** A scale bar about a fifth of `widthNm` long, rounded down to 1, 2 or 5 × 10^k nanometres. Pure. */
export function scaleBarNm(widthNm: number): number {
  const target = widthNm / 5;
  if (!(target > 0)) return 0;
  const decade = 10 ** Math.floor(Math.log10(target));
  for (const m of [5, 2, 1]) if (m * decade <= target) return m * decade;
  return decade;
}

/** SVG path data for an outline in the layout's frame: y is flipped, since SVG's y points down. Pure. */
export function pathOf(polygon: readonly (readonly [number, number])[]): string {
  return polygon.map(([x, y], i) => `${i ? "L" : "M"}${x} ${-y}`).join(" ") + " Z";
}

/** The SVG viewBox of `box` (y flipped, as `pathOf`). Pure. */
export function viewBoxOf(box: Box): string {
  return `${box.x0} ${-box.y1} ${box.x1 - box.x0} ${box.y1 - box.y0}`;
}

const hex = (c: number) => c.toString(16).padStart(2, "0");

/** The CSS colour of `t` on `cmap`. Pure. */
export function cssColour(cmap: Colormap, t: number): string {
  const [r, g, b] = colormap(cmap, t);
  return `#${hex(r)}${hex(g)}${hex(b)}`;
}

/** Black or white, whichever reads better on `fill` (`#rrggbb`), by relative luminance. Pure. */
export function inkOn(fill: string): string {
  const lin = (i: number) => {
    const c = parseInt(fill.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const lum = 0.2126 * lin(1) + 0.7152 * lin(3) + 0.0722 * lin(5);
  return lum > 0.179 ? "#000000" : "#ffffff";
}

/** A gate's level for its label: volts to three decimals, or a dash. Pure. */
export function levelText(v: number | null): string {
  return v === null ? "—" : `${v.toFixed(3)} V`;
}

/** Colour stops for a CSS linear-gradient of `cmap` from the low end to the high end. Pure. */
export function gradientStops(cmap: Colormap, n = 11): string {
  return Array.from({ length: n }, (_, i) => `${cssColour(cmap, i / (n - 1))} ${((100 * i) / (n - 1)).toFixed(0)}%`).join(", ");
}

/** How every gate is drawn at these levels (channel → volts), and the range the colours span. A gate
 * whose channel is null or has no level gets no fill. Pure. */
export function paint(layout: DeviceLayout, levels: Readonly<Record<string, number>>, cmap: Colormap): { gates: GatePaint[]; range: Range | null } {
  const levelOf = (channel: string | null | undefined) => (channel && Number.isFinite(levels[channel]) ? levels[channel]! : null);
  const range = levelRange(layout.gates.map((g) => levelOf(g.channel)).filter((v): v is number => v !== null));
  const gates = layout.gates.map((g): GatePaint => {
    const level = levelOf(g.channel);
    const fill = level !== null && range ? cssColour(cmap, rangeFraction(level, range)) : null;
    const xs = g.polygon_nm.map((p) => p[0]);
    const ys = g.polygon_nm.map((p) => p[1]);
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    return {
      name: g.name,
      role: g.role,
      channel: g.channel ?? null,
      level,
      fill,
      ink: fill ? inkOn(fill) : "currentColor",
      path: pathOf(g.polygon_nm),
      centre: [(x0 + x1) / 2 || 0, -(y0 + y1) / 2 || 0],
      vertical: y1 - y0 > x1 - x0,
      size: [x1 - x0, y1 - y0],
    };
  });
  return { gates, range };
}
