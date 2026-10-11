// Flight Deck renderer benchmark (Open Decision #9; Step 1 live exit criterion; Analysis 0001 targets).
//
// For each renderer: start `python -m qdt_lab.stream --wait-for-client` at the target size and rate, open the
// built Flight Deck in the system Chrome (playwright-core, no browser download) with ?bench=1, wait until the
// map is complete, and read per-chunk [produced_at, drawn] samples. Latency = drawn - produced_at: the
// producer's stamp to the frame finishing on the GPU, same machine clock.
//
//   pnpm build && node bench/run.mjs [--size 2048] [--rate 1000000] [--renderers webgl2,cpu]
//                                    [--gpu hardware|swiftshader] [--out bench/results/<file>.json]
//                                    [--assert]   exit 1 unless every renderer meets the targets in steady state
//                                                 (p95 latency <= 50 ms, rendered rate >= 95% of --rate)
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { preview } from "vite";

const HERE = fileURLToPath(new URL("../", import.meta.url));
const REPO = fileURLToPath(new URL("../../../", import.meta.url));

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const size = Number(arg("size", 2048));
const rate = Number(arg("rate", 1_000_000));
const renderers = arg("renderers", "webgl2,cpu").split(",");
const gpu = arg("gpu", "hardware");
const ppc = arg("points-per-chunk", null);
const WARMUP_MS = 500;

const GPU_ARGS = {
  // real GPU through ANGLE; Chrome picks the platform backend
  hardware: ["--enable-gpu", "--ignore-gpu-blocklist", "--enable-unsafe-webgpu"],
  // software rasteriser: what a CI runner without a GPU gets
  swiftshader: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
};

const python = [`${REPO}.venv/Scripts/python.exe`, `${REPO}.venv/bin/python`].find(existsSync);
if (!python) throw new Error("no repo .venv — run `uv sync --all-packages` first");
if (!existsSync(`${HERE}dist/index.html`)) throw new Error("no build — run `pnpm build` first");

const freePort = () =>
  new Promise((resolve) => {
    const s = createServer().listen(0, "127.0.0.1", () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
  });

function quantile(sorted, q) {
  if (!sorted.length) return NaN;
  const i = Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))));
  return sorted[i];
}

