// The workspace shell (ADR 0054, Step 6b deliverable 1) in a real Chrome: the default layout, the
// theme as data on :root, split/close with persistence across a reload, the centre refusing a second
// plot this session, gutters driven from the keyboard, and the theme menu's focus behaviour. No
// qdt-server: the replay fixture feeds the plot, the strip's stand/device read "?" and that is fine.
import { existsSync, mkdirSync } from "node:fs";
import { chromium, type Browser, type Page } from "playwright-core";
import { preview, type PreviewServer } from "vite";
import { afterAll, beforeAll, expect, it } from "vitest";
import { recording } from "../test/helpers";

const ROOT = new URL("../", import.meta.url);
const NAME = "synthetic_map_64";
const SHOTS = process.env.FLIGHTDECK_SHOTS; // a directory: screenshots land there for a human to look at

let server: PreviewServer;
let browser: Browser;
let app = "";

beforeAll(async () => {
  if (!existsSync(new URL("dist/index.html", ROOT))) throw new Error("no build — run `pnpm build` first");
  server = await preview({ root: ROOT.pathname.replace(/^\/(\w:)/, "$1"), preview: { port: 0, host: "127.0.0.1" }, logLevel: "silent" });
  app = server.resolvedUrls!.local[0]!;
  browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  if (SHOTS) mkdirSync(SHOTS, { recursive: true });
});

afterAll(async () => {
  await browser?.close();
  await new Promise((r) => server?.httpServer.close(r));
});

async function open(page: Page): Promise<void> {
  // a predicate, not a glob: the page URL itself ends in the fixture name
  await page.route((url) => url.pathname === "/fixture.qdtrec", (route) => route.fulfill({ body: Buffer.from(recording(NAME)), contentType: "application/octet-stream" }));
  await page.goto(`${app}?replay=/fixture.qdtrec`);
  await page.waitForFunction(() => /\(complete\)/.test(document.querySelector("#status")?.textContent ?? ""));
}

const widgets = (page: Page, col: string) => page.locator(`.col.${col} .pane`).evaluateAll((els) => els.map((e) => (e as HTMLElement).dataset.widget));

