// The widget contract and registry (ADR 0054). A widget is mounted into a pane's body and head and
// returns its unmount; it reaches the server only through the ApiClient in its context, the data
// through the shared stores, and other widgets through the bus. Mount and unmount are symmetric: the
// registry scopes the bus per mount and disposes it, so a closed pane leaks no listener.
import type { ApiClient } from "../api/client";
import type { Datasets } from "../stream/datasets";
import { Bus, ScopedBus } from "./bus";

export interface WidgetContext {
  readonly api: ApiClient;
  /** Every announced Dataset, by id, with the newest marked; shared by every pane. */
  readonly datasets: Datasets;
  readonly bus: ScopedBus;
  /** URL parameters the app was opened with (renderer choice, bench flag). */
  readonly params: URLSearchParams;
  /** The pane this mount lives in; events that target a pane name it. */
  readonly paneId: string;
  /** This pane's remembered view state and how to update it; persisted with the layout (ADR 0061). */
  readonly pane: { readonly state: Record<string, unknown> | undefined; save(state: Record<string, unknown>): void };
  /** Layout operations a widget may ask for: another plot pane (null when refused), the plot panes by label. */
  readonly layout: { addPlotPane(): string | null; plotPanes(): { id: string; label: string }[] };
}

export interface Widget {
  /** Registry id, also what the layout persists. */
  readonly id: string;
  readonly label: string;
  /** One line under the label in the pane head. */
  readonly sub: string;
  /** At most one pane may show this widget at a time (the temporary control panel; the plot until N panes land). */
  readonly single?: boolean;
  /** Build into `body`; `head` is the pane head's slot for the widget's own controls. Return the unmount. */
  mount(body: HTMLElement, head: HTMLElement, ctx: WidgetContext): () => void;
}

export interface Mounted {
  readonly widget: Widget;
  unmount(): void;
}

export class WidgetRegistry {
  private readonly widgets = new Map<string, Widget>();
  private readonly mounted = new Map<string, number>();

  register(widget: Widget): this {
    if (this.widgets.has(widget.id)) throw new Error(`widget ${widget.id} registered twice`);
    this.widgets.set(widget.id, widget);
    return this;
  }

  get(id: string): Widget | undefined {
    return this.widgets.get(id);
  }

  ids(): string[] {
    return [...this.widgets.keys()];
  }

  list(): Widget[] {
    return [...this.widgets.values()];
  }

  /** Widgets a side pane may switch to now: every registered one that is not a plot and not a busy single. */
  selectable(current?: string): Widget[] {
    return this.list().filter((w) => w.id !== "plot" && (w.id === current || !w.single || !this.instances(w.id)));
  }

  instances(id: string): number {
    return this.mounted.get(id) ?? 0;
  }

  /** Mount a widget into a pane with a bus scoped to that mount. A single-instance widget that is
   * already mounted gets a notice instead, so the layout can name it twice without breaking. */
  mount(id: string, paneId: string, body: HTMLElement, head: HTMLElement, bus: Bus, ctx: Omit<WidgetContext, "bus" | "paneId">): Mounted {
    // (the context carries this pane's remembered state; the workspace supplies it per pane)
    const widget = this.widgets.get(id) ?? this.widgets.get("empty");
    if (!widget) throw new Error(`no widget ${id} and no empty widget to fall back on`);
    const scoped = new ScopedBus(bus);
    const n = this.instances(widget.id);
    if (widget.single && n > 0) {
      body.textContent = `${widget.label} is already open in another pane`;
      return { widget, unmount: () => scoped.dispose() };
    }
    this.mounted.set(widget.id, n + 1);
    const unmount = widget.mount(body, head, { ...ctx, bus: scoped, paneId });
    let done = false;
    return {
      widget,
      unmount: () => {
        if (done) return;
        done = true;
        unmount();
        scoped.dispose();
        this.mounted.set(widget.id, this.instances(widget.id) - 1);
      },
    };
  }
}
