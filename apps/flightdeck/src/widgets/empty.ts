// A pane with nothing in it yet: what a fresh split shows until the user picks a widget.
import { h } from "../workspace/dom";
import type { Widget } from "../workspace/widget";

export const emptyWidget: Widget = {
  id: "empty",
  label: "Empty",
  sub: "pick a widget for this pane",
  mount(body) {
    body.append(h("div", { className: "empty", text: "Choose a widget from the menu in this pane's head." }));
    return () => body.replaceChildren();
  },
};