it("lays out the default workspace, wears the slate theme as custom properties, and shows the stream in the strip", async () => {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, colorScheme: "dark" });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await open(page);
  expect(await widgets(page, "left")).toEqual(["sweep", "analysis", "tuneup"]);
  expect(await widgets(page, "center")).toEqual(["plot"]);
  expect(await widgets(page, "right")).toEqual(["pulse", "levels", "queue", "history"]);
  expect(await page.textContent(".col.center .pane .title")).toBe("Plot 1");
  expect(await page.textContent(".col.center .pane .src")).toMatch(/^live · synthetic/);
  await page.locator(".col.center .pane [data-menu]").click();
  const menu = page.locator(".menu.plot");
  expect(await menu.locator("select[name=dataset] option").count()).toBe(2);
  expect(await menu.locator("select[name=dataset]").inputValue()).toBe("live");
  await page.keyboard.press("Escape");
  expect(await page.locator(".menu.plot").count()).toBe(0);
  expect(await page.evaluate(() => document.activeElement?.getAttribute("data-menu"))).toBe("");
  // the theme: tokens on :root, no deco classes, the scheme on <html>
  const root = await page.evaluate(() => {
    const r = document.documentElement;
    const s = getComputedStyle(r);
    return { name: r.dataset.themeName, scheme: r.dataset.theme, bg: s.getPropertyValue("--bg").trim(), classes: [...r.classList], bodyBg: getComputedStyle(document.body).backgroundColor };
  });
  expect(root).toEqual({ name: "slate", scheme: "dark", bg: "#1A212C", classes: [], bodyBg: "rgb(26, 33, 44)" });
  // the strip
  expect(await page.textContent("#source")).toMatch(/replay/);
  expect(await page.textContent("#live-text")).toBe("complete");
  expect(await page.textContent("#status")).toMatch(/heatmap/);
  expect(await page.getAttribute("#progress", "aria-valuenow")).toBe("1.000");
  expect(await page.isVisible("#run")).toBe(true);
  // the plot is square inside its pane, with the two canvases stacked on it
  const square = (await page.locator(".plot .square").boundingBox())!;
  expect(Math.abs(square.width - square.height)).toBeLessThan(2);
  expect(square.width).toBeGreaterThan(300);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/workspace-slate.png` });
  expect(errors).toEqual([]);
  await page.close();
});

it("splits and closes panes, a second plot shows the same Dataset with its own view, and the layout restores after a reload", async () => {
  // tall enough for a fifth pane on the right (four by default, each at least MIN_PANE_HEIGHT)
  const page = await browser.newPage({ viewport: { width: 1400, height: 1200 }, colorScheme: "dark" });
  await open(page);
  const right = page.locator(".col.right .pane");
  expect(await right.first().locator("[data-close]").isDisabled()).toBe(false); // two panes: either may close
  await right.nth(2).locator("[data-split]").click();
  expect(await widgets(page, "right")).toEqual(["pulse", "levels", "queue", "empty", "history"]);
  expect(await page.locator(".col.right .gutter.h").count()).toBe(4);
  // the new pane may take any widget that is not a busy single (every form widget is open already)
  const options = await right.nth(3).locator(".picker option").allTextContents();
  expect(options).toEqual(["Empty", "History", "Virtual gates", "Script"]);
  // the Script placeholder (ADR 0059): stage lints against the allowed API and says nothing ran
  await right.nth(3).locator(".picker").selectOption("script");
  const script = page.locator(".pane[data-widget=script]");
  await script.locator("textarea[name=script]").fill("qdt.run(qdt.sweep(axes=[]))\nqdt.erase_everything()");
  await script.locator("[data-stage]").click();
  expect(await script.locator("[data-report]").textContent()).toMatch(/line 2: qdt\.erase_everything is not an allowed call/);
  await script.locator("textarea[name=script]").fill("qdt.run(qdt.sweep(axes=[]))");
  await script.locator("[data-stage]").click();
  expect(await script.locator("[data-report]").textContent()).toMatch(/staged: .* nothing was run/);
  await right.nth(3).locator(".picker").selectOption("empty");
  // the centre splits into a second plot pane that follows the stream too, with its own renderer and cut
  await page.locator(".col.center .pane [data-split]").first().click();
  expect(await page.locator(".col.center .pane .title").allTextContents()).toEqual(["Plot 1", "Plot 2"]);
  await page.waitForFunction(() => /^live · synthetic/.test(document.querySelectorAll(".col.center .pane .src")[1]?.textContent ?? ""));
  const second = page.locator(".col.center .pane").nth(1);
  await second.locator("[data-menu]").click();
  await second.locator(".menu.plot input[name=swap]").check();
  await second.locator(".menu.plot input[name=cut]").fill("0.25");
  expect(await second.locator(".menu.plot .mono").textContent()).toMatch(/V_outer = /); // swapped: the cut runs along the outer axis
  await page.keyboard.press("Escape");
  await page.locator(".col.center .pane [data-menu]").first().click();
  expect(await page.locator(".col.center .pane").first().locator(".menu.plot input[name=swap]").isChecked()).toBe(false);
  await page.locator(".col.center .pane").first().locator(".menu.plot select[name=colormap]").selectOption("magma");
  await page.keyboard.press("Escape");
  await page.reload();
  await page.waitForFunction(() => /\(complete\)/.test(document.querySelector("#status")?.textContent ?? ""));
  expect(await widgets(page, "right")).toEqual(["pulse", "levels", "queue", "empty", "history"]);
  expect(await widgets(page, "center")).toEqual(["plot", "plot"]);
  // each pane's view came back with it (ADR 0061): Plot 1 in magma, Plot 2 swapped with its cut
  await page.locator(".col.center .pane [data-menu]").first().click();
  expect(await page.locator(".col.center .pane").first().locator(".menu.plot select[name=colormap]").inputValue()).toBe("magma");
  await page.keyboard.press("Escape");
  await page.locator(".col.center .pane").nth(1).locator("[data-menu]").click();
  expect(await page.locator(".col.center .pane").nth(1).locator(".menu.plot input[name=swap]").isChecked()).toBe(true);
  expect(await page.locator(".col.center .pane").nth(1).locator(".menu.plot input[name=cut]").inputValue()).toBe("0.25");
  await page.keyboard.press("Escape");
  await page.locator(".col.center .pane").nth(1).locator("[data-close]").click();
  await page.locator(".col.right .pane").nth(3).locator("[data-close]").click();
  expect(await widgets(page, "right")).toEqual(["pulse", "levels", "queue", "history"]);
  expect(await widgets(page, "center")).toEqual(["plot"]);
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("flightdeck.layout.v5")!) as { right: unknown[] });
  expect(stored.right).toHaveLength(4);
  await page.close();
});

it("resizes columns from the keyboard on a gutter and the theme menu is keyboard-closable", async () => {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, colorScheme: "dark" });
  await open(page);
  const colL = () => page.evaluate(() => getComputedStyle(document.getElementById("ws")!).getPropertyValue("--colL").trim());
  expect(await colL()).toBe("30.00%");
  await page.focus("[data-gutter=left]");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  expect(await colL()).toBe("34.00%");
  await page.keyboard.press("ArrowLeft");
  expect(await colL()).toBe("32.00%");
  // the theme menu: opens on the button, a pick applies the theme's flags and is remembered, Escape closes and returns focus
  await page.click("#theme");
  expect(await page.getAttribute("#theme", "aria-expanded")).toBe("true");
  await page.click(".menu.theme [data-theme=steel]");
  const after = await page.evaluate(() => ({ classes: [...document.documentElement.classList], remembered: localStorage.getItem("flightdeck.theme.v1") }));
  expect(after).toEqual({ classes: ["deco-caps", "deco-brackets", "deco-graticule", "deco-glow", "deco-flat"], remembered: "steel" });
  expect(await page.textContent("#theme")).toBe("Theme: steel");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/workspace-steel.png` });
  await page.click("#theme");
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector(".menu.theme"));
  expect(await page.evaluate(() => document.activeElement?.id)).toBe("theme");
  await page.reload();
  await page.waitForFunction(() => /\(complete\)/.test(document.querySelector("#status")?.textContent ?? ""));
  expect(await page.evaluate(() => document.documentElement.dataset.themeName)).toBe("steel");
  await page.close();
});
