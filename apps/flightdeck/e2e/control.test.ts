// Step 4b exit (ADR 0032): from a fresh browser with only qdt-server running against the simulator, a
// user crafts a sweep (with its pulse sequence), runs it, watches it live, finds the record, runs a
// curated analysis, and sees the overlays drawn. Drives the built app in the system Chrome.
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
const API_PORT = 18700 + Math.floor(Math.random() * 500);
const WS_PORT = API_PORT + 1000;

let server: PreviewServer;

/** The ⚙ menu of the n-th plot pane, opened if it is not. */
async function plotMenu(page: Page, n = 0) {
  const pane = page.locator(".col.center .pane").nth(n);
  if ((await pane.locator(".menu.plot").count()) === 0) await pane.locator("[data-menu]").click();
  return pane.locator(".menu.plot");
}
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
  await page.waitForFunction(() => document.querySelectorAll(".pane[data-widget=sweep] select[name=outer_channel] option").length > 0);
  expect(await page.inputValue(".pane[data-widget=sweep] select[name=outer_channel]")).toBe("P1");
  expect(await page.inputValue(".pane[data-widget=sweep] select[name=inner_channel]")).toBe("P2_pulse");
  expect((await page.locator(".pane[data-widget=analysis] select[name=method] option").allTextContents()).sort()).toEqual(["Charge transitions", "Coulomb diamonds", "Plane", "Sensor peak", "Single exponential"]);

  // craft: an occupied-window stability sweep (the lattice estimate needs a periodic region)
  await page.fill(".pane[data-widget=sweep] input[name=name]", "e2e stability");
  for (const [k, v] of [["outer_num", "48"], ["inner_num", "48"]]) await page.fill(`.pane[data-widget=sweep] input[name=${k}]`, v!);
  // compile first (ADR 0056): the strip shows the plan's identity; an edit marks it stale; Run compiles again
  await page.locator(".pane[data-widget=sweep] [data-compile]").click();
  await page.waitForFunction(() => /^plan [0-9a-f]{8}$/.test(document.querySelector("#plan")?.textContent ?? ""));
  expect(await page.textContent(".pane[data-widget=sweep] .plan")).toMatch(/e2e stability · P1 48 × P2 48 · 2,304 pts/);
  // ADR 0066: the stand decides how each axis advances and the plan says so; the simulated device is its own
  // sequencer, so 'auto' triggers the DC axis with no marker line
  expect(await page.textContent(".pane[data-widget=sweep] .plan")).toMatch(/P1: triggered by the sequencer itself\nP2: swept in the sequence/);
  expect(await page.inputValue(".pane[data-widget=sweep] select[name=stepping]")).toBe("auto");
  await page.fill(".pane[data-widget=sweep] input[name=inner_num]", "40");
  await page.waitForFunction(() => /stale/.test(document.querySelector("#plan")?.textContent ?? ""));
  await page.fill(".pane[data-widget=sweep] input[name=inner_num]", "48");
  expect(await page.textContent("#next-run")).toBe("next: e2e stability · stage · P1 48 × P2_pulse 48");
  await page.click("#run");
  await page.waitForFunction(() => /queued|running/.test(document.querySelector("#run-state")?.textContent ?? ""));

  // run → live → completed → record listed
  await page.waitForFunction(() => /completed → record/.test(document.querySelector("#run-state")?.textContent ?? ""), null, { timeout: 60_000 });
  await page.locator(".pane[data-widget=history] [data-refresh]").click();
  await page.locator(".pane[data-widget=history] tr", { hasText: "e2e stability" }).first().waitFor();
  expect(await page.textContent("#status")).toMatch(/heatmap/);
  const menu = await plotMenu(page);
  expect(await menu.locator("select[name=dataset]").inputValue()).toBe("live");
  expect(await menu.locator("select[name=dataset] option").count()).toBe(2); // live + the run's Dataset
  await page.keyboard.press("Escape");
  expect(await page.locator(".menu.plot").count()).toBe(0);

  // analyse the record with the curated method, then put the overlays on the live map
  await page.locator(".pane[data-widget=history] tr", { hasText: "e2e stability" }).first().getByRole("button", { name: "analyse" }).click();
  await page.waitForFunction(() => (document.querySelector(".pane[data-widget=analysis] select[name=record]") as HTMLSelectElement | null)?.value !== "");
  await page.locator(".pane[data-widget=analysis] select[name=method]").selectOption({ label: "Charge transitions" });
  await page.locator(".pane[data-widget=analysis] [data-analyse]").first().click();
  await page.waitForFunction(() => /^(ok|failed)/.test(document.querySelector(".pane[data-widget=analysis] .estimates")?.textContent ?? ""), null, { timeout: 60_000 });
  const estimates = (await page.textContent(".pane[data-widget=analysis] .estimates")) ?? "";
  expect(estimates).toMatch(/^ok/);
  expect(estimates).toMatch(/a_per_volt_row/);

  await page.locator(".pane[data-widget=analysis] [data-overlays]").click();
  await page.waitForFunction(() => (document.querySelector("#message")?.textContent ?? "").startsWith("replaying"));
  // the overlay canvas gets painted on the next frames: red segment pixels (axis labels are white)
  await page.waitForFunction(
    () => {
      const c = document.querySelector(".pane canvas.overlay") as HTMLCanvasElement;
      const d = c.getContext("2d")!.getImageData(0, 0, c.width, c.height).data;
      let red = 0;
      for (let i = 0; i < d.length; i += 4) if (d[i + 3]! > 0 && d[i]! > 200 && d[i + 1]! < 140) red++;
      return red > 100;
    },
    null,
    { timeout: 20_000 },
  );
  // click-to-set (ADR 0053): a click on the map offers the point under it; setting it holds the levels on
  // the stand, and the next compiled sweep inherits what it does not move itself
  const box = (await page.locator(".pane canvas.overlay").first().boundingBox())!;
  await page.mouse.click(box.x + box.width * 0.5, box.y + box.height * 0.5);
  // the map's x axis is the inner (P2) axis, so P2 is listed first
  const levels = page.locator(".pane[data-widget=levels]");
  await page.waitForFunction(() => /clicked: P2 = .* · P1 = /.test(document.querySelector(".pane[data-widget=levels] .offer")?.textContent ?? ""));
  await levels.locator("[data-offer]").click();
  await page.waitForFunction(() => /held: P1 = .* · P2 = /.test(document.querySelector(".pane[data-widget=levels] .held-summary")?.textContent ?? ""));
  // the table shows the stand (ADR 0057): P1's setpoint is what was set, its readback is None (a simulated
  // gate is not sensed), the sensor's readback is a current
  await page.waitForFunction(() => /0\.10/.test(document.querySelector(".pane[data-widget=levels] tr[data-channel=P1] td.setpoint")?.textContent ?? ""));
  expect(await levels.locator("tr[data-channel=P1] td.readback").textContent()).toBe("—");
  expect(await levels.locator("tr[data-channel=sensor] td.readback").textContent()).toMatch(/ A$/);
  const held = (await (await page.request.get(`http://127.0.0.1:${API_PORT}/levels`)).json()) as { channel: string; value: number }[];
  expect(held.map((l) => l.channel).sort()).toEqual(["P1", "P2"]);
  for (const l of held) expect(Math.abs(l.value - 0.105)).toBeLessThan(0.01); // the middle of the 0.03..0.18 window
  // inline set with limit refusal (a browser setting, ±1 by default) and the settling state
  await levels.locator("tr[data-channel=P1] input[name=set_P1]").fill("5");
  await levels.locator("tr[data-channel=P1] button", { hasText: "set" }).click();
  expect(await levels.locator("tr[data-channel=P1] .badge").textContent()).toMatch(/beyond the limit/);
  await levels.locator("tr[data-channel=P1] input[name=set_P1]").fill("0.02");
  await levels.locator("tr[data-channel=P1] input[name=set_P1]").press("Enter");
  await page.waitForFunction(() => /held: P1 = 0\.02 V/.test(document.querySelector(".pane[data-widget=levels] .held-summary")?.textContent ?? ""));
  await levels.locator("[data-release]").click();
  await page.waitForFunction(() => /held: nothing/.test(document.querySelector(".pane[data-widget=levels] .held-summary")?.textContent ?? ""));

  // the view options are client-side: switching to the derivative and swapping axes keeps the view alive
  const view = await plotMenu(page);
  await view.locator("select[name=transform]").selectOption("grad");
  await view.locator("input[name=swap]").check();
  await page.waitForFunction(() => /\|gradient\|.*axes swapped/.test(document.querySelector("#status")?.textContent ?? ""));
  await page.keyboard.press("Escape");

  // History (ADR 0055): the record opens in a second plot pane, pinned to it, while Plot 1 follows the stream
  const hist = page.locator(".pane[data-widget=history]");
  await hist.locator("[data-refresh]").click();
  await hist.locator("tr", { hasText: "e2e stability" }).first().waitFor();
  await hist.locator("tr", { hasText: "e2e stability" }).first().getByRole("button", { name: "open" }).click();
  await page.waitForFunction(() => document.querySelectorAll(".col.center .pane").length === 2);
  await page.waitForFunction(() => /pinned · record/.test(document.querySelectorAll(".col.center .pane .src")[1]?.textContent ?? ""), null, { timeout: 20_000 });
  expect(await page.locator(".col.center .pane .src").first().textContent()).toMatch(/^live/);
  await page.waitForFunction(() => /Plot 2/.test(document.querySelector(".pane[data-widget=history] tr.open td.shown")?.textContent ?? ""));
  // each pane has its own cut: Plot 2's slider moves only its rule
  const second = await plotMenu(page, 1);
  await second.locator("input[name=cut]").fill("0.2");
  expect(await second.locator(".mono").textContent()).toMatch(/P2 = /);
  await page.keyboard.press("Escape");
  await page.locator(".col.center .pane").nth(1).locator("[data-close]").click();
  await page.waitForFunction(() => document.querySelectorAll(".col.center .pane").length === 1);
  await page.close();
}, 180_000);

