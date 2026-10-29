// The Device widget's pure model (ADR 0089, #164): bounds, the colour range, the scale bar, the flipped
// paths, readable labels, and how every gate is painted at the levels it sits at.
import { describe, expect, it } from "vitest";
import { cssColour, gradientStops, inkOn, labelFit, layoutBounds, levelRange, levelText, paint, pathOf, rangeFraction, scaleBarNm, viewBoxOf } from "../src/control/device";
import type { DeviceLayout } from "../src/schema/api";

const rect = (x0: number, x1: number, y0: number, y1: number): [[number, number], [number, number], [number, number], [number, number]] => [
  [x0, y0],
  [x1, y0],
  [x1, y1],
  [x0, y1],
];

const LAYOUT: DeviceLayout = {
  device_id: "dot",
  material: "SiGe",
  source: "test",
  channel_nm: [-160, 160, -36, 36],
  sensor_nm: [-80, 80, 174, 246],
  gates: [
    { name: "P1", role: "plunger", channel: "P1", polygon_nm: rect(-62, -18, -60, 60) },
    { name: "B_M", role: "barrier", channel: "B_M", polygon_nm: rect(-12, 12, -60, 60) },
    { name: "R_L", role: "reservoir", channel: "R_L", polygon_nm: rect(-320, -102, -60, 60) },
    { name: "X", role: "gate", channel: null, polygon_nm: rect(100, 140, 100, 120) },
  ],
};

describe("device diagram model", () => {
  it("bounds every gate, the channel and the sensor, with a margin", () => {
    expect(layoutBounds(LAYOUT, 10)).toEqual({ x0: -330, x1: 170, y0: -70, y1: 256 });
    expect(viewBoxOf({ x0: -330, x1: 170, y0: -70, y1: 256 })).toBe("-330 -256 500 326");
  });

  it("flips y for SVG", () => {
    expect(pathOf([[0, 0], [10, 0], [10, 5]])).toBe("M0 0 L10 0 L10 -5 Z");
  });

  it("spans the colours over the levels, widening a single level", () => {
    expect(levelRange([0.6, 0.15, 0.7])).toEqual({ lo: 0.15, hi: 0.7 });
    const one = levelRange([0.6, 0.6])!;
    expect(one.lo).toBeCloseTo(0.55);
    expect(one.hi).toBeCloseTo(0.65);
    expect(levelRange([])).toBeNull();
    expect(rangeFraction(0.425, { lo: 0.15, hi: 0.7 })).toBeCloseTo(0.5);
    expect(rangeFraction(2, { lo: 0, hi: 1 })).toBe(1);
  });

  it("rounds the scale bar to 1, 2 or 5 times a power of ten", () => {
    expect(scaleBarNm(760)).toBe(100);
    expect(scaleBarNm(1200)).toBe(200);
    expect(scaleBarNm(3000)).toBe(500);
    expect(scaleBarNm(0)).toBe(0);
  });

  it("labels in black on a light fill and white on a dark one", () => {
    expect(inkOn("#fde725")).toBe("#000000");
    expect(inkOn("#440154")).toBe("#ffffff");
    expect(levelText(0.6)).toBe("0.600 V");
    expect(levelText(null)).toBe("—");
    expect(gradientStops("grey", 3)).toBe(`${cssColour("grey", 0)} 0%, ${cssColour("grey", 0.5)} 50%, ${cssColour("grey", 1)} 100%`);
  });

  it("paints each gate at its channel's level, the extremes at the colormap's ends", () => {
    const { gates, range } = paint(LAYOUT, { P1: 0.6, B_M: 0.2, R_L: 0.7, X: 9 }, "viridis");
    expect(range).toEqual({ lo: 0.2, hi: 0.7 });
    const by = Object.fromEntries(gates.map((g) => [g.name, g]));
    expect(by.B_M!.fill).toBe(cssColour("viridis", 0));
    expect(by.R_L!.fill).toBe(cssColour("viridis", 1));
    expect(by.P1!.fill).toBe(cssColour("viridis", 0.8));
    // a gate with no channel has no level, whatever a same-named channel holds, and no fill
    expect(by.X!.level).toBeNull();
    expect(by.X!.fill).toBeNull();
    expect(by.P1!.vertical).toBe(true);
    expect(by.R_L!.vertical).toBe(false);
    expect(by.P1!.centre).toEqual([-40, 0]);
  });

  it("leaves a gate unfilled when its channel has no level", () => {
    const { gates, range } = paint(LAYOUT, { P1: 0.6 }, "magma");
    expect(range!.lo).toBeCloseTo(0.55);
    expect(gates.filter((g) => g.fill).map((g) => g.name)).toEqual(["P1"]);
  });
});

describe("gate labels", () => {
  it("writes the name and level where they fit, the name alone where only it fits, and nothing below the floor", () => {
    // P1: 44 × 120 nm, written along its height
    const full = labelFit([44, 120], true, "P1", "0.600 V", 1)!;
    expect(full.lines).toEqual(["P1  0.600 V"]);
    expect(full.fontNm * 1).toBeLessThanOrEqual(12);
    expect(labelFit([44, 120], true, "P1", "0.600 V", 0.5)!.lines).toEqual(["P1  0.600 V"]);
    expect(labelFit([44, 120], true, "P1", "0.600 V", 0.25)!.lines).toEqual(["P1"]);
    expect(labelFit([44, 120], true, "P1", "0.600 V", 0.1)).toBeNull();
    // R_L: 218 × 120 nm, two lines across
    const wide = labelFit([218, 120], false, "R_L", "0.700 V", 0.5)!;
    expect(wide.lines).toEqual(["R_L", "0.700 V"]);
    expect(wide.fontNm * 0.5).toBeCloseTo(12);
    expect(labelFit([218, 120], false, "R_L", "0.700 V", 0)).toBeNull();
  });
});
