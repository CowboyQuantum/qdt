// Step 6c deliverable 8 (ADR 0075, 0086; L0 row "Flight Deck e2e"): the Queue widget is a view of the
// stand server's queue. Entries submitted from anywhere show in the server's order; moving, removing,
// pausing and resuming from the widget change the server's queue, and the entries run in that order.
// The Levels widget sets a stand limit (ADR 0085) and refuses a level beyond it. Commands are absent
// against a read server: `readonly.test.ts` shows that the picker offers no command widget there.
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
const API_PORT = 19300 + Math.floor(Math.random() * 500);
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

/** A small DC sweep on the simulated stand: P1 stepped, the sensor read at every point. */
const sweep = (name: string) => ({ definition: { name, axes: [{ name: "P1", channel: "P1", start: 0.03, stop: 0.09, num: 4 }], sensed: [{ name: "I", channel: "sensor" }] }, options: { seed: 1 } });

interface Entry {
  queue_id: string;
  state: string;
  finished_at?: string | null;
  request: { definition: { name: string } };
}
const serverQueue = async () => ((await (await fetch(`${API}/queue`)).json()) as { paused: boolean; entries: Entry[] });
const waitingOnServer = async () => (await serverQueue()).entries.filter((e) => e.state === "queued").map((e) => e.request.definition.name);
const rows = (page: Page, state: string) => page.locator(`.pane[data-widget=queue] tr[data-state=${state}] td.name`).allTextContents();

beforeAll(async () => {
  if (!existsSync(new URL("dist/index.html", ROOT))) throw new Error("no build — run `pnpm build` first");
  const root = mkdtempSync(join(tmpdir(), "qdt-e2e-queue-"));
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

it("shows the stand's queue in the server's order, and moves, removes, pauses and resumes it there", async () => {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1300 } });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(`${app}?ws=ws://127.0.0.1:${WS_PORT}&api=${API}`);
  const queue = page.locator(".pane[data-widget=queue]");
  await page.waitForFunction(() => /the queue is empty/.test(document.querySelector(".pane[data-widget=queue] [data-queue-summary]")?.textContent ?? ""));

  // pause from the widget, so the order can be arranged before anything runs
  await queue.locator("[data-toggle]").click();
  await page.waitForFunction(() => document.querySelector(".pane[data-widget=queue] [data-toggle]")?.textContent === "resume");
  expect((await serverQueue()).paused).toBe(true);
  expect(await queue.locator("[data-queue-note]").textContent()).toBe("paused: paused by local");

  // entries submitted elsewhere (a script, another desk) appear in the server's order
  for (const name of ["first", "second", "third"]) expect((await fetch(`${API}/queue`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(sweep(name)) })).status).toBe(201);
  await page.waitForFunction(() => document.querySelectorAll(".pane[data-widget=queue] tr[data-state=queued]").length === 3);
  expect(await rows(page, "queued")).toEqual(["first", "second", "third"]);

  // ↓ on the first entry: the server's order changes and the widget shows it
  await queue.locator("tr[data-state=queued]").first().locator("[data-down]").click();
  await expect.poll(waitingOnServer).toEqual(["second", "first", "third"]);
  await expect.poll(() => rows(page, "queued")).toEqual(["second", "first", "third"]);
  expect(await queue.locator("tr[data-state=queued]").first().locator("[data-up]").isDisabled()).toBe(true);

  // remove the last one: it never runs
  await queue.locator("tr[data-state=queued]").nth(2).locator("[data-remove]").click();
  await expect.poll(waitingOnServer).toEqual(["second", "first"]);
  await expect.poll(() => rows(page, "queued")).toEqual(["second", "first"]);

  // resume: the entries run, one at a time, in the order the widget showed
  await queue.locator("[data-toggle]").click();
  await expect.poll(() => rows(page, "done"), { timeout: 60_000 }).toHaveLength(2);
  const done = (await serverQueue()).entries.filter((e) => e.state === "done").sort((a, b) => a.finished_at!.localeCompare(b.finished_at!));
  expect(done.map((e) => e.request.definition.name)).toEqual(["second", "first"]);
  expect((await serverQueue()).entries.some((e) => e.request.definition.name === "third")).toBe(false);
  expect(errors).toEqual([]);
  await page.close();
});

it("sets a stand limit from the Levels widget, which then refuses a level beyond it", async () => {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1300 } });
  await page.goto(`${app}?ws=ws://127.0.0.1:${WS_PORT}&api=${API}`);
  const levels = page.locator(".pane[data-widget=levels]");
  await levels.locator("tr[data-channel=P1]").waitFor();
  await levels.locator("select[name=limit_channel]").selectOption("P1");
  await levels.locator("input[name=limit_min]").fill("0");
  await levels.locator("input[name=limit_max]").fill("0.1");
  await levels.locator("[data-set-limit]").click();
  expect(await levels.locator("[data-limit-note]").textContent()).toBe("say why the limit changes"); // a reason is kept with the version
  await levels.locator("input[name=limit_reason]").fill("e2e: P1 stays below 0.1 V");
  await levels.locator("[data-set-limit]").click();
  await page.waitForFunction(() => document.querySelector(".pane[data-widget=levels] tr[data-channel=P1] td.limit")?.textContent === "[0, 0.1] V");
  const state = (await (await fetch(`${API}/stand/state`)).json()) as { limits: { channel: string; min_v: number; max_v: number }[]; reason: string; set_by: string };
  expect(state.limits).toEqual([expect.objectContaining({ channel: "P1", min_v: 0, max_v: 0.1 })]);
  expect([state.reason, state.set_by]).toEqual(["e2e: P1 stays below 0.1 V", "local"]);
  expect(await levels.locator("[data-stand-state]").textContent()).toMatch(/stand state v\d+ · local · e2e: P1 stays below 0\.1 V/);
  // a level beyond it is refused in the widget, before the server would refuse it too
  await levels.locator("input[name=set_P1]").fill("0.2");
  await levels.locator("tr[data-channel=P1] button", { hasText: "set" }).click();
  expect(await levels.locator("tr[data-channel=P1] .badge").textContent()).toBe("beyond the stand's limit [0, 0.1] V");
  await page.close();
});
