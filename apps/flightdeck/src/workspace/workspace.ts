// The workspace: the layout model rendered as three columns of panes (ADR 0054). Structural changes
// (split, close, a different widget) re-render by reconciling pane ids, so an untouched pane keeps its
// DOM and its widget; resizes only touch styles. Gutters resize by pointer and by keyboard.
import type { Bus } from "./bus";
import { h } from "./dom";
import {
  canSplit,
  close,
  COLUMNS,
  columnOf,
  EMPTY_WIDGET,
  MAX_PLOT_PANES,
  type Column,
  type Layout,
  LAYOUT_KEY,
  type Pane,
  PLOT_WIDGET,
  resizeColumn,
  resizeRows,
  safeStorage,
  saveLayout,
  setPaneState,
  setWidget,
  split,
} from "./layout";
import type { Mounted, WidgetContext, WidgetRegistry } from "./widget";

interface PaneEls {
  section: HTMLElement;
  title: HTMLElement;
  picker: HTMLSelectElement | null;
  sub: HTMLElement;
  slot: HTMLElement;
  splitButton: HTMLButtonElement;
  closeButton: HTMLButtonElement;
  body: HTMLElement;
  mounted: Mounted;
}

export class Workspace {
  private layout: Layout;
  private readonly cols: Record<Column, HTMLElement>;
  private readonly panes = new Map<string, PaneEls>();
  private readonly ctx: Omit<WidgetContext, "bus" | "paneId" | "pane">;

  constructor(
    private readonly root: HTMLElement,
    private readonly registry: WidgetRegistry,
    private readonly bus: Bus,
    ctx: Omit<WidgetContext, "bus" | "layout" | "paneId" | "pane">,
    layout: Layout,
    /** Where this layout persists; a read server's layout has its own key (ADR 0074). */
    private readonly layoutKey: string = LAYOUT_KEY,
  ) {
    this.layout = layout;
    this.ctx = {
      ...ctx,
      layout: {
        addPlotPane: () => this.addPlotPane(),
        plotPanes: () => this.layout.center.map((p, i) => ({ id: p.id, label: `Plot ${i + 1}` })),
      },
    };
    this.cols = {
      left: h("div", { className: "col left", attrs: { "data-col": "left" } }),
      center: h("div", { className: "col center", attrs: { "data-col": "center" } }),
      right: h("div", { className: "col right", attrs: { "data-col": "right" } }),
    };
    root.replaceChildren(this.cols.left, this.columnGutter("left"), this.cols.center, this.columnGutter("right"), this.cols.right);
    this.applyWidths();
    this.render();
    window.addEventListener("resize", () => this.updateHeads());
  }

  get current(): Layout {
    return this.layout;
  }

  /** Another plot pane below the last one in the centre (a widget asks for this to open a record beside the
   * live map); its id, or null when the column is full or too short. */
  addPlotPane(): string | null {
    const last = this.layout.center.at(-1);
    if (!last) return null;
    const { layout, pane } = split(this.layout, last.id, PLOT_WIDGET, this.height("center"));
    this.commit(layout);
    return pane?.id ?? null;
  }

  private commit(next: Layout): void {
    if (next === this.layout) return;
    this.layout = next;
    this.render();
    saveLayout(this.layout, safeStorage(), this.layoutKey);
  }

  private height(column: Column): number {
    return this.cols[column].clientHeight || window.innerHeight - 60;
  }

  private applyWidths(): void {
    this.root.style.setProperty("--colL", `${(this.layout.widths.left * 100).toFixed(2)}%`);
    this.root.style.setProperty("--colR", `${(this.layout.widths.right * 100).toFixed(2)}%`);
  }

  // --- rendering -----------------------------------------------------------------------------------

