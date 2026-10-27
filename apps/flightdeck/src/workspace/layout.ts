// The workspace layout model (ADR 0054): three columns, each a vertical stack of panes; the centre
// holds plot panes only. Pure functions over plain data, so split/close/resize invariants are unit
// tested; the DOM rendering is in workspace.ts. Layout is UI state per browser, not a schema object.

export type Column = "left" | "center" | "right";
export const COLUMNS: readonly Column[] = ["left", "center", "right"];

export interface Pane {
  id: string;
  /** Widget id from the registry; the centre column holds only `plot`. */
  widget: string;
  /** Relative height within the column (flex-grow); sizes in a column sum to 1 after normalize. */
  size: number;
  /** The widget's own view state, persisted with the layout (ADR 0061); opaque to the layout. */
  state?: Record<string, unknown>;
}

export interface Layout {
  left: Pane[];
  center: Pane[];
  right: Pane[];
  /** Side column widths as a fraction of the workspace; the centre takes the rest. */
  widths: { left: number; right: number };
}

/** A pane shorter than this cannot be split, and a split that would leave one this short is refused. */
export const MIN_PANE_HEIGHT = 180;
export const PLOT_WIDGET = "plot";
export const EMPTY_WIDGET = "empty";
export const MIN_SIDE = 0.12;
export const MAX_SIDE = 0.45;
export const MAX_SIDES = 0.75;
/** Plot panes at most: each holds a WebGL2 context and browsers allow 8–16 per page (ADR 0055). */
export const MAX_PLOT_PANES = 6;

let seq = 0;
export const newPaneId = (): string => `pane-${++seq}`;

export function defaultLayout(): Layout {
  return {
    left: [
      { id: newPaneId(), widget: "sweep", size: 0.45 },
      { id: newPaneId(), widget: "analysis", size: 0.25 },
      { id: newPaneId(), widget: "tuneup", size: 0.3 },
    ],
    center: [{ id: newPaneId(), widget: PLOT_WIDGET, size: 1 }],
    right: [
      { id: newPaneId(), widget: "pulse", size: 0.22 },
      { id: newPaneId(), widget: "levels", size: 0.38 },
      { id: newPaneId(), widget: "queue", size: 0.2 },
      { id: newPaneId(), widget: "history", size: 0.2 },
    ],
    widths: { left: 0.3, right: 0.26 },
  };
}

/** Against a read server (ADR 0074): the records and the plots; nothing that commands a stand exists. */
export function readOnlyLayout(): Layout {
  return {
    left: [{ id: newPaneId(), widget: "history", size: 1 }],
    center: [{ id: newPaneId(), widget: PLOT_WIDGET, size: 1 }],
    right: [{ id: newPaneId(), widget: EMPTY_WIDGET, size: 1 }],
    widths: { left: 0.3, right: 0.14 },
  };
}

export function columnOf(layout: Layout, paneId: string): Column | null {
  for (const c of COLUMNS) if (layout[c].some((p) => p.id === paneId)) return c;
  return null;
}

export function normalize(panes: Pane[]): Pane[] {
  const total = panes.reduce((a, p) => a + p.size, 0) || 1;
  return panes.map((p) => ({ ...p, size: p.size / total }));
}

/** Whether a column of pixel height `height` can take one more pane without any pane going below the minimum. */
export function canSplit(layout: Layout, column: Column, height: number): boolean {
  if (column === "center" && layout.center.length >= MAX_PLOT_PANES) return false;
  return height / (layout[column].length + 1) >= MIN_PANE_HEIGHT;
}

/** Split `paneId` in two: the new pane goes below it with the named widget and half its size.
 * Returns the same layout object and no pane when the column is too short or the widget is not
 * allowed in that column (plots only in the centre; never a plot at the sides). */
export function split(layout: Layout, paneId: string, widget: string, height: number): { layout: Layout; pane: Pane | null } {
  const column = columnOf(layout, paneId);
  if (!column || !canSplit(layout, column, height)) return { layout, pane: null };
  if ((column === "center") !== (widget === PLOT_WIDGET)) return { layout, pane: null };
  const panes = layout[column];
  const i = panes.findIndex((p) => p.id === paneId);
  const old = panes[i]!;
  const pane: Pane = { id: newPaneId(), widget, size: old.size / 2 };
  const next = [...panes.slice(0, i), { ...old, size: old.size / 2 }, pane, ...panes.slice(i + 1)];
  return { layout: { ...layout, [column]: normalize(next) }, pane };
}

/** Close a pane; its height goes to the pane above (or below, for the first). The last pane of a column stays. */
export function close(layout: Layout, paneId: string): Layout {
  const column = columnOf(layout, paneId);
  if (!column || layout[column].length < 2) return layout;
  const panes = layout[column];
  const i = panes.findIndex((p) => p.id === paneId);
  const rest = panes.filter((p) => p.id !== paneId);
  const j = Math.max(0, i - 1);
  rest[j] = { ...rest[j]!, size: rest[j]!.size + panes[i]!.size };
  return { ...layout, [column]: normalize(rest) };
}

