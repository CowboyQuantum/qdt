// The control panel as one temporary widget (ADR 0054, deliverable 1): `ControlPanel` is mounted
// unchanged so the shell lands without a behaviour change. Later sessions extract its sections (sweep,
// pulse, levels, virtual gates, history, methods, tune-up) into widgets of their own and delete it.
import { ControlPanel } from "../control/panel";
import { h } from "../workspace/dom";
import type { Widget } from "../workspace/widget";

export const controlWidget: Widget = {
  id: "control",
  label: "Control",
  sub: "sweep · operating point · runs · records · analysis · tune-up",
  single: true,
  mount(body, _head, ctx) {
    const root = h("div", { id: "control" });
    body.append(root);
    const panel = new ControlPanel(root, ctx.api, {
      say: (text, isError = false) => ctx.bus.emit("say", { text, error: isError }),
    });
    const form = () => root.querySelector<HTMLFormElement>("form#sweep");
    const value = (name: string) => {
      const el = form()?.elements.namedItem(name) as HTMLInputElement | HTMLSelectElement | null;
      return el?.value ?? "";
    };
    /** One line for the strip: what pressing Run would do, read from the form as it stands. */
    const next = () => {
      const kind = value("kind");
      const outer = value("outer_channel");
      const axes = kind === "capture" ? [outer && `${outer} ${value("outer_num")}`, value("capture_channel")] : [outer && `${outer} ${value("outer_num")}`, `${value("inner_channel")} ${value("inner_num")}`];
      ctx.bus.emit("run:next", { summary: `${value("name") || "sweep"} · ${kind} · ${axes.filter(Boolean).join(" × ")}` });
    };
    root.addEventListener("input", next);
    root.addEventListener("change", next);
    void panel.init().then(next);
    // the strip's Run is the panel's own submit: one action, two places until the sweep widget lands
    ctx.bus.on("run:request", () => form()?.requestSubmit());
    // click-to-set (ADR 0053): the plot offers a point; the panel knows the stand's channels
    ctx.bus.on("map:click", ({ point }) => panel.offerSetpoint(point));
    return () => {
      root.removeEventListener("input", next);
      root.removeEventListener("change", next);
      body.replaceChildren();
      ctx.bus.emit("run:next", { summary: "" });
    };
  },
};