  render(): void {
    for (const [id, e] of this.panes) {
      if (!columnOf(this.layout, id)) {
        e.mounted.unmount();
        e.section.remove();
        this.panes.delete(id);
      }
    }
    for (const column of COLUMNS) {
      const children: HTMLElement[] = [];
      this.layout[column].forEach((p, i) => {
        if (i > 0) children.push(this.rowGutter(column, i - 1));
        let e = this.panes.get(p.id);
        if (!e) {
          e = this.createPane(column, p);
          this.panes.set(p.id, e);
        } else if (e.mounted.widget.id !== p.widget) {
          e.mounted.unmount();
          e.slot.replaceChildren();
          e.body.replaceChildren();
          e.mounted = this.registry.mount(p.widget, p.id, e.body, e.slot, this.bus, this.paneCtx(p));
        }
        children.push(e.section);
      });
      this.cols[column].replaceChildren(...children);
    }
    this.applyWidths();
    this.updateHeads();
    this.bus.emit("layout:changed", {});
  }

  private createPane(column: Column, p: Pane): PaneEls {
    const title = h("span", { className: "title" });
    const picker = column === "center" ? null : h("select", { className: "picker", attrs: { "aria-label": "Widget for this pane" } });
    const sub = h("span", { className: "sub" });
    const slot = h("span", { className: "slot" });
    const splitButton = h("button", { className: "icon", type: "button", text: "+", attrs: { "data-split": "", "aria-label": "Add a pane below" } });
    const closeButton = h("button", { className: "icon", type: "button", text: "✕", attrs: { "data-close": "", "aria-label": "Close this pane" } });
    const body = h("div", { className: "pane-body" });
    const head = h("div", { className: "pane-head" }, picker ?? title, sub, h("span", { className: "right" }, slot, splitButton, closeButton));
    const section = h("section", { className: "pane", attrs: { "data-pane": p.id, "data-widget": p.widget } }, head, body);
    picker?.addEventListener("change", () => this.commit(setWidget(this.layout, p.id, picker.value)));
    splitButton.addEventListener("click", () => {
      const widget = column === "center" ? PLOT_WIDGET : EMPTY_WIDGET;
      this.commit(split(this.layout, p.id, widget, this.height(column)).layout);
    });
    closeButton.addEventListener("click", () => this.commit(close(this.layout, p.id)));
    const mounted = this.registry.mount(p.widget, p.id, body, slot, this.bus, this.paneCtx(p));
    return { section, title, picker, sub, slot, splitButton, closeButton, body, mounted };
  }

  /** The context one pane's widget mounts with: the shared one plus this pane's remembered state. */
  private paneCtx(p: Pane): Omit<WidgetContext, "bus" | "paneId"> {
    const state = this.layout[columnOf(this.layout, p.id)!].find((x) => x.id === p.id)?.state;
    return {
      ...this.ctx,
      pane: {
        state,
        save: (next) => {
          this.layout = setPaneState(this.layout, p.id, next);
          saveLayout(this.layout, safeStorage(), this.layoutKey);
        },
      },
    };
  }

  /** Titles, pickers, enabled buttons: everything in a head that depends on the layout around the pane. */
  private updateHeads(): void {
    for (const column of COLUMNS) {
      const panes = this.layout[column];
      const splittable = canSplit(this.layout, column, this.height(column));
      panes.forEach((p, i) => {
        const e = this.panes.get(p.id)!;
        const widget = e.mounted.widget;
        e.section.dataset.widget = p.widget;
        e.section.style.flexGrow = String(p.size);
        e.sub.textContent = widget.sub;
        if (column === "center") e.title.textContent = `Plot ${i + 1}`;
        if (e.picker) {
          e.picker.replaceChildren(...this.registry.selectable(p.widget).map((w) => new Option(w.label, w.id)));
          e.picker.value = p.widget;
        }
        const full = column === "center" && panes.length >= MAX_PLOT_PANES;
        e.splitButton.disabled = !splittable;
        e.splitButton.title = full ? `${MAX_PLOT_PANES} plot panes at most (each holds a WebGL2 context)` : splittable ? "Split: add a pane below" : "No room for another pane at this height";
        e.closeButton.disabled = panes.length < 2;
        e.closeButton.title = panes.length < 2 ? "The last pane of a column stays" : "Close this pane";
      });
    }
  }