it("edits the pulse sequence, binds its symbols, and runs it; then a 1-D sweep draws a trace", async () => {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  page.on("pageerror", (e) => console.error("page error:", e));
  await page.goto(`${app}?ws=ws://127.0.0.1:${WS_PORT}&api=http://127.0.0.1:${API_PORT}`);
  await page.waitForFunction(() => document.querySelectorAll(".pane[data-widget=pulse] .op-row").length === 2);
  const row = (i: number) => page.locator(".pane[data-widget=pulse] .op-row").nth(i);
  const errors = () => page.textContent(".pane[data-widget=pulse] .sequence-errors");

  // the template: step(P2_pulse, v_P2) ; measure(sensor), its symbol bound to the inner axis
  expect(await row(0).locator("input[name=level]").inputValue()).toBe("v_P2");
  expect(await page.inputValue(".pane[data-widget=pulse] .symbols input[name=bind_v_P2]")).toBe("P2");

  await page.fill(".pane[data-widget=sweep] input[name=name]", "e2e pulsed");
  for (const [k, v] of [["outer_num", "8"], ["inner_num", "8"]]) await page.fill(`.pane[data-widget=sweep] input[name=${k}]`, v!);
  // add a wait and move it between the step and the measure; add a second measure
  await page.selectOption(".pane[data-widget=pulse] .add-op", "wait");
  await page.getByRole("button", { name: "add op" }).click();
  await row(2).getByRole("button", { name: "↑" }).click();
  expect(await row(1).locator("select.op").inputValue()).toBe("wait");
  await page.selectOption(".pane[data-widget=pulse] .add-op", "measure");
  await page.getByRole("button", { name: "add op" }).click();
  expect(await errors()).toMatch(/result "I_sensor" is already a result/);
  await row(3).locator("input[name=result]").fill("I_ref");
  // a symbol duration needs a binding before the sweep can run
  await row(0).locator("input[name=duration]").fill("t_hold");
  expect(await errors()).toMatch(/symbol "t_hold" needs an axis/);
  await page.click("#run");
  await page.waitForFunction(() => /t_hold/.test(document.querySelector("#message")?.textContent ?? ""));
  await page.fill(".pane[data-widget=pulse] .symbols input[name=bind_t_hold]", "300");
  expect(await errors()).toBe("");
  // chopped readout (ADR 0037): the reference point follows the swept level; the difference is recorded
  await page.selectOption(".pane[data-widget=pulse] .add-op", "step");
  await page.getByRole("button", { name: "add op" }).click();
  await row(4).locator("select[name=channel]").selectOption("P2_pulse");
  await row(4).locator("input[name=level]").fill("v_P2 + 0.002");
  await row(4).getByRole("button", { name: "↑" }).click(); // before the reference measure
  expect(await row(3).locator("input[name=level]").inputValue()).toBe("v_P2 + 0.002");
  expect(await row(3).locator("label").filter({ hasText: "level" }).textContent()).toMatch(/level ← P2 \(swept\)/);
  await page.selectOption(".pane[data-widget=pulse] .add-op", "difference");
  await page.getByRole("button", { name: "add op" }).click();
  expect(await row(5).locator("input[name=a]").inputValue()).toBe("I_sensor");
  expect(await row(5).locator("input[name=b]").inputValue()).toBe("I_ref");
  expect(await errors()).toBe("");

  await page.click("#run");
  await page.waitForFunction(() => /e2e pulsed · completed → record/.test(document.querySelector("#run-state")?.textContent ?? ""), null, { timeout: 60_000 });
  // the recorded difference is a variable of its own; any two same-shape variables can be subtracted in the view
  const vars = await plotMenu(page);
  expect((await vars.locator("select[name=variable] option").allTextContents()).sort()).toEqual(["I_ref", "I_sensor", "dI"]);
  await vars.locator("select[name=variable]").selectOption("I_sensor");
  await vars.locator("select[name=minus]").selectOption("I_ref");
  await page.waitForFunction(() => /· I_sensor − I_ref · heatmap/.test(document.querySelector("#status")?.textContent ?? ""));
  await vars.locator("select[name=variable]").selectOption("dI");
  await page.waitForFunction(() => /· dI · heatmap/.test(document.querySelector("#status")?.textContent ?? ""));
  await page.keyboard.press("Escape");

  // 1-D: no outer axis, back to the template
  await page.selectOption(".pane[data-widget=sweep] select[name=outer_channel]", "");
  await page.getByRole("button", { name: "reset to template" }).click();
  expect(await page.locator(".pane[data-widget=pulse] .op-row").count()).toBe(2);
  await page.fill(".pane[data-widget=sweep] input[name=name]", "e2e trace");
  // operating point (ADR 0038): hold a DC level for the sweep; in 1-D, P1 is not swept and may be held too
  await page.getByRole("button", { name: "add level" }).click();
  await page.locator(".pane[data-widget=sweep] .levels .level-row").first().locator("select[name=level_channel]").selectOption("P2");
  await page.locator(".pane[data-widget=sweep] .levels .level-row").first().locator("input[name=level_value]").fill("0.05");
  expect(await page.textContent(".pane[data-widget=sweep] .level-errors")).toBe("");
  await page.locator(".pane[data-widget=sweep] .levels .level-row").first().locator("select[name=level_channel]").selectOption("P1");
  expect(await page.textContent(".pane[data-widget=sweep] .level-errors")).toBe(""); // 1-D: P1 is not swept, so it may be held
  await page.locator(".pane[data-widget=sweep] .levels .level-row").first().locator("select[name=level_channel]").selectOption("P2");
  await page.click("#run");
  await page.waitForFunction(() => /e2e trace · completed → record/.test(document.querySelector("#run-state")?.textContent ?? ""), null, { timeout: 60_000 });
  await page.waitForFunction(() => /· trace/.test(document.querySelector("#status")?.textContent ?? ""), null, { timeout: 20_000 });
  await page.close();
}, 180_000);

