// Regenerates the screenshots of docs/guides/simulated-stand.md (#158): starts qdt-server on the simulated
// stand with an empty registry, serves the built app, walks the guide's steps in a headless Chrome, and writes
// docs/guides/img/*.png quantized to 256 colours. Any step that does not complete stops it with an error, and
// nothing is written. Run it as `pnpm screenshots` (which builds first), from apps/flightdeck.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { preview } from "vite";

const ROOT = fileURLToPath(new URL("../", import.meta.url));
const REPO = fileURLToPath(new URL("../../../", import.meta.url));
const OUT = join(REPO, "docs/guides/img");
const API_PORT = 18700 + Math.floor(Math.random() * 500);
const WS_PORT = API_PORT + 1000;
const PILLOW = "pillow==12.3.0";

async function waitForServer(url, ms) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`qdt-server did not answer on ${url}`);
}

/** Wait for the page to satisfy `fn`, or stop with what the guide's step was doing. */
async function step(page, what, fn, arg, timeout = 120_000) {
  try {
    await page.waitForFunction(fn, arg, { timeout });
  } catch {
    throw new Error(`${what}: not done within ${timeout / 1000} s; the strip says ${JSON.stringify(await page.textContent("#message"))}`);
  }
}

const finished = (name) => [(n) => new RegExp(`${n} · completed → record`).test(document.querySelector("#run-state")?.textContent ?? ""), name];
const analysed = () => /^(ok|failed)/.test(document.querySelector(".pane[data-widget=analysis] .estimates")?.textContent ?? "");

/** History → analyse the named record → the method → run → overlays; returns the estimates' text. */
async function analyse(page, record, method, params = {}) {
  await page.locator(".pane[data-widget=history] [data-refresh]").click();
  await page.locator(".pane[data-widget=history] tr", { hasText: record }).first().getByRole("button", { name: "analyse" }).click();
  await step(page, `select ${record} in Analysis`, () => document.querySelector(".pane[data-widget=analysis] select[name=record]")?.value !== "");
  await page.locator(".pane[data-widget=analysis] select[name=method]").selectOption({ label: method });
  for (const [k, v] of Object.entries(params)) await page.locator(`.pane[data-widget=analysis] input[name=${k}]`).fill(v);
  await page.locator(".pane[data-widget=analysis] [data-analyse]").first().click();
  await step(page, `${method} on ${record}`, analysed);
  const estimates = (await page.textContent(".pane[data-widget=analysis] .estimates")) ?? "";
  if (!estimates.startsWith("ok")) throw new Error(`${method} on ${record}: ${estimates.slice(0, 300)}`);
  if (estimates.startsWith("ok · 0 overlays")) throw new Error(`${method} on ${record} drew no overlays`);
  await page.locator(".pane[data-widget=analysis] [data-overlays]").click();
  await step(page, `overlays of ${record}`, () => (document.querySelector("#message")?.textContent ?? "").startsWith("replaying"));
  await page.waitForTimeout(2500); // the replay draws, then the overlays land on it
  return estimates;
}