/** Remember a widget's view state on its pane (a plot's variable, transform, colormap, …). */
export function setPaneState(layout: Layout, paneId: string, state: Record<string, unknown>): Layout {
  const column = columnOf(layout, paneId);
  if (!column) return layout;
  return { ...layout, [column]: layout[column].map((p) => (p.id === paneId ? { ...p, state } : p)) };
}

/** Change which widget a side pane shows (the centre is plots only). */
export function setWidget(layout: Layout, paneId: string, widget: string): Layout {
  const column = columnOf(layout, paneId);
  if (!column || column === "center" || widget === PLOT_WIDGET) return layout;
  return { ...layout, [column]: layout[column].map((p) => (p.id === paneId ? { ...p, widget, state: undefined } : p)) };
}

/** Move the boundary between pane `i` and `i+1` of a column so that `fraction` of their joint height
 * goes to the upper one; clamped so neither vanishes. */
export function resizeRows(layout: Layout, column: Column, i: number, fraction: number): Layout {
  const panes = layout[column];
  const a = panes[i];
  const b = panes[i + 1];
  if (!a || !b) return layout;
  const f = Math.min(0.85, Math.max(0.15, fraction));
  const total = a.size + b.size;
  const next = panes.map((p, k) => (k === i ? { ...p, size: total * f } : k === i + 1 ? { ...p, size: total * (1 - f) } : p));
  return { ...layout, [column]: next };
}

/** Set a side column's width (fraction of the workspace), clamped; the two sides never exceed MAX_SIDES together. */
export function resizeColumn(layout: Layout, side: "left" | "right", width: number): Layout {
  const widths = { ...layout.widths, [side]: Math.min(MAX_SIDE, Math.max(MIN_SIDE, width)) };
  const over = widths.left + widths.right - MAX_SIDES;
  if (over > 0) {
    widths.left -= over / 2;
    widths.right -= over / 2;
  }
  return { ...layout, widths };
}

/** Parse a stored layout; anything malformed falls back to the default so a stale key never breaks the app.
 * `known` lists the widget ids that exist; a side pane naming an unknown widget shows `empty`. */
export function parseLayout(text: string | null, known: readonly string[], makeFallback: () => Layout = defaultLayout): Layout {
  const fallback = makeFallback();
  if (!text) return fallback;
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return fallback;
  }
  if (!raw || typeof raw !== "object") return fallback;
  const r = raw as Partial<Record<Column, unknown>> & { widths?: unknown };
  const col = (c: Column): Pane[] | null => {
    const v = r[c];
    if (!Array.isArray(v) || v.length === 0) return null;
    const panes: Pane[] = [];
    for (const p of v as unknown[]) {
      if (!p || typeof p !== "object") return null;
      const { widget, size, state } = p as { widget?: unknown; size?: unknown; state?: unknown };
      if (typeof widget !== "string") return null;
      const w = c === "center" ? PLOT_WIDGET : widget === PLOT_WIDGET || !known.includes(widget) ? EMPTY_WIDGET : widget;
      const kept = state && typeof state === "object" && !Array.isArray(state) && w === widget ? (state as Record<string, unknown>) : undefined;
      panes.push({ id: newPaneId(), widget: w, size: typeof size === "number" && size > 0 ? size : 1, ...(kept ? { state: kept } : {}) });
    }
    return normalize(panes);
  };
  const left = col("left");
  const center = col("center");
  const right = col("right");
  if (!left || !center || !right) return fallback;
  const w = (r.widths ?? {}) as { left?: unknown; right?: unknown };
  let layout: Layout = { left, center, right, widths: fallback.widths };
  if (typeof w.left === "number") layout = resizeColumn(layout, "left", w.left);
  if (typeof w.right === "number") layout = resizeColumn(layout, "right", w.right);
  return layout;
}

/** The persisted form: widgets and sizes, never pane ids. */
export function serializeLayout(layout: Layout): string {
  const col = (panes: Pane[]) => panes.map(({ widget, size, state }) => ({ widget, size, ...(state ? { state } : {}) }));
  return JSON.stringify({ left: col(layout.left), center: col(layout.center), right: col(layout.right), widths: layout.widths });
}

/** Versioned: a new default layout (new widgets) retires the stored one rather than hiding them. */
export const LAYOUT_KEY = "flightdeck.layout.v5";
/** The layout against a read server lives under its own key: one browser may face both kinds of server. */
export const READ_ONLY_LAYOUT_KEY = "flightdeck.layout.read.v1";

/** localStorage is a per-viewer convenience: absent, blocked or full, the app still runs. */
export function loadLayout(
  known: readonly string[],
  storage: Pick<Storage, "getItem"> | null = safeStorage(),
  key: string = LAYOUT_KEY,
  makeFallback: () => Layout = defaultLayout,
): Layout {
  try {
    return parseLayout(storage?.getItem(key) ?? null, known, makeFallback);
  } catch {
    return makeFallback();
  }
}

export function saveLayout(layout: Layout, storage: Pick<Storage, "setItem"> | null = safeStorage(), key: string = LAYOUT_KEY): void {
  try {
    storage?.setItem(key, serializeLayout(layout));
  } catch {
    /* private window, quota, or no storage at all */
  }
}

export function safeStorage(): Storage | null {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}