it("captures a record on the simulated scope, draws it as a trace, and marks the exponential's edge and τ on it", async () => {
  // ADR 0047: the L2-3 shape through the UI. The simulated scope records a droop; the single exponential
  // reads τ from the stored record; its markers are rules on the trace.
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  page.on("pageerror", (e) => console.error("page error:", e));
  await page.goto(`${app}?ws=ws://127.0.0.1:${WS_PORT}&api=http://127.0.0.1:${API_PORT}`);
  await page.waitForFunction(() => document.querySelectorAll(".pane[data-widget=sweep] select[name=outer_channel] option").length > 0);
  await page.selectOption(".pane[data-widget=sweep] select[name=kind]", "capture");
  expect(await page.isHidden(".pane[data-widget=sweep] select[name=sensor]")).toBe(true);
  expect(await page.inputValue(".pane[data-widget=sweep] select[name=capture_channel]")).toBe("scope1");
  await page.selectOption(".pane[data-widget=sweep] select[name=outer_channel]", "");
  await page.fill(".pane[data-widget=sweep] input[name=name]", "e2e droop");
  await page.fill(".pane[data-widget=sweep] input[name=options]", '{"seed": 2, "noise": true, "tau_s": 0.0015}');
  await page.click("#run");
  await page.waitForFunction(() => /e2e droop · completed → record/.test(document.querySelector("#run-state")?.textContent ?? ""), null, { timeout: 60_000 });
  await page.waitForFunction(() => /· trace · trace/.test(document.querySelector("#status")?.textContent ?? ""), null, { timeout: 20_000 });

  await page.locator(".pane[data-widget=history] [data-refresh]").click();
  await page.locator(".pane[data-widget=history] tr", { hasText: "e2e droop" }).first().getByRole("button", { name: "analyse" }).click();
  await page.waitForFunction(() => (document.querySelector(".pane[data-widget=analysis] select[name=record]") as HTMLSelectElement | null)?.value !== "");
  await page.locator(".pane[data-widget=analysis] select[name=method]").selectOption({ label: "Single exponential" });
  await page.locator(".pane[data-widget=analysis] [data-analyse]").first().click();
  await page.waitForFunction(() => /^(ok|failed)/.test(document.querySelector(".pane[data-widget=analysis] .estimates")?.textContent ?? ""), null, { timeout: 60_000 });
  const estimates = (await page.textContent(".pane[data-widget=analysis] .estimates")) ?? "";
  expect(estimates).toMatch(/^ok/);
  expect(estimates).toMatch(/tau\s+0\.001[45]/);

  await page.locator(".pane[data-widget=analysis] [data-overlays]").click();
  await page.waitForFunction(() => (document.querySelector("#message")?.textContent ?? "").startsWith("replaying"));
  // the markers are red rules on the trace canvas (the 2-D overlay; the trace itself is teal). A heatmap
  // was shown on this page before, so the WebGL map canvas is hidden and the trace is really drawn.
  await page.waitForFunction(
    () => {
      const c = document.querySelector(".pane canvas.overlay") as HTMLCanvasElement;
      const d = c.getContext("2d")?.getImageData(0, 0, c.width, c.height).data;
      if (!d) return false;
      let red = 0;
      let teal = 0;
      for (let i = 0; i < d.length; i += 4) {
        if (d[i]! > 200 && d[i + 1]! < 120 && d[i + 2]! < 120) red++;
        else if (d[i + 1]! > 150 && d[i]! < 120) teal++;
      }
      return red > 50 && teal > 50 && (document.querySelector(".pane canvas.map") as HTMLElement).style.visibility === "hidden";
    },
    null,
    { timeout: 20_000 },
  );
  await page.close();
}, 180_000);

