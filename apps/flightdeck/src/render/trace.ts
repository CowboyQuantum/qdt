// 1D trace on canvas-2D (ADR 0008: 1D views may use canvas-2D; <= 1e4 points is trivially fast).
import type { TypedArray } from "../stream/decode";
import { finiteRange } from "./cpu";

/** A vertical rule on the trace at `x` (data units of the x axis) with a label: how a 1-coordinate
 * `marker` annotation (an edge, a time constant) is drawn on a 1-D view (ADR 0047). */
export interface TraceMark {
  x: number;
  label: string;
}

export function drawTrace(canvas: HTMLCanvasElement, x: TypedArray, y: TypedArray, marks: readonly TraceMark[] = []): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const { width: w, height: h } = canvas;
  ctx.fillStyle = "#111";
  ctx.fillRect(0, 0, w, h);
  const xr = finiteRange(x);
  const yr = finiteRange(y);
  if (!xr || !yr) return;
  const sx = (v: number) => ((v - xr.min) / (xr.max - xr.min || 1)) * (w - 1);
  const sy = (v: number) => h - 1 - ((v - yr.min) / (yr.max - yr.min || 1)) * (h - 1);
  ctx.strokeStyle = "#ff5252"; // the overlay red of the heatmap's annotations
  ctx.fillStyle = "#ff5252";
  ctx.font = "12px sans-serif";
  ctx.lineWidth = 1;
  for (const m of marks) {
    if (!Number.isFinite(m.x) || m.x < xr.min || m.x > xr.max) continue;
    const px = Math.round(sx(m.x)) + 0.5;
    ctx.beginPath();
    ctx.moveTo(px, 0);
    ctx.lineTo(px, h);
    ctx.stroke();
    if (m.label) ctx.fillText(m.label, Math.min(px + 4, w - ctx.measureText(m.label).width - 2), 14);
  }
  ctx.strokeStyle = "#4ec9b0";
  ctx.lineWidth = 1;
  ctx.beginPath();
  let pen = false;
  for (let i = 0; i < y.length; i++) {
    const xv = Number(x[i]);
    const yv = Number(y[i]);
    if (Number.isNaN(xv) || Number.isNaN(yv)) {
      pen = false;
      continue;
    }
    if (pen) ctx.lineTo(sx(xv), sy(yv));
    else ctx.moveTo(sx(xv), sy(yv));
    pen = true;
  }
  ctx.stroke();
}
