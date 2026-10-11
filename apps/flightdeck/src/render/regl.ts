// regl 2D map renderer — the library candidate in the #9 benchmark. Same design as the raw WebGL2 path
// (float texture, sub-image row uploads, colormap in the shader), but regl runs on WebGL1 + OES_texture_float.
import createREGL from "regl";
import type { TypedArray } from "../stream/decode";
import { GLSL_VIRIDIS, MISSING } from "./colormap";
import type { Range } from "./cpu";
import type { MapRenderer } from "./map";

export class ReglMap implements MapRenderer {
  readonly name = "regl";
  private readonly regl: createREGL.Regl;
  private readonly texture: createREGL.Texture2D;
  private readonly drawCmd: createREGL.DrawCommand;
  private range: Range = { min: 0, max: 1 };
  private rows = 0;
  private cols = 0;
  private scratch = new Float32Array(0);

  constructor(private readonly canvas: HTMLCanvasElement) {
    this.regl = createREGL({
      canvas,
      extensions: ["OES_texture_float"],
      attributes: { antialias: false, preserveDrawingBuffer: true },
    });
    this.texture = this.regl.texture({ width: 1, height: 1, format: "luminance", type: "float" });
    const missing = MISSING.slice(0, 3).map((x) => (x / 255).toFixed(6)).join(", ");
    this.drawCmd = this.regl({
      vert: `
        precision highp float;
        attribute vec2 pos;
        varying vec2 uv;
        void main() { uv = pos * 0.5 + 0.5; gl_Position = vec4(pos, 0.0, 1.0); }`,
      frag: `
        precision highp float;
        uniform sampler2D data;
        uniform vec2 range;
        varying vec2 uv;
        ${GLSL_VIRIDIS}
        void main() {
          float v = texture2D(data, uv).r;
          if (v != v) { gl_FragColor = vec4(${missing}, 1.0); return; }
          gl_FragColor = vec4(viridis((v - range.x) / max(range.y - range.x, 1e-30)), 1.0);
        }`,
      attributes: { pos: [-1, -1, 1, -1, -1, 1, 1, 1] },
      uniforms: {
        data: this.texture,
        range: () => [this.range.min, this.range.max],
      },
      primitive: "triangle strip",
      count: 4,
    });
  }

  resize(rows: number, cols: number): void {
    [this.rows, this.cols] = [rows, cols];
    this.texture({ width: cols, height: rows, format: "luminance", type: "float", min: "nearest", mag: "nearest" });
  }

  upload(values: TypedArray, r0: number, r1: number): void {
    const n = (r1 - r0) * this.cols;
    let rows: Float32Array;
    if (values instanceof Float32Array) rows = values.subarray(r0 * this.cols, r1 * this.cols);
    else {
      if (this.scratch.length < n) this.scratch = new Float32Array(n);
      rows = this.scratch.subarray(0, n);
      for (let i = 0; i < n; i++) rows[i] = Number(values[r0 * this.cols + i]);
    }
    this.texture.subimage({ data: rows, width: this.cols, height: r1 - r0, format: "luminance", type: "float" }, 0, r0);
  }

  draw(range: Range): void {
    this.range = range;
    this.regl.poll();
    this.drawCmd();
  }

  finish(): void {
    this.regl.read({ x: 0, y: 0, width: 1, height: 1 });
  }

  pixels(): Uint8Array {
    const { width: w, height: h } = this.canvas;
    const raw = this.regl.read() as Uint8Array;
    const out = new Uint8Array(raw.length);
    for (let y = 0; y < h; y++) out.set(raw.subarray((h - 1 - y) * w * 4, (h - y) * w * 4), y * w * 4);
    return out;
  }

  get shape(): [number, number] {
    return [this.rows, this.cols];
  }
}
