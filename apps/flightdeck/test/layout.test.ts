// The layout model (ADR 0054): split/close/resize invariants, sizes sum, min-height refusal,
// persistence round trip. Pure data, no DOM.
import { describe, expect, it } from "vitest";
import {
  canSplit,
  close,
  defaultLayout,
  LAYOUT_KEY,
  loadLayout,
  MAX_SIDE,
  MAX_PLOT_PANES,
  MAX_SIDES,
  MIN_PANE_HEIGHT,
  MIN_SIDE,
  parseLayout,
  resizeColumn,
  resizeRows,
  saveLayout,
  serializeLayout,
  setWidget,
  split,
  type Layout,
} from "../src/workspace/layout";

const KNOWN = ["plot", "control", "empty", "history", "sweep", "pulse"];
/** The default layout with one pane per column: the split/close arithmetic reads best from there. */
const single = () => {
  let l = defaultLayout();
  l = close(l, l.left[1]!.id);
  l = close(l, l.right[1]!.id);
  return l;
};
const sum = (panes: { size: number }[]) => panes.reduce((a, p) => a + p.size, 0);
const TALL = 10 * MIN_PANE_HEIGHT;

describe("default layout", () => {
  it("is sweep + control left, one plot centre, pulse + history right, sides narrower than the centre", () => {
    const l = defaultLayout();
    expect(l.left.map((p) => p.widget)).toEqual(["sweep", "control"]);
    expect(l.center.map((p) => p.widget)).toEqual(["plot"]);
    expect(l.right.map((p) => p.widget)).toEqual(["pulse", "history"]);
    expect(l.widths.left + l.widths.right).toBeLessThan(0.6);
    expect(sum(l.left)).toBeCloseTo(1);
    expect(sum(l.right)).toBeCloseTo(1);
    const ids = [...l.left, ...l.center, ...l.right].map((p) => p.id);
    expect(new Set(ids).size).toBe(5);
  });
});

describe("split", () => {
  it("halves the pane, puts the new one below it, keeps the column summing to 1", () => {
    const l = single();
    const { layout, pane } = split(l, l.right[0]!.id, "empty", TALL);
    expect(pane).not.toBeNull();
    expect(layout.right.map((p) => p.id)).toEqual([l.right[0]!.id, pane!.id]);
    expect(layout.right.map((p) => p.size)).toEqual([0.5, 0.5]);
    expect(sum(layout.right)).toBeCloseTo(1);
    expect(l.right).toHaveLength(1); // the input is untouched
  });

  it("splits in the middle of a stack and leaves the other panes' share alone", () => {
    let l = single();
    const a = l.left[0]!.id;
    l = split(l, a, "empty", TALL).layout;
    const b = l.left[1]!.id;
    l = split(l, a, "empty", TALL).layout;
    expect(l.left.map((p) => p.id)[2]).toBe(b);
    expect(l.left.map((p) => p.size)).toEqual([0.25, 0.25, 0.5]);
  });

  it("refuses when the column is too short for one more pane at the minimum height", () => {
    const l = single();
    expect(canSplit(l, "left", 2 * MIN_PANE_HEIGHT)).toBe(true);
    expect(canSplit(l, "left", 2 * MIN_PANE_HEIGHT - 1)).toBe(false);
    const r = split(l, l.left[0]!.id, "empty", 2 * MIN_PANE_HEIGHT - 1);
    expect(r.pane).toBeNull();
    expect(r.layout).toBe(l);
    // and the refusal scales with the number of panes already there
    const two = split(l, l.left[0]!.id, "empty", TALL).layout;
    expect(canSplit(two, "left", 3 * MIN_PANE_HEIGHT - 1)).toBe(false);
    expect(canSplit(two, "left", 3 * MIN_PANE_HEIGHT)).toBe(true);
  });

  it("caps the centre at MAX_PLOT_PANES (one WebGL2 context each)", () => {
    let l = defaultLayout();
    for (let i = 1; i < MAX_PLOT_PANES; i++) {
      const r = split(l, l.center[0]!.id, "plot", 100 * MIN_PANE_HEIGHT);
      expect(r.pane, `pane ${i + 1}`).not.toBeNull();
      l = r.layout;
    }
    expect(l.center).toHaveLength(MAX_PLOT_PANES);
    expect(canSplit(l, "center", 100 * MIN_PANE_HEIGHT)).toBe(false);
    expect(split(l, l.center[0]!.id, "plot", 100 * MIN_PANE_HEIGHT).pane).toBeNull();
    expect(canSplit(close(l, l.center[0]!.id), "center", 100 * MIN_PANE_HEIGHT)).toBe(true);
  });

  it("keeps plots in the centre and only in the centre", () => {
    const l = defaultLayout();
    expect(split(l, l.center[0]!.id, "empty", TALL).pane).toBeNull();
    expect(split(l, l.left[0]!.id, "plot", TALL).pane).toBeNull();
    expect(split(l, l.center[0]!.id, "plot", TALL).pane?.widget).toBe("plot");
  });

  it("ignores an unknown pane id", () => {
    const l = defaultLayout();
    expect(split(l, "nope", "empty", TALL).layout).toBe(l);
  });
});

