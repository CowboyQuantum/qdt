// Raw WebGL2 2D map renderer (ADR 0008, 0012): the map lives in an R32F texture; live updates upload only
// the changed rows with texSubImage2D; colour mapping happens in the fragment shader. No library.
import type { TypedArray } from "../stream/decode";
import { GLSL_VIRIDIS, MISSING } from "./colormap";
import type { Range } from "./cpu";
import type { MapRenderer } from "./map";

const VERTEX = `#version 300 es
in vec2 pos;
out vec2 uv;
void main() {
  uv = pos * 0.5 + 0.5;
  gl_Position = vec4(pos, 0.0, 1.0);
}`;

const FRAGMENT = `#version 300 es
precision highp float;
uniform highp sampler2D data;
uniform vec2 range;
in vec2 uv;
out vec4 color;
${GLSL_VIRIDIS}
void main() {
  float v = texture(data, uv).r;
  if (isnan(v)) { color = vec4(${MISSING.slice(0, 3).map((x) => (x / 255).toFixed(6)).join(", ")}, 1.0); return; }
  color = vec4(viridis((v - range.x) / max(range.y - range.x, 1e-30)), 1.0);
}`;

function compile(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader {
  const s = gl.createShader(type)!;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? "shader");
  return s;
}

export class WebGL2Map implements MapRenderer {
  readonly name = "webgl2";
  private readonly gl: WebGL2RenderingContext;
  private readonly program: WebGLProgram;
  private readonly texture: WebGLTexture;
  private rows = 0;
  private cols = 0;
  private scratch = new Float32Array(0);

  constructor(canvas: HTMLCanvasElement) {
    const gl = canvas.getContext("webgl2", { antialias: false, preserveDrawingBuffer: true });
    if (!gl) throw new Error("WebGL2 unavailable");
    this.gl = gl;
    const p = gl.createProgram()!;
    gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, VERTEX));
    gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) ?? "link");
    this.program = p;
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(p, "pos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    this.texture = gl.createTexture()!;
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    for (const [k, v] of [
      [gl.TEXTURE_MIN_FILTER, gl.NEAREST],
      [gl.TEXTURE_MAG_FILTER, gl.NEAREST],
      [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE],
      [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE],
    ] as const) {
      gl.texParameteri(gl.TEXTURE_2D, k, v);
    }
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  }

  /** Allocate the texture for a rows x cols map (texture row 0 = outer index 0 = bottom of the view). */
  resize(rows: number, cols: number): void {
    const gl = this.gl;
    [this.rows, this.cols] = [rows, cols];
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32F, cols, rows, 0, gl.RED, gl.FLOAT, null);
  }

  /** Upload rows [r0, r1) of the full row-major map `values` (only those rows cross to the GPU). */
  upload(values: TypedArray, r0: number, r1: number): void {
    const gl = this.gl;
    const n = (r1 - r0) * this.cols;
    let rows: Float32Array;
    if (values instanceof Float32Array) {
      rows = values.subarray(r0 * this.cols, r1 * this.cols);
    } else {
      if (this.scratch.length < n) this.scratch = new Float32Array(n);
      rows = this.scratch.subarray(0, n);
      for (let i = 0; i < n; i++) rows[i] = Number(values[r0 * this.cols + i]);
    }
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, r0, this.cols, r1 - r0, gl.RED, gl.FLOAT, rows);
  }

  draw(range: Range): void {
    const gl = this.gl;
    gl.viewport(0, 0, gl.canvas.width, gl.canvas.height);
    gl.useProgram(this.program);
    gl.uniform2f(gl.getUniformLocation(this.program, "range"), range.min, range.max);
    gl.uniform1i(gl.getUniformLocation(this.program, "data"), 0);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.texture);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  /** Block until the GPU has finished the last draw (a 1-pixel readback forces the sync). */
  finish(): void {
    this.gl.readPixels(0, 0, 1, 1, this.gl.RGBA, this.gl.UNSIGNED_BYTE, new Uint8Array(4));
  }

  /** The drawn canvas as RGBA, top row first (for pixel tests). */
  pixels(): Uint8Array {
    const { width: w, height: h } = this.gl.canvas;
    const raw = new Uint8Array(w * h * 4);
    this.gl.readPixels(0, 0, w, h, this.gl.RGBA, this.gl.UNSIGNED_BYTE, raw);
    const out = new Uint8Array(raw.length);
    for (let y = 0; y < h; y++) out.set(raw.subarray((h - 1 - y) * w * 4, (h - y) * w * 4), y * w * 4);
    return out;
  }

  get shape(): [number, number] {
    return [this.rows, this.cols];
  }
}
