// The control panel as one temporary widget (ADR 0054): what is left of `ControlPanel` after the sweep,
// pulse and history sections became widgets (ADR 0055, 0056): the held operating point, records,
// analysis and the tune-up runner. Later sessions extract those too and delete it.
import { ControlPanel } from "../control/panel";
import { h } from "../workspace/dom";
import type { Widget } from "../workspace/widget";

export const controlWidget: Widget = {
  id: "control",
  label: "Control",
  sub: "operating point · records · analysis · tune-up",
  single: true,
  mount(body, _head, ctx) {
    const root = h("div", { id: "control", className: "form-widget" });
    body.append(root);
    const panel = new ControlPanel(root, ctx.api, {
      say: (text, isError = false) => ctx.bus.emit("say", { text, error: isError }),
    });
    void panel.init();
    // click-to-set (ADR 0053): the plot offers a point; the panel knows the stand's channels
    ctx.bus.on("map:click", ({ point }) => panel.offerSetpoint(point));
    // a run finished elsewhere (the Sweep widget): the records list is stale
    ctx.bus.on("records:changed", () => void panel.refreshRecords());
    return () => body.replaceChildren();
  },
};