async function runOne(browser, appUrl, renderer) {
  const port = await freePort();
  const pyArgs = ["-m", "qdt_lab.stream", "--size", `${size}`, "--rate", `${rate}`, "--port", `${port}`, "--wait-for-client"];
  if (ppc) pyArgs.push("--points-per-chunk", ppc);
  const server = spawn(python, pyArgs, { stdio: ["ignore", "pipe", "inherit"] });
  try {
    await new Promise((resolve, reject) => {
      server.stdout.on("data", (d) => d.toString().includes("serving") && resolve());
      server.on("exit", (c) => reject(new Error(`stream server exited ${c}`)));
    });
    const page = await browser.newPage({ viewport: { width: 1100, height: 1150 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto(`${appUrl}?ws=ws://127.0.0.1:${port}&renderer=${renderer}&bench=1`);
    const budget = ((size * size) / rate) * 4 * 1000 + 30_000;
    await page.waitForFunction(() => window.__flightdeck?.complete || window.__flightdeck?.error, null, {
      timeout: budget,
      polling: 100,
    });
    const state = await page.evaluate(() => window.__flightdeck);
    const glRenderer = await page.evaluate(() => {
      const gl = document.createElement("canvas").getContext("webgl2");
      const ext = gl?.getExtension("WEBGL_debug_renderer_info");
      return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl ? gl.getParameter(gl.RENDERER) : "none";
    });
    await page.close();
    if (state.error || errors.length) throw new Error(`${renderer}: ${state.error ?? errors.join("; ")}`);

    const lat = state.samples.map(([p, d]) => d - p).sort((a, b) => a - b);
    // steady state: chunks produced after the first WARMUP_MS (first frame, texture allocation, shader compile)
    const t0 = Math.min(...state.samples.map(([p]) => p));
    const steady = state.samples.filter(([p]) => p - t0 >= WARMUP_MS).map(([p, d]) => d - p).sort((a, b) => a - b);
    const worst = state.samples
      .map(([p, d]) => [d - p, p - t0])
      .sort((a, b) => b[0] - a[0])
      .slice(0, 5)
      .map(([l, at]) => ({ latency_ms: l, at_ms: at }));
    const points = state.samples.reduce((a, [, , n]) => a + n, 0);
    const firstProduced = Math.min(...state.samples.map(([p]) => p));
    const lastProduced = Math.max(...state.samples.map(([p]) => p));
    const lastDrawn = Math.max(...state.samples.map(([, d]) => d));
    return {
      renderer,
      gl_renderer: glRenderer,
      chunks: state.samples.length,
      frames: state.frames,
      points,
      latency_ms: { p50: quantile(lat, 0.5), p95: quantile(lat, 0.95), p99: quantile(lat, 0.99), max: lat.at(-1) },
      steady_latency_ms: {
        p50: quantile(steady, 0.5),
        p95: quantile(steady, 0.95),
        p99: quantile(steady, 0.99),
        max: steady.at(-1),
      },
      worst_chunks: worst,
      producer_rate_pts_s: Math.round(points / ((lastProduced - firstProduced) / 1000)),
      rendered_rate_pts_s: Math.round(points / ((lastDrawn - firstProduced) / 1000)),
      tail_ms: lastDrawn - lastProduced,
    };
  } finally {
    server.kill();
  }
}

const server = await preview({ root: HERE, preview: { port: 0, host: "127.0.0.1" }, logLevel: "silent" });
const appUrl = server.resolvedUrls.local[0];
const browser = await chromium.launch({ channel: "chrome", headless: true, args: GPU_ARGS[gpu] });
const results = [];
try {
  for (const r of renderers) {
    const res = await runOne(browser, appUrl, r);
    results.push(res);
    const l = res.latency_ms;
    const st = res.steady_latency_ms;
    console.log(
      `${r.padEnd(7)} p50 ${l.p50} ms · p95 ${l.p95} ms · p99 ${l.p99} ms · max ${l.max} ms · ` +
        `steady p95 ${st.p95} / p99 ${st.p99} / max ${st.max} ms · worst at ${res.worst_chunks.map((w) => w.at_ms).join(",")} ms · ` +
        `rendered ${res.rendered_rate_pts_s.toLocaleString()} pts/s (producer ${res.producer_rate_pts_s.toLocaleString()}) · ` +
        `${res.chunks} chunks / ${res.frames} frames · ${res.gl_renderer}`,
    );
  }
} finally {
  await browser.close();
  await new Promise((r) => server.httpServer.close(r));
}

const out = arg("out", null);
const report = {
  date: new Date().toISOString(),
  platform: `${process.platform} ${process.arch}`,
  chrome: browser.version(),
  gpu_mode: gpu,
  targets: { size, rate, latency_ms: 50 },
  points_per_chunk: ppc ? Number(ppc) : size,
  results,
};
if (out) {
  mkdirSync(fileURLToPath(new URL(".", new URL(out, `file://${HERE}`))), { recursive: true });
  writeFileSync(new URL(out, `file://${HERE.replaceAll("\\", "/")}`), `${JSON.stringify(report, null, 2)}\n`);
  console.log(`wrote ${out}`);
}

if (process.argv.includes("--assert")) {
  const failures = results.filter(
    (r) => !(r.steady_latency_ms.p95 <= report.targets.latency_ms) || r.rendered_rate_pts_s < 0.95 * rate,
  );
  for (const f of failures) {
    console.error(
      `FAIL ${f.renderer}: steady p95 ${f.steady_latency_ms.p95} ms (target <= ${report.targets.latency_ms}), ` +
        `rendered ${f.rendered_rate_pts_s} pts/s (target >= ${0.95 * rate})`,
    );
  }
  if (failures.length) process.exit(1);
  console.log("bench: targets met");
}