async function walk(page, dir) {
  const sweep = page.locator(".pane[data-widget=sweep]");
  const shot = (name, target = page) => target.screenshot({ path: join(dir, name) });

  // the workspace, as it opens: the Sweep form about where the stand sits (#157)
  await step(page, "load the stand", () => document.querySelectorAll(".pane[data-widget=sweep] select[name=outer_channel] option").length > 0);
  await step(page, "open the Sweep form about P1's 0.6 V", () => document.querySelector(".pane[data-widget=sweep] input[name=outer_start]")?.value === "0.45");
  await page.waitForTimeout(1500);
  await shot("01-workspace.png");

  // 1. a stability diagram, in the windows the form opened with
  const windows = await Promise.all(["outer_start", "outer_stop", "inner_start", "inner_stop"].map((k) => sweep.locator(`input[name=${k}]`).inputValue()));
  if (windows.join(" ") !== "0.45 0.75 -0.15 0.15") throw new Error(`the Sweep form opened at ${windows.join(" ")}, not the guide's 0.45 0.75 -0.15 0.15`);
  await sweep.locator("input[name=name]").fill("first stability diagram");
  for (const k of ["outer_num", "inner_num"]) await sweep.locator(`input[name=${k}]`).fill("96"); // nine pixels a cell (ADR 0092)
  await sweep.locator("input[name=options]").fill('{"seed": 1, "noise": false}');
  await sweep.locator("[data-compile]").click();
  await step(page, "compile the stability diagram", () => /^plan [0-9a-f]{8}$/.test(document.querySelector("#plan")?.textContent ?? ""));
  await shot("02-sweep-form.png", sweep);
  await page.click("#run");
  await step(page, "run the stability diagram", ...finished("first stability diagram"));
  await page.waitForTimeout(1500);
  await shot("03-stability.png");

  // 2. its charge transitions
  console.log("charge transitions:", (await analyse(page, "first stability diagram", "Charge transitions", { threshold_rel: "0.1" })).slice(0, 300));
  await shot("04-transitions.png");

  // 3. the sensor's Coulomb diamonds
  await sweep.locator("select[name=kind]").selectOption("dc");
  await sweep.locator("select[name=outer_channel]").selectOption("SG");
  await sweep.locator("select[name=inner_channel]").selectOption("bias");
  await sweep.locator("input[name=inner_name]").fill("V_sd");
  await sweep.locator("input[name=name]").fill("sensor diamonds");
  for (const [k, v] of [["outer_start", "0.64"], ["outer_stop", "0.70"], ["inner_start", "-0.012"], ["inner_stop", "0.012"], ["outer_num", "64"], ["inner_num", "64"]]) await sweep.locator(`input[name=${k}]`).fill(v);
  await sweep.locator("input[name=options]").fill('{"seed": 1, "noise": false}');
  await page.click("#run");
  await step(page, "run the diamonds", ...finished("sensor diamonds"));
  console.log("Coulomb diamonds:", (await analyse(page, "sensor diamonds", "Coulomb diamonds")).slice(0, 300));
  await shot("05-diamonds.png");

  // 5. the tune-up, then Levels with SG parked where it found the wing
  const tune = page.locator(".pane[data-widget=tuneup]");
  for (const box of await tune.locator("input[name=node]").all()) if (!(await box.isChecked())) await box.check();
  await tune.locator("input[name=options]").fill('{"seed": 2, "noise": false}');
  await tune.locator("[data-start]").click();
  await step(page, "run the tune-up", () => /· (completed|failed|stopped)/.test(document.querySelector(".pane[data-widget=tuneup] .tuneup-head")?.textContent ?? ""), undefined, 300_000);
  const head = (await tune.locator(".tuneup-head").textContent()) ?? "";
  if (!head.includes("· completed")) throw new Error(`the tune-up did not complete: ${head}`);
  console.log("tune-up:", (await tune.locator(".dag").innerText()).replace(/\s+/g, " ").slice(0, 300));
  await page.waitForTimeout(1500);
  await shot("06-tuneup.png");
  await tune.locator(".dag").scrollIntoViewIfNeeded();
  await page.waitForTimeout(800);
  await shot("07-tuneup-result.png", tune);
  await shot("08-levels.png", page.locator(".pane[data-widget=levels]"));
}

/** Quantize every PNG in `dir` to 256 colours (no dithering) into OUT, with a pinned Pillow that uv fetches
 * for this command alone: it is not a dependency of the workspace. */
function quantize(dir) {
  const code = [
    "import sys, pathlib",
    "from PIL import Image",
    "src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])",
    "for p in sorted(src.glob('*.png')):",
    "    im = Image.open(p).convert('RGB').quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)",
    "    im.save(out / p.name, optimize=True)",
  ].join("\n");
  const r = spawnSync("uv", ["run", "--no-project", "--with", PILLOW, "python", "-c", code, dir, OUT], { cwd: REPO, stdio: "inherit" });
  if (r.status !== 0) throw new Error(`quantizing with ${PILLOW} failed (exit ${r.status})`);
}

async function main() {
  if (!existsSync(join(ROOT, "dist/index.html"))) throw new Error("no build: run `pnpm screenshots`, which builds first");
  const root = mkdtempSync(join(tmpdir(), "qdt-guide-registry-"));
  const dir = mkdtempSync(join(tmpdir(), "qdt-guide-shots-"));
  const backend = spawn("uv", ["run", "python", "-m", "qdt_server", "--root", root, "--port", String(API_PORT), "--stream-port", String(WS_PORT)], {
    cwd: REPO,
    stdio: ["ignore", "ignore", "pipe"],
  });
  backend.stderr.on("data", (d) => process.stderr.write(`[qdt-server] ${d}`));
  let server;
  let browser;
  try {
    await waitForServer(`http://127.0.0.1:${API_PORT}/stream`, 60_000);
    server = await preview({ root: ROOT, preview: { port: 0, host: "127.0.0.1" }, logLevel: "silent" });
    browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
    page.on("pageerror", (e) => console.error("page error:", e.message));
    await page.goto(`${server.resolvedUrls.local[0]}?ws=ws://127.0.0.1:${WS_PORT}&api=http://127.0.0.1:${API_PORT}`);
    await walk(page, dir);
  } finally {
    await browser?.close();
    await new Promise((r) => (server ? server.httpServer.close(r) : r()));
    backend.kill();
  }
  quantize(dir);
  for (const name of readdirSync(dir).sort()) console.log(`${name}: ${Math.round(statSync(join(OUT, name)).size / 1024)} KB`);
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : e);
  process.exit(1);
});