it("runs a three-node tune-up from the UI and shows the DAG state with every node accepted", async () => {
  // ADR 0050: the nodes come from GET /nodes, the tune-up runs on the server one sweep at a time (each
  // visible on the stream), and the panel renders the TuneUp as it progresses
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  page.on("pageerror", (e) => console.error("page error:", e));
  await page.goto(`${app}?ws=ws://127.0.0.1:${WS_PORT}&api=http://127.0.0.1:${API_PORT}`);
  await page.waitForFunction(() => document.querySelectorAll(".pane[data-widget=tuneup] input[name=node]").length === 4);
  expect(await page.locator(".pane[data-widget=tuneup] .node-id").allTextContents()).toEqual(["sensor-operating-point", "sensor-wing", "charge-lattice", "virtual-lattice"]);
  // a cold sensor so the diamonds resolve (ADR 0030); the sensor node decides where the stability nodes park SG
  await page.fill(".pane[data-widget=tuneup] input[name=options]", '{"seed": 2, "noise": false, "sensor_width_v": 0.01}');
  await page.locator(".pane[data-widget=tuneup] [data-start]").click();
  await page.waitForFunction(() => /queued|running/.test(document.querySelector(".pane[data-widget=tuneup] .tuneup-state")?.textContent ?? ""));
  await page.waitForFunction(() => /· completed/.test(document.querySelector(".pane[data-widget=tuneup] .tuneup-head")?.textContent ?? ""), null, { timeout: 120_000 });
  const lines = await page.locator(".pane[data-widget=tuneup] .dag li").allTextContents();
  expect(lines).toHaveLength(4);
  expect(lines[0]).toMatch(/sensor-operating-point · accepted/);
  expect(lines[0]).toMatch(/sg_peak_v=/);
  // ADR 0062: the wing node fits the width and parks the gate on the wing; the server then holds it
  expect(lines[1]).toMatch(/sensor-wing · accepted/);
  expect(lines[1]).toMatch(/sg_width_v=/);
  expect(lines[2]).toMatch(/charge-lattice · accepted/);
  expect(lines[2]).toMatch(/c_21=/);
  expect(lines[3]).toMatch(/virtual-lattice · accepted/);
  expect(lines[3]).toMatch(/residual_a=/);
  await page.waitForFunction(() => /held: SG = /.test(document.querySelector(".pane[data-widget=levels] .held-summary")?.textContent ?? ""), null, { timeout: 10_000 });
  // both sweeps were runs and records like any other
  await page.waitForFunction(() => (document.querySelector(".pane[data-widget=history]")?.textContent ?? "").includes("virtual-gate lattice"), null, { timeout: 20_000 });
  await page.close();
}, 180_000);

