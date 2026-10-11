// 1D trace on canvas-2D (ADR 0008: 1D views may use canvas-2D; <= 1e4 points is trivially fast).
import type { TypedArray } from "../stream/decode";
import { finiteRange } from "./cpu";

export function drawTrace(canvas: HTMLCanvasElement, x: TypedArray, y: TypedArray): void {
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
