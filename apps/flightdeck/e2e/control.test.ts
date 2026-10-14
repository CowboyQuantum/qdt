// Step 4b exit (ADR 0032): from a fresh browser with only qdt-server running against the simulator, a
// user crafts a sweep (with its pulse sequence), runs it, watches it live, finds the record, runs a
// curated analysis, and sees the overlays drawn. Drives the built app in the system Chrome.
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, type Browser } from "playwright-core";
import { preview, type PreviewServer } from "vite";
import { afterAll, beforeAll, expect, it } from "vitest";

const ROOT = new URL("../", import.meta.url);
const REPO = fileURLToPath(new URL("../../../", import.meta.url));
const API_PORT = 18700 + Math.floor(Math.random() * 500);
const WS_PORT = API_PORT + 1000;

let server: PreviewServer;
let browser: Browser;
let backend: ChildProcess;
let app = "";

async function waitForServer(url: string, ms: number): Promise<void> {
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

beforeAll(async () => {
  if (!existsSync(new URL("dist/index.html", ROOT))) throw new Error("no build — run `pnpm build` first");
  const root = mkdtempSync(join(tmpdir(), "qdt-e2e-"));
  backend = spawn(
    "uv",
    ["run", "python", "-m", "qdt_server", "--root", root, "--port", String(API_PORT), "--stream-port", String(WS_PORT)],
    { cwd: REPO, stdio: ["ignore", "pipe", "pipe"] },
  );
  backend.stderr?.on("data", (d: Buffer) => process.stderr.write(`[qdt-server] ${d}`));
  await waitForServer(`http://127.0.0.1:${API_PORT}/stream`, 60_000);
  server = await preview({ root: ROOT.pathname.replace(/^\/(\w:)/, "$1"), preview: { port: 0, host: "127.0.0.1" }, logLevel: "silent" });
  app = server.resolvedUrls!.local[0]!;
  browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
});

afterAll(async () => {
  await browser?.close();
  await new Promise((r) => server?.httpServer.close(r));
  backend?.kill();
});

it("crafts, runs, records, analyses and overlays a sweep from the UI against the simulator", async () => {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  page.on("pageerror", (e) => console.error("page error:", e));
  await page.goto(`${app}?ws=ws://127.0.0.1:${WS_PORT}&api=http://127.0.0.1:${API_PORT}`);

  // the form fills from GET /stand and GET /methods
  await page.waitForFunction(() => document.querySelectorAll("#sweep select[name=outer_channel] option").length > 0);
  expect(await page.inputValue("#sweep select[name=outer_channel]")).toBe("P1");
  expect(await page.inputValue("#sweep select[name=inner_channel]")).toBe("P2_pulse");
  expect((await page.locator("#method option").allTextContents()).sort()).toEqual(["Charge transitions", "Coulomb diamonds"]);

  // craft: an occupied-window stability sweep (the lattice estimate needs a periodic region)
  await page.fill("#sweep input[name=name]", "e2e stability");
  for (const [k, v] of [["outer_num", "48"], ["inner_num", "48"]]) await page.fill(`#sweep input[name=${k}]`, v!);
  await page.click("#sweep button[type=submit]");
  await page.waitForFunction(() => /queued|running/.test(document.querySelector("#runs")?.textContent ?? ""));

  // run → live → completed → record listed
  await page.waitForFunction(() => /completed → record/.test(document.querySelector("#runs")?.textContent ?? ""), null, { timeout: 60_000 });
  await page.waitForFunction(() => (document.querySelector("#records")?.textContent ?? "").includes("e2e stability"));
  expect(await page.inputValue("#datasets")).not.toBe("");
  expect(await page.textContent("#status")).toMatch(/heatmap/);

  // analyse the record with the curated method, then put the overlays on the live map
  await page.locator("#records li", { hasText: "e2e stability" }).first().getByRole("button", { name: "analyse" }).click();
  await page.selectOption("#method", { label: "Charge transitions" });
  await page.getByRole("button", { name: "run analysis" }).click();
  await page.waitForFunction(() => /^(ok|failed)/.test(document.querySelector("#estimates")?.textContent ?? ""), null, { timeout: 60_000 });
  const estimates = (await page.textContent("#estimates")) ?? "";
  expect(estimates).toMatch(/^ok/);
  expect(estimates).toMatch(/a_per_volt_row/);

  await page.getByRole("button", { name: "show overlays" }).click();
  await page.waitForFunction(() => (document.querySelector("#message")?.textContent ?? "").startsWith("replaying"));
  // the overlay canvas gets painted on the next frames: red segment pixels (axis labels are white)
  await page.waitForFunction(
    () => {
      const c = document.getElementById("overlay") as HTMLCanvasElement;
      const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
      let red = 0;
      for (let i = 0; i < d.length; i += 4) if (d[i + 3]! > 0 && d[i]! > 200 && d[i + 1]! < 140) red++;
      return red > 100;
    },
    null,
    { timeout: 20_000 },
  );
  // the view options are client-side: switching to the derivative and swapping axes keeps the view alive
  await page.selectOption("#transform", "grad");
  await page.check("#swap");
  await page.waitForFunction(() => /\|gradient\|.*axes swapped/.test(document.querySelector("#status")?.textContent ?? ""));
  await page.close();
});

it("edits the pulse sequence, binds its symbols, and runs it; then a 1-D sweep draws a trace", async () => {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  page.on("pageerror", (e) => console.error("page error:", e));
  await page.goto(`${app}?ws=ws://127.0.0.1:${WS_PORT}&api=http://127.0.0.1:${API_PORT}`);
  await page.waitForFunction(() => document.querySelectorAll("#ops .op-row").length === 2);
  const row = (i: number) => page.locator("#ops .op-row").nth(i);
  const errors = () => page.textContent("#sequence-errors");

  // the template: step(P2_pulse, v_P2) ; measure(sensor), its symbol bound to the inner axis
  expect(await row(0).locator("input[name=level]").inputValue()).toBe("v_P2");
  expect(await page.inputValue("#symbols input[name=bind_v_P2]")).toBe("P2");

  await page.fill("#sweep input[name=name]", "e2e pulsed");
  for (const [k, v] of [["outer_num", "8"], ["inner_num", "8"]]) await page.fill(`#sweep input[name=${k}]`, v!);
  // add a wait and move it between the step and the measure; add a second measure
  await page.selectOption("#add-op", "wait");
  await page.getByRole("button", { name: "add op" }).click();
  await row(2).getByRole("button", { name: "↑" }).click();
  expect(await row(1).locator("select.op").inputValue()).toBe("wait");
  await page.selectOption("#add-op", "measure");
  await page.getByRole("button", { name: "add op" }).click();
  expect(await errors()).toMatch(/result "I_sensor" is already measured/);
  await row(3).locator("input[name=result]").fill("I_ref");
  // a symbol duration needs a binding before the sweep can run
  await row(0).locator("input[name=duration]").fill("t_hold");
  expect(await errors()).toMatch(/symbol "t_hold" needs an axis/);
  await page.click("#sweep button[type=submit]");
  expect(await page.textContent("#message")).toMatch(/t_hold/);
  await page.fill("#symbols input[name=bind_t_hold]", "300");
  expect(await errors()).toBe("");

  await page.click("#sweep button[type=submit]");
  await page.waitForFunction(() => /e2e pulsed · completed → record/.test(document.querySelector("#runs")?.textContent ?? ""), null, { timeout: 60_000 });

  // 1-D: no outer axis, back to the template
  await page.selectOption("#sweep select[name=outer_channel]", "");
  await page.getByRole("button", { name: "reset to template" }).click();
  expect(await page.locator("#ops .op-row").count()).toBe(2);
  await page.fill("#sweep input[name=name]", "e2e trace");
  await page.click("#sweep button[type=submit]");
  await page.waitForFunction(() => /e2e trace · completed → record/.test(document.querySelector("#runs")?.textContent ?? ""), null, { timeout: 60_000 });
  await page.waitForFunction(() => /· trace/.test(document.querySelector("#status")?.textContent ?? ""), null, { timeout: 20_000 });
  await page.close();
});