  // --- gutters -------------------------------------------------------------------------------------

  private columnGutter(side: "left" | "right"): HTMLElement {
    const g = h("div", {
      className: "gutter v",
      tabIndex: 0,
      attrs: { role: "separator", "aria-orientation": "vertical", "aria-label": `Resize ${side} column`, "data-gutter": side },
    });
    const set = (width: number) => {
      this.layout = resizeColumn(this.layout, side, width);
      this.applyWidths();
    };
    g.addEventListener("pointerdown", (e) => {
      g.setPointerCapture(e.pointerId);
      g.classList.add("active");
      document.body.classList.add("resizing");
      const move = (ev: PointerEvent) => {
        const r = this.root.getBoundingClientRect();
        const f = (ev.clientX - r.left) / r.width;
        set(side === "left" ? f : 1 - f);
      };
      const up = () => {
        g.classList.remove("active");
        document.body.classList.remove("resizing");
        g.removeEventListener("pointermove", move);
        g.removeEventListener("pointerup", up);
        saveLayout(this.layout, safeStorage(), this.layoutKey);
        this.updateHeads();
      };
      g.addEventListener("pointermove", move);
      g.addEventListener("pointerup", up);
    });
    g.addEventListener("keydown", (e) => {
      const d = e.key === "ArrowLeft" ? -0.02 : e.key === "ArrowRight" ? 0.02 : 0;
      if (!d) return;
      e.preventDefault();
      set(this.layout.widths[side] + (side === "left" ? d : -d));
      saveLayout(this.layout, safeStorage(), this.layoutKey);
      this.updateHeads();
    });
    return g;
  }

  private rowGutter(column: Column, i: number): HTMLElement {
    const g = h("div", {
      className: "gutter h",
      tabIndex: 0,
      attrs: { role: "separator", "aria-orientation": "horizontal", "aria-label": "Resize the panes above and below" },
    });
    const apply = (fraction: number) => {
      this.layout = resizeRows(this.layout, column, i, fraction);
      for (const p of this.layout[column]) {
        const e = this.panes.get(p.id);
        if (e) e.section.style.flexGrow = String(p.size);
      }
    };
    const fraction = () => {
      const [a, b] = [this.layout[column][i]!, this.layout[column][i + 1]!];
      return a.size / (a.size + b.size);
    };
    g.addEventListener("pointerdown", (e) => {
      const [a, b] = [this.layout[column][i], this.layout[column][i + 1]];
      if (!a || !b) return;
      const top = this.panes.get(a.id)!.section.getBoundingClientRect().top;
      const bottom = this.panes.get(b.id)!.section.getBoundingClientRect().bottom;
      g.setPointerCapture(e.pointerId);
      g.classList.add("active");
      document.body.classList.add("resizing", "h");
      const move = (ev: PointerEvent) => apply((ev.clientY - top) / (bottom - top));
      const up = () => {
        g.classList.remove("active");
        document.body.classList.remove("resizing", "h");
        g.removeEventListener("pointermove", move);
        g.removeEventListener("pointerup", up);
        saveLayout(this.layout, safeStorage(), this.layoutKey);
      };
      g.addEventListener("pointermove", move);
      g.addEventListener("pointerup", up);
    });
    g.addEventListener("keydown", (e) => {
      const d = e.key === "ArrowUp" ? -0.05 : e.key === "ArrowDown" ? 0.05 : 0;
      if (!d) return;
      e.preventDefault();
      apply(fraction() + d);
      saveLayout(this.layout, safeStorage(), this.layoutKey);
    });
    return g;
  }
}
