// Step 6c goal 1 (ADR 0074, 0080): a stand server measures once and syncs to the registry server; a read
// server on "the database PC" serves that record to a fresh Flight Deck with no command anywhere — no Run,
// no command widget, nothing to pick — and History opens the record on the read server's own stream.
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium, type Browser } from "playwright-core";
import { preview, type PreviewServer } from "vite";
import { afterAll, beforeAll, expect, it } from "vitest";

const ROOT = new URL("../", import.meta.url);
const REPO = fileURLToPath(new URL("../../../", import.meta.url));
const STAND_PORT = 19700 + Math.floor(Math.random() * 500);
const READ_PORT = STAND_PORT + 500;
const NAME = "read-only e2e";

let server: PreviewServer;
let browser: Browser;
let standServer: ChildProcess;
let readServer: ChildProcess;
let app = "";

const serverEnv = (tmp: string) => ({
  ...process.env,
  QDT_REGISTRY_DSN: `sqlite:///${join(tmp, "server", "server.sqlite").replace(/\\/g, "/")}`,
  QDT_PAYLOAD_STORE: join(tmp, "server", "store"),
});

function start(args: string[], env: NodeJS.ProcessEnv, tag: string): ChildProcess {
  const p = spawn("uv", ["run", "python", "-m", "qdt_server", ...args], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  p.stderr?.on("data", (d: Buffer) => process.stderr.write(`[${tag}] ${d}`));
  return p;
}

async function until<T>(probe: () => Promise<T | null>, ms: number, what: string): Promise<T> {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try {
      const v = await probe();
      if (v !== null) return v;
    } catch {
      /* not yet */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`timed out: ${what}`);
}

beforeAll(async () => {
  if (!existsSync(new URL("dist/index.html", ROOT))) throw new Error("no build — run `pnpm build` first");
  const tmp = mkdtempSync(join(tmpdir(), "qdt-e2e-read-"));
  mkdirSync(join(tmp, "server"));
  const env = serverEnv(tmp);
  // the laptop: a stand server on the simulator, one sweep through the API, synced after its record
  standServer = start(["--root", join(tmp, "laptop"), "--port", String(STAND_PORT), "--stream-port", String(STAND_PORT + 1000)], env, "stand");
  const stand = `http://127.0.0.1:${STAND_PORT}`;
  await until(async () => ((await fetch(`${stand}/server`)).ok ? true : null), 60_000, "stand server up");
  const definition = execFileSync(
    "uv",
    ["run", "python", "-c", `from qdt_sim.scenarios import stability; print(stability(24, 24, p1=(0.03, 0.18), p2=(0.03, 0.18), name=${JSON.stringify(NAME)}).model_dump_json())`],
    { cwd: REPO, encoding: "utf8" },
  );
  const run = (await (await fetch(`${stand}/runs`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ definition: JSON.parse(definition) }) })).json()) as { run_id: string };
  await until(async () => {
    const r = (await (await fetch(`${stand}/runs/${run.run_id}`)).json()) as { state: string; error?: string };
    if (r.state === "failed") throw new Error(r.error);
    return r.state === "completed" ? true : null;
  }, 60_000, "the run completes");
  // the database PC: a read server over the same registry server, its own root, no stand
  readServer = start(["--read-only", "--root", join(tmp, "desktop"), "--port", String(READ_PORT), "--stream-port", String(READ_PORT + 1000)], env, "read");
  const read = `http://127.0.0.1:${READ_PORT}`;
  await until(async () => ((await fetch(`${read}/server`)).ok ? true : null), 60_000, "read server up");
  await until(async () => (((await (await fetch(`${read}/records`)).json()) as unknown[]).length ? true : null), 30_000, "the record reaches the server");
  server = await preview({ root: ROOT.pathname.replace(/^\/(\w:)/, "$1"), preview: { port: 0, host: "127.0.0.1" }, logLevel: "silent" });
  app = server.resolvedUrls!.local[0]!;
  browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
});

afterAll(async () => {
  await browser?.close();
  await new Promise((r) => server?.httpServer.close(r));
  readServer?.kill();
  standServer?.kill();
});

it("shows a record measured elsewhere, with no command anywhere, against a read server", async () => {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(`${app}?ws=ws://127.0.0.1:${READ_PORT + 1000}&api=http://127.0.0.1:${READ_PORT}`);
  await page.locator(".pane[data-widget=history] tbody tr").first().waitFor();

  // the strip: no Run, no abort, no plan; the stand is the registry
  for (const id of ["#run", "#abort", "#plan", "#next-run", "#run-state"]) expect(await page.locator(id).count(), id).toBe(0);
  expect(await page.textContent("#stand")).toBe("registry");
  const [device] = (await (await fetch(`http://127.0.0.1:${READ_PORT}/devices`)).json()) as { device_id: string }[];
  expect(await page.textContent("#device")).toBe(device!.device_id); // the laptop's device, read from the server
  // the workspace: history and the plot; the picker offers no command widget
  const widgets = (col: string) => page.locator(`.col.${col} .pane`).evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.widget));
  expect(await widgets("left")).toEqual(["history"]);
  expect(await widgets("center")).toEqual(["plot"]);
  expect(await widgets("right")).toEqual(["empty"]);
  const offered = await page.locator(".col.right .pane select.picker option").evaluateAll((els) => els.map((e) => (e as HTMLOptionElement).value).sort());
  expect(offered).toEqual(["empty", "history"]);

  // History lists the laptop's record and opens it: the read server replays it on its own stream
  const row = page.locator(".pane[data-widget=history] tr", { hasText: NAME }).first();
  await row.waitFor();
  await row.locator("[data-open]").click();
  await page.waitForFunction(() => (document.querySelector("#message")?.textContent ?? "").startsWith("replaying"));
  await page.waitForFunction(() => /heatmap/.test(document.querySelector("#status")?.textContent ?? ""), null, { timeout: 30_000 });
  expect(errors).toEqual([]);
});
