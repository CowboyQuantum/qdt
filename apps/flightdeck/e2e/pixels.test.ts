// GPU pixel test: every 2D renderer, driven in a real Chrome (SwiftShader, deterministic and CI-safe),
// must draw the committed map fixture the same as the CPU reference renderer, cell by cell.
import { existsSync } from "node:fs";
import { chromium, type Browser } from "playwright-core";
import { preview, type PreviewServer } from "vite";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { finiteRange, renderRGBA } from "../src/render/cpu";
import { ReplaySource } from "../src/sources/replay";
import { consume } from "../src/sources/source";
import { oracle, recording } from "../test/helpers";

const ROOT = new URL("../", import.meta.url);
const NAME = "synthetic_map_64";

let server: PreviewServer;
let browser: Browser;
let app = "";

beforeAll(async () => {
  if (!existsSync(new URL("dist/index.html", ROOT))) throw new Error("no build — run `pnpm build` first");
  server = await preview({ root: ROOT.pathname.replace(/^\/(\w:)/, "$1"), preview: { port: 0, host: "127.0.0.1" }, logLevel: "silent" });
  app = server.resolvedUrls!.local[0]!;
  browser = await chromium.launch({
    channel: "chrome",
    headless: true,
    args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
  });
});

afterAll(async () => {
  await browser?.close();
  await new Promise((r) => server?.httpServer.close(r));
});

async function reference() {
  const stores = await consume(new ReplaySource(recording(NAME), NAME));
  const map = stores.get(oracle(NAME).dataset_id)!.get("signal");
  const [rows, cols] = map.shape as [number, number];
  return { rgba: renderRGBA(map.values, [rows, cols], finiteRange(map.values)!), rows, cols };
}

describe.each(["webgl2", "cpu"])("renderer %s", (renderer) => {
  it("draws the map fixture like the CPU reference", async () => {
    const page = await browser.newPage({ viewport: { width: 1200, height: 1300 } });
    await page.route("**/fixture.qdtrec", (route) =>
      route.fulfill({ body: Buffer.from(recording(NAME)), contentType: "application/octet-stream" }),
    );
    await page.goto(`${app}?replay=/fixture.qdtrec&renderer=${renderer}&bench=1`);
    await page.waitForFunction(() => window.__flightdeck?.complete || window.__flightdeck?.error, null, { polling: 50 });
    // one more frame so the final draw has landed
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const { error, name, width, height, pixels } = await page.evaluate(() => {
      const r = window.__flightdeckRenderer!;
      const c = document.querySelector(".pane canvas.map") as HTMLCanvasElement;
      return { error: window.__flightdeck!.error, name: r.name, width: c.width, height: c.height, pixels: Array.from(r.pixels()) };
    });
    await page.close();
    expect(error).toBeNull();
    expect(name).toBe(renderer);

    const ref = await reference();
    const cell = { w: width / ref.cols, h: height / ref.rows };
    let worst = 0;
    for (let y = 0; y < ref.rows; y++) {
      for (let x = 0; x < ref.cols; x++) {
        const px = Math.floor((x + 0.5) * cell.w);
        const py = Math.floor((y + 0.5) * cell.h);
        for (let ch = 0; ch < 4; ch++) {
          const got = pixels[(py * width + px) * 4 + ch]!;
          const want = ref.rgba[(y * ref.cols + x) * 4 + ch]!;
          worst = Math.max(worst, Math.abs(got - want));
        }
      }
    }
    // GPU float maths vs JS doubles: allow a couple of levels of rounding difference
    expect(worst).toBeLessThanOrEqual(2);
  });
});