it("reads in the shot (ADR 0067): a DC map whose sensor is integrated in the shot, a capture recorded in the shot", async () => {
  // the readout is the sweep's choice; the pacing is the stand's (ADR 0066): the simulated device is its own
  // sequencer, so 'auto' triggers the innermost DC axis once the reading is in the shot
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  page.on("pageerror", (e) => console.error("page error:", e));
  await page.goto(`${app}?ws=ws://127.0.0.1:${WS_PORT}&api=http://127.0.0.1:${API_PORT}`);
  const sweep = page.locator(".pane[data-widget=sweep]");
  await page.waitForFunction(() => document.querySelectorAll(".pane[data-widget=sweep] select[name=outer_channel] option").length > 0);

  // a DC map: per point the sensor is sensed and there is no shot; in the shot it is integrated by the device
  await sweep.locator("select[name=kind]").selectOption("dc");
  await sweep.locator("select[name=inner_channel]").selectOption("P2");
  await sweep.locator("input[name=name]").fill("e2e map in the shot");
  await sweep.locator("input[name=outer_num]").fill("6");
  await sweep.locator("input[name=inner_num]").fill("8");
  expect(await sweep.locator("select[name=readout]").inputValue()).toBe("point");
  expect(await sweep.locator("input[name=shots]").isVisible()).toBe(false);
  expect(await sweep.locator("select[name=stepping]").isVisible()).toBe(false); // read per point: the host steps it
  expect(await sweep.locator("[data-readout-hint]").textContent()).toMatch(/can instead be read in a shot of dot/);
  await sweep.locator("select[name=readout]").selectOption("shot");
  expect(await sweep.locator("[data-readout-hint]").textContent()).toMatch(/sensor is integrated by dot in a one-measure shot/);
  expect(await sweep.locator("input[name=shot_measure_ns]").isVisible()).toBe(true);
  expect(await sweep.locator("[data-stepping-hint]").textContent()).toMatch(/applies to P2, the innermost DC axis/);
  // read in the shot, a host-stepped DC point has no axis for its measure (ADR 0066): software is not offered
  expect(await sweep.locator("select[name=stepping] option[value=software]").evaluate((o) => (o as HTMLOptionElement).disabled)).toBe(true);
  await sweep.locator("input[name=shots]").fill("2");
  expect(await page.textContent("#next-run")).toBe("next: e2e map in the shot · dc in the shot · P1 6 × P2 8");
  if (process.env.FLIGHTDECK_SHOTS) await page.screenshot({ path: `${process.env.FLIGHTDECK_SHOTS}/sweep-readout.png` });
  await sweep.locator("[data-compile]").click();
  await page.waitForFunction(() => /P2: triggered/.test(document.querySelector(".pane[data-widget=sweep] .plan")?.textContent ?? ""));
  expect(await sweep.locator(".plan").textContent()).toMatch(/e2e map in the shot · P1 6 × P2 8 · 48 pts .* stage program\nP1: stepped from the host\nP2: triggered by the sequencer itself/);
  await page.click("#run");
  await page.waitForFunction(() => /e2e map in the shot · completed → record/.test(document.querySelector("#run-state")?.textContent ?? ""), null, { timeout: 60_000 });
  await page.waitForFunction(() => /e2e map in the shot · I_sensor · heatmap/.test(document.querySelector("#status")?.textContent ?? ""), null, { timeout: 20_000 });

  // a capture: in the shot the record starts at its marker (start pinned at 0), a wait follows it
  await sweep.locator("select[name=kind]").selectOption("capture");
  await sweep.locator("select[name=outer_channel]").selectOption("P1");
  await sweep.locator("input[name=name]").fill("e2e staircase");
  await sweep.locator("input[name=capture_num]").fill("200");
  await sweep.locator("select[name=readout]").selectOption("shot");
  expect(await sweep.locator("[data-readout-hint]").textContent()).toMatch(/scope1 is captured in a shot of dot from its marker/);
  expect(await sweep.locator("input[name=capture_start]").isDisabled()).toBe(true);
  expect(await sweep.locator("input[name=capture_start]").inputValue()).toBe("0");
  expect(await sweep.locator("input[name=capture_pace_ms]").isVisible()).toBe(true);
  await sweep.locator("input[name=capture_pace_ms]").fill("0");
  await page.click("#run");
  await page.waitForFunction(() => /e2e staircase · completed → record/.test(document.querySelector("#run-state")?.textContent ?? ""), null, { timeout: 60_000 });
  expect(await sweep.locator(".plan").textContent()).toMatch(/e2e staircase · P1 6 × time 200 · 1,200 pts .*\nP1: triggered by the sequencer itself/);
  // back to per point: the capture of ADR 0047, its start restored, no wait, no stepping
  await sweep.locator("select[name=readout]").selectOption("point");
  expect(await sweep.locator("input[name=capture_start]").isDisabled()).toBe(false);
  expect(await sweep.locator("input[name=capture_start]").inputValue()).toBe("-0.001");
  expect(await sweep.locator("input[name=capture_pace_ms]").isVisible()).toBe(false);
  expect(await sweep.locator("select[name=stepping]").isVisible()).toBe(false);
  await page.close();
}, 180_000);
