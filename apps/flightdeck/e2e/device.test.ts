// ADR 0089, #164: the Device widget draws the simulated device's gates to scale from `GET /device/layout`,
// each coloured by the level it sits at, and follows a level set elsewhere (here: straight to the API).
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, type Browser, type Page } from "playwright-core";
import { preview, type PreviewServer } from "vite";
import { afterAll, beforeAll, expect, it } from "vitest";

const ROOT = new URL("../", import.meta.url);
const REPO = fileURLToPath(new URL("../../../", import.meta.url));
const API_PORT = 21000 + Math.floor(Math.random() * 500);
const WS_PORT = API_PORT + 1000;
const API = `http://127.0.0.1:${API_PORT}`;

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
  const root = mkdtempSync(join(tmpdir(), "qdt-e2e-device-"));
  backend = spawn("uv", ["run", "python", "-m", "qdt_server", "--root", root, "--port", String(API_PORT), "--stream-port", String(WS_PORT)], { cwd: REPO, stdio: ["ignore", "pipe", "pipe"] });
  backend.stderr?.on("data", (d: Buffer) => process.stderr.write(`[qdt-server] ${d}`));
  await waitForServer(`${API}/queue`, 60_000);
  server = await preview({ root: ROOT.pathname.replace(/^\/(\w:)/, "$1"), preview: { port: 0, host: "127.0.0.1" }, logLevel: "silent" });
  app = server.resolvedUrls!.local[0]!;
  browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
});

afterAll(async () => {
  await browser?.close();
  await new Promise((r) => server?.httpServer.close(r));
  backend?.kill();
});

it("draws the device's gates at their levels and follows a level set on the stand", async () => {
  const page = await browser.newPage({ viewport: { width: 1400, height: process.env.QDT_DEVICE_SHOT ? 1800 : 1100 } });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(`${app}?ws=ws://127.0.0.1:${WS_PORT}&api=${API}`);
  await page.locator(".col.right .pane select.picker").first().selectOption("device");
  const pane = page.locator(".pane[data-widget=device]");
  const level = (gate: string) => pane.locator(`path[data-gate=${gate}]`).getAttribute("data-level");
  await page.waitForFunction(() => document.querySelector(".pane[data-widget=device] path[data-gate=P1]")?.getAttribute("data-level") === "0.6");

  // every gate of the device, the sensor's barriers and baths too (Phantom 0.3.0 on), at the stand's starting
  // point (the programmed one, the sensor gate where it reads, ADR 0090); the colours span lowest to highest
  const gates = await pane.locator("path[data-gate]").evaluateAll((els) => els.map((e) => e.getAttribute("data-gate")));
  expect(gates).toEqual(["B_L", "P1", "B_M", "P2", "B_R", "SG", "R_L", "R_R", "SB_L", "SB_R", "SR_L", "SR_R"]);
  expect(await level("SB_R")).toBe("0.3");
  expect(await level("B_L")).toBe("0.15");
  expect(await level("R_R")).toBe("0.7");
  expect(await pane.locator("[data-lo]").textContent()).toBe("0.150 V");
  expect(await pane.locator("[data-hi]").textContent()).toBe("0.700 V");
  expect(await pane.locator("[data-scale-nm]").getAttribute("data-scale-nm")).toBe("100");
  const [bar] = await pane.locator(".sbar .line").evaluate((e) => [e.getBoundingClientRect().width]);
  expect(await pane.locator(".foot").textContent()).toContain("Phantom 0.6.0, device file two-dot-sige-a");

  // to scale: P1 is 44 nm wide and 120 nm tall, R_L 218 nm wide; the drawn fills keep those ratios
  const drawn = (gate: string) => pane.locator(`path[data-gate=${gate}]`).evaluate((e) => [e.getBoundingClientRect().width, e.getBoundingClientRect().height]);
  const [w1, h1] = await drawn("P1");
  const [wl] = await drawn("R_L");
  expect(h1! / w1!).toBeCloseTo(120 / 44, 2);
  expect(wl! / w1!).toBeCloseTo(218 / 44, 2);
  expect(bar! / w1!).toBeCloseTo(100 / 44, 2);
  expect(await pane.locator("[data-legend=SG]").textContent()).toBe("SG0.651 V"); // 0.650544 V, ADR 0090
  if (process.env.QDT_DEVICE_SHOT) await pane.screenshot({ path: process.env.QDT_DEVICE_SHOT });

  // a level set on the stand (not from this widget) shows within a poll, with a new colour
  const before = await pane.locator("path[data-gate=P1]").evaluate((e) => getComputedStyle(e).fill);
  const r = await fetch(`${API}/levels`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify([{ channel: "P1", value: 0.3 }]) });
  expect(r.ok).toBe(true);
  await page.waitForFunction(() => document.querySelector(".pane[data-widget=device] path[data-gate=P1]")?.getAttribute("data-level") === "0.3", null, { timeout: 10_000 });
  expect(await pane.locator("path[data-gate=P1]").evaluate((e) => getComputedStyle(e).fill)).not.toBe(before);
  expect(await pane.locator("[data-legend=P1]").textContent()).toBe("P10.300 V");
  expect(await pane.locator("path[data-gate=P1] title").textContent()).toBe("P1 (plunger) on channel P1: 0.300 V");
  expect(errors).toEqual([]);
});