describe("close", () => {
  it("gives the closed pane's height to the one above, or below for the first", () => {
    let l = single();
    const a = l.left[0]!.id;
    l = split(l, a, "empty", TALL).layout;
    const b = l.left[1]!.id;
    l = split(l, b, "empty", TALL).layout; // [a 0.5, b 0.25, c 0.25]
    const c = l.left[2]!.id;
    const closedB = close(l, b);
    expect(closedB.left.map((p) => [p.id, p.size])).toEqual([[a, 0.75], [c, 0.25]]);
    const closedA = close(l, a);
    expect(closedA.left.map((p) => [p.id, p.size])).toEqual([[b, 0.75], [c, 0.25]]);
    expect(sum(closedA.left)).toBeCloseTo(1);
  });

  it("keeps the last pane of a column", () => {
    const l = single();
    expect(close(l, l.center[0]!.id)).toBe(l);
  });
});

describe("setWidget", () => {
  it("changes a side pane's widget and never makes a plot or touches the centre", () => {
    const l = defaultLayout();
    expect(setWidget(l, l.right[0]!.id, "control").right[0]!.widget).toBe("control");
    expect(setWidget(l, l.right[0]!.id, "plot")).toBe(l);
    expect(setWidget(l, l.center[0]!.id, "empty")).toBe(l);
  });
});

describe("resize", () => {
  it("moves the boundary between two panes, clamped, keeping their total", () => {
    let l = single();
    l = split(l, l.left[0]!.id, "empty", TALL).layout;
    const r = resizeRows(l, "left", 0, 0.7);
    expect(r.left[0]!.size).toBeCloseTo(0.7);
    expect(r.left[1]!.size).toBeCloseTo(0.3);
    expect(resizeRows(l, "left", 0, 0.01).left[0]!.size).toBe(0.15);
    expect(resizeRows(l, "left", 0, 0.99).left[0]!.size).toBe(0.85);
    expect(sum(resizeRows(l, "left", 0, 0.99).left)).toBeCloseTo(1);
    expect(resizeRows(l, "left", 5, 0.5)).toBe(l); // no such boundary
  });

  it("clamps a column width and keeps the two sides under the shared cap", () => {
    const l = defaultLayout();
    expect(resizeColumn(l, "left", 0.01).widths.left).toBe(MIN_SIDE);
    expect(resizeColumn(l, "left", 0.9).widths.left).toBe(MAX_SIDE);
    const wide = resizeColumn(resizeColumn(l, "left", MAX_SIDE), "right", MAX_SIDE);
    expect(wide.widths.left + wide.widths.right).toBeCloseTo(MAX_SIDES);
    expect(wide.widths.left).toBeCloseTo(wide.widths.right);
  });
});

describe("persistence", () => {
  it("round-trips widgets, sizes and widths; pane ids are fresh", () => {
    let l = single();
    l = split(l, l.left[0]!.id, "empty", TALL).layout;
    l = resizeRows(l, "left", 0, 0.7);
    l = resizeColumn(l, "right", 0.25);
    const back = parseLayout(serializeLayout(l), KNOWN);
    const strip = (x: Layout) => ({ ...x, left: x.left.map(({ widget, size }) => ({ widget, size })), center: x.center.map(({ widget, size }) => ({ widget, size })), right: x.right.map(({ widget, size }) => ({ widget, size })) });
    expect(strip(back)).toEqual(strip(l));
    expect(back.left[0]!.id).not.toBe(l.left[0]!.id);
  });

  it("falls back to the default on garbage, and to `empty` for a widget that no longer exists", () => {
    const d = defaultLayout();
    const shape = (x: Layout) => [x.left.map((p) => p.widget), x.center.map((p) => p.widget), x.right.map((p) => p.widget)];
    expect(shape(parseLayout(null, KNOWN))).toEqual(shape(d));
    expect(shape(parseLayout("{not json", KNOWN))).toEqual(shape(d));
    expect(shape(parseLayout('{"left":[]}', KNOWN))).toEqual(shape(d));
    expect(shape(parseLayout('{"left":[{"widget":"matrix"}],"center":[{"widget":"x"}],"right":[{"widget":"plot"}]}', KNOWN))).toEqual([["empty"], ["plot"], ["empty"]]);
    const w = parseLayout('{"left":[{"widget":"control"}],"center":[{"widget":"plot"}],"right":[{"widget":"empty"}],"widths":{"left":0.9,"right":"x"}}', KNOWN);
    expect(w.widths.left).toBe(MAX_SIDE);
    expect(w.widths.right).toBe(d.widths.right);
  });

  it("saves to and loads from a storage, and survives a storage that throws or is missing", () => {
    const store = new Map<string, string>();
    const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
    let l = single();
    l = split(l, l.right[0]!.id, "empty", TALL).layout;
    saveLayout(l, storage);
    expect(store.has(LAYOUT_KEY)).toBe(true);
    expect(loadLayout(KNOWN, storage).right).toHaveLength(2);
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("quota");
      },
    };
    expect(() => saveLayout(l, broken)).not.toThrow();
    expect(loadLayout(KNOWN, broken).right).toHaveLength(2);
    expect(loadLayout(KNOWN, null).center).toHaveLength(1);
  });
});
