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

it("lays out control | plot | empty, wears the slate theme as custom properties, and shows the stream in the strip", async () => {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, colorScheme: "dark" });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await open(page);
  expect(await widgets(page, "left")).toEqual(["control"]);
  expect(await widgets(page, "center")).toEqual(["plot"]);
  expect(await widgets(page, "right")).toEqual(["empty"]);
  expect(await page.textContent(".col.center .pane .title")).toBe("Plot 1");
  expect(await page.locator(".col.center .pane .slot #datasets option").count()).toBe(1);
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

it("splits and closes side panes, refuses a second plot this session, and restores the layout after a reload", async () => {
  const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, colorScheme: "dark" });
  await open(page);
  const right = page.locator(".col.right .pane");
  expect(await page.locator(".col.center .pane [data-split]").isDisabled()).toBe(true);
  expect(await right.first().locator("[data-close]").isDisabled()).toBe(true); // the last pane of a column stays
  await right.first().locator("[data-split]").click();
  expect(await widgets(page, "right")).toEqual(["empty", "empty"]);
  expect(await page.locator(".col.right .gutter.h").count()).toBe(1);
  // the new pane can take the control panel only once the left pane gives it up: it is single-instance
  const options = await right.nth(1).locator(".picker option").allTextContents();
  expect(options).toEqual(["Empty"]);
  await page.reload();
  await page.waitForFunction(() => /\(complete\)/.test(document.querySelector("#status")?.textContent ?? ""));
  expect(await widgets(page, "right")).toEqual(["empty", "empty"]);
  await page.locator(".col.right .pane").nth(1).locator("[data-close]").click();
  expect(await widgets(page, "right")).toEqual(["empty"]);
  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("flightdeck.layout.v1")!) as { right: unknown[] });
  expect(stored.right).toHaveLength(1);
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
