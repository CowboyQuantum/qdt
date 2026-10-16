// The widget contract (ADR 0054): the registry, mount/unmount symmetry (no leaked listeners), bus typing.
import { describe, expect, expectTypeOf, it } from "vitest";
import { Bus, type Events, ScopedBus } from "../src/workspace/bus";
import { type Widget, type WidgetContext, WidgetRegistry } from "../src/workspace/widget";

const el = () => ({ textContent: "" }) as unknown as HTMLElement;
const ctx = () => ({ api: {}, datasets: {}, params: new URLSearchParams(), layout: { addPlotPane() {} } }) as unknown as Omit<WidgetContext, "bus">;

const widget = (id: string, extra: Partial<Widget> = {}, onMount?: (c: WidgetContext) => () => void): Widget => ({
  id,
  label: id,
  sub: `the ${id} widget`,
  mount: (_b, _h, c) => onMount?.(c) ?? (() => {}),
  ...extra,
});

describe("Bus", () => {
  it("delivers typed payloads, unsubscribes by handle or by off, and tolerates off during emit", () => {
    const bus = new Bus();
    const seen: string[] = [];
    const off = bus.on("stream:state", (p) => {
      expectTypeOf(p).toEqualTypeOf<Events["stream:state"]>();
      seen.push(p.state);
    });
    const once = bus.on("stream:state", (p) => {
      seen.push(`once:${p.state}`);
      once();
    });
    bus.emit("stream:state", { state: "live", progress: 0.5, summary: "" });
    bus.emit("stream:state", { state: "complete", progress: 1, summary: "" });
    expect(seen).toEqual(["live", "once:live", "complete"]);
    expect(bus.count("stream:state")).toBe(1);
    off();
    expect(bus.count()).toBe(0);
    // @ts-expect-error — a payload of the wrong shape does not compile
    bus.emit("stream:state", { state: "live" });
    // @ts-expect-error — an event that is not in Events does not compile
    bus.on("no:such", () => {});
  });

  it("a scoped bus drops everything it subscribed on dispose, and emits straight through", () => {
    const bus = new Bus();
    const scoped = new ScopedBus(bus);
    let n = 0;
    scoped.on("say", () => n++);
    scoped.on("run:request", () => n++);
    bus.on("say", () => n++);
    scoped.emit("say", { text: "hi", error: false });
    expect(n).toBe(2);
    expect(bus.count()).toBe(3);
    scoped.dispose();
    expect(bus.count()).toBe(1);
    scoped.emit("say", { text: "again", error: false });
    expect(n).toBe(3);
  });
});

describe("WidgetRegistry", () => {
  it("registers once per id and lists what a side pane may switch to: never the plot, never a busy single", () => {
    const r = new WidgetRegistry().register(widget("plot", { single: true })).register(widget("control", { single: true })).register(widget("empty"));
    expect(() => r.register(widget("empty"))).toThrow(/twice/);
    expect(r.ids()).toEqual(["plot", "control", "empty"]);
    expect(r.selectable().map((w) => w.id)).toEqual(["control", "empty"]);
    const m = r.mount("control", el(), el(), new Bus(), ctx());
    expect(r.selectable().map((w) => w.id)).toEqual(["empty"]);
    expect(r.selectable("control").map((w) => w.id)).toEqual(["control", "empty"]); // the pane that has it keeps it
    m.unmount();
    expect(r.selectable().map((w) => w.id)).toEqual(["control", "empty"]);
  });

  it("mount and unmount are symmetric: a widget's bus subscriptions go even when it forgets them", () => {
    const bus = new Bus();
    let unmounted = 0;
    const forgetful = widget("forgetful", {}, (c) => {
      c.bus.on("say", () => {});
      c.bus.on("stream:dataset", () => {});
      return () => unmounted++;
    });
    const r = new WidgetRegistry().register(forgetful);
    const m = r.mount("forgetful", el(), el(), bus, ctx());
    expect(bus.count()).toBe(2);
    expect(r.instances("forgetful")).toBe(1);
    m.unmount();
    m.unmount(); // idempotent
    expect(unmounted).toBe(1);
    expect(bus.count()).toBe(0);
    expect(r.instances("forgetful")).toBe(0);
  });

  it("a single-instance widget mounted twice shows a notice the second time and never calls mount", () => {
    let mounts = 0;
    const r = new WidgetRegistry().register(widget("control", { single: true }, () => (mounts++, () => {})));
    const bus = new Bus();
    const a = r.mount("control", el(), el(), bus, ctx());
    const body = el();
    const b = r.mount("control", body, el(), bus, ctx());
    expect(mounts).toBe(1);
    expect(body.textContent).toMatch(/already open/);
    expect(r.instances("control")).toBe(1);
    b.unmount();
    expect(r.instances("control")).toBe(1);
    a.unmount();
    expect(r.instances("control")).toBe(0);
    r.mount("control", el(), el(), bus, ctx());
    expect(mounts).toBe(2);
  });

  it("an unknown widget id mounts the empty widget, so a stale layout never breaks a pane", () => {
    const r = new WidgetRegistry().register(widget("empty"));
    expect(r.mount("gone", el(), el(), new Bus(), ctx()).widget.id).toBe("empty");
    expect(() => new WidgetRegistry().mount("gone", el(), el(), new Bus(), ctx())).toThrow(/no widget/);
  });
});
