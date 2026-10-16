// The Levels widget (ADR 0038, 0053, 0057): the stand's operating point by channel. Every channel an
// instrument sets or senses, from `GET /levels/state`: the level the instrument holds, the level the
// server holds for it (every sweep inherits that, ADR 0053) and what the instrument reads back.
// Filterable (type, instrument, text, pinned, near-limit: AND across groups, OR within), sortable,
// pinnable, with an inline set that refuses a level beyond the limit and shows a settling state while
// the server applies it. Click-to-set lands here: the plot offers a point (`map:click`), this widget
// turns it into levels for the stand's DC channels and sets them. Polled while mounted; never stored.
import { ApiError } from "../api/client";
import type { ChannelLevel, ChannelMap, FixedLevel } from "../schema/api";
import { h } from "../workspace/dom";
import { safeStorage } from "../workspace/layout";
import type { Widget, WidgetContext } from "../workspace/widget";

/** A clicked point as the setpoint it means: the coordinates whose names are DC channels of the stand
 * become levels; the rest are reported as not settable (ADR 0053). Pure, so click-to-set is testable. */
export function setpointFor(point: { name: string; value: number }[], dc: readonly Pick<ChannelMap, "logical">[]): { levels: FixedLevel[]; skipped: string[] } {
  const names = new Set(dc.map((c) => c.logical));
  const levels: FixedLevel[] = [];
  const skipped: string[] = [];
  for (const p of point) {
    if (names.has(p.name) && Number.isFinite(p.value)) levels.push({ channel: p.name, value: p.value });
    else skipped.push(p.name);
  }
  return { levels, skipped };
}

export interface LevelFilters {
  /** Quantities to show; empty = all. */
  quantities: ReadonlySet<string>;
  /** Instruments to show; empty = all. */
  instruments: ReadonlySet<string>;
  text: string;
  pinnedOnly: boolean;
  nearLimit: boolean;
}

export const NO_FILTERS: LevelFilters = { quantities: new Set(), instruments: new Set(), text: "", pinnedOnly: false, nearLimit: false };
export type SortKey = "channel" | "instrument" | "setpoint" | "held" | "readback";

/** The fraction of the limit above which a setpoint counts as near it. */
export const NEAR = 0.9;

/** Whether a setpoint is within `NEAR` of the limit (either sign). Null setpoints never are. */
export function nearLimit(row: Pick<ChannelLevel, "setpoint">, limit: number): boolean {
  return row.setpoint !== null && row.setpoint !== undefined && Math.abs(row.setpoint) >= NEAR * limit;
}

/** AND across filter groups, OR within each. Pure. */
export function filterLevels(rows: readonly ChannelLevel[], f: LevelFilters, pinned: ReadonlySet<string>, limit: number): ChannelLevel[] {
  const q = f.text.trim().toLowerCase();
  return rows.filter(
    (r) =>
      (!f.quantities.size || f.quantities.has(r.quantity)) &&
      (!f.instruments.size || f.instruments.has(r.instrument)) &&
      (!q || `${r.channel} ${r.instrument}`.toLowerCase().includes(q)) &&
      (!f.pinnedOnly || pinned.has(r.channel)) &&
      (!f.nearLimit || nearLimit(r, limit)),
  );
}

/** Pinned rows first, then by `key`; nulls last within a direction. Pure, stable. */
export function sortLevels(rows: readonly ChannelLevel[], key: SortKey, dir: 1 | -1, pinned: ReadonlySet<string>): ChannelLevel[] {
  const val = (r: ChannelLevel) => r[key] ?? null;
  return [...rows].sort((a, b) => {
    const pa = pinned.has(a.channel) ? 0 : 1;
    const pb = pinned.has(b.channel) ? 0 : 1;
    if (pa !== pb) return pa - pb;
    const va = val(a);
    const vb = val(b);
    if (va === null && vb === null) return 0;
    if (va === null) return 1;
    if (vb === null) return -1;
    if (typeof va === "number" && typeof vb === "number") return dir * (va - vb);
    return dir * String(va).localeCompare(String(vb));
  });
}

/** Why a typed level cannot be set, or null when it can. */
export function checkSet(text: string, limit: number): string | null {
  const v = Number(text.trim());
  if (text.trim() === "" || !Number.isFinite(v)) return "not a number";
  if (Math.abs(v) > limit) return `beyond the limit of ±${limit}`;
  return null;
}

const PINNED_KEY = "flightdeck.levels.pinned.v1";
const LIMIT_KEY = "flightdeck.levels.limit.v1";
/** The default limit (SI unit of the channel): a browser setting until the stand declares one. */
export const DEFAULT_LIMIT = 1;
const POLL_MS = 2000;
const fmt = (v: number | null | undefined, unit: string) => (v === null || v === undefined ? "—" : `${Number(v.toPrecision(5))} ${unit}`);
const unitOf = (q: string) => (q === "current" ? "A" : "V");

export const levelsWidget: Widget = {
  id: "levels",
  label: "Levels",
  sub: "the operating point by channel: setpoint, held, readback",
  single: true,
  mount(body, head, ctx) {
    const w = new LevelsWidget(body, head, ctx);
    return () => w.unmount();
  },
};

class LevelsWidget {
  private rows: ChannelLevel[] = [];
  private pinned = new Set<string>();
  private filters: LevelFilters = { ...NO_FILTERS, quantities: new Set(), instruments: new Set() };
  private sort: { key: SortKey; dir: 1 | -1 } = { key: "channel", dir: 1 };
  private limit = DEFAULT_LIMIT;
  private settling = new Set<string>();
  private offer: { levels: FixedLevel[]; skipped: string[]; text: string } | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private readonly tbody: HTMLTableSectionElement;
  private readonly filterBar: HTMLDivElement;
  private readonly offerBox: HTMLDivElement;
  private readonly foot: HTMLDivElement;
  private readonly offs: (() => void)[] = [];

  constructor(
    private readonly body: HTMLElement,
    private readonly head: HTMLElement,
    private readonly ctx: WidgetContext,
  ) {
    const storage = safeStorage();
    try {
      this.pinned = new Set(JSON.parse(storage?.getItem(PINNED_KEY) ?? "[]") as string[]);
      const limit = Number(storage?.getItem(LIMIT_KEY));
      if (Number.isFinite(limit) && limit > 0) this.limit = limit;
    } catch {
      /* no storage */
    }
    this.tbody = h("tbody");
    this.filterBar = h("div", { className: "filters" });
    this.offerBox = h("div", { className: "offer" });
    this.foot = h("div", { className: "foot" });
    const refresh = h("button", { type: "button", text: "refresh", attrs: { "data-refresh": "" } });
    refresh.addEventListener("click", () => void this.refresh());
    const release = h("button", { type: "button", text: "release", title: "Forget the held operating point; the stand stays where it is", attrs: { "data-release": "" } });
    release.addEventListener("click", () => void this.release());
    head.append(refresh, release);
    const headers: [SortKey | null, string][] = [
      ["channel", "channel"],
      ["instrument", "instrument"],
      ["setpoint", "setpoint"],
      ["held", "held"],
      ["readback", "readback"],
      [null, "set"],
    ];
    body.append(
      h(
        "div",
        { className: "dc" },
        this.filterBar,
        this.offerBox,
        h(
          "div",
          { className: "tbl" },
          h(
            "table",
            { className: "dct" },
            h(
              "thead",
              {},
              h(
                "tr",
                {},
                h("th", { text: "", title: "pinned first" }),
                ...headers.map(([key, label]) => {
                  const th = h("th", { text: label, className: key && ["setpoint", "held", "readback"].includes(key) ? "num" : "" });
                  if (key) {
                    th.addEventListener("click", () => {
                      this.sort = { key, dir: this.sort.key === key ? ((-this.sort.dir) as 1 | -1) : 1 };
                      this.render();
                    });
                    th.dataset.sort = key;
                  }
                  return th;
                }),
              ),
            ),
            this.tbody,
          ),
        ),
        this.foot,
      ),
    );
    this.renderFilters();
    this.offs.push(
      ctx.bus.on("map:click", ({ point }) => this.offerPoint(point)),
      // a run leaves its last level on the stand (ADR 0038): read again when one ends
      ctx.bus.on("run:state", ({ run }) => {
        if (run && ["completed", "aborted", "failed"].includes(run.state)) void this.refresh();
      }),
    );
    void this.refresh();
    this.timer = setInterval(() => void this.refresh(true), POLL_MS);
  }

  unmount(): void {
    if (this.timer) clearInterval(this.timer);
    for (const off of this.offs.splice(0)) off();
    this.body.replaceChildren();
    this.head.replaceChildren();
  }

  private say(text: string, error = false): void {
    this.ctx.bus.emit("say", { text, error });
  }

  private savePins(): void {
    try {
      safeStorage()?.setItem(PINNED_KEY, JSON.stringify([...this.pinned]));
    } catch {
      /* no storage */
    }
  }

  // --- data ----------------------------------------------------------------------------------------

  async refresh(quiet = false): Promise<void> {
    try {
      this.rows = await this.ctx.api.levelState();
      this.render();
    } catch (e) {
      if (!quiet) this.say(`levels: ${describe(e)}`, true);
    }
  }

  private async set(levels: FixedLevel[]): Promise<void> {
    for (const l of levels) this.settling.add(l.channel);
    this.render();
    try {
      await this.ctx.api.setLevels(levels);
      this.say(`set ${levels.map((l) => `${l.channel}=${Number(l.value.toPrecision(5))}`).join(", ")} on the stand`);
      this.ctx.bus.emit("levels:changed", {});
    } catch (e) {
      this.say(describe(e), true);
    } finally {
      for (const l of levels) this.settling.delete(l.channel);
      await this.refresh();
    }
  }

  private async release(): Promise<void> {
    try {
      await this.ctx.api.clearLevels();
      this.say("released the held operating point; the stand stays where it is");
      this.ctx.bus.emit("levels:changed", {});
    } catch (e) {
      this.say(describe(e), true);
    }
    await this.refresh();
  }

  /** Click-to-set (ADR 0053): the point's coordinates that are DC channels become levels to offer. */
  private offerPoint(point: { name: string; unit: string; value: number }[]): void {
    const dc = this.rows.filter((r) => r.quantity === "voltage" && r.setpoint !== null);
    const { levels, skipped } = setpointFor(point, dc.map((r) => ({ logical: r.channel })));
    const text = point.map((p) => `${p.name} = ${p.value.toPrecision(4)}${p.unit ? ` ${p.unit}` : ""}`).join(" · ");
    this.offer = { levels, skipped, text };
    this.renderOffer();
  }

  // --- rendering -----------------------------------------------------------------------------------

  private renderFilters(): void {
    const chip = (label: string, on: boolean, toggle: () => void) => {
      const b = h("button", { type: "button", className: `chip${on ? " on" : ""}`, text: label, attrs: { "aria-pressed": String(on) } });
      b.addEventListener("click", () => {
        toggle();
        this.renderFilters();
        this.render();
      });
      return b;
    };
    const toggleIn = (set: Set<string>, v: string) => (set.has(v) ? set.delete(v) : set.add(v));
    const quantities = [...new Set(this.rows.map((r) => r.quantity))];
    const instruments = [...new Set(this.rows.map((r) => r.instrument))];
    const text = h("input", { type: "search", name: "filter", value: this.filters.text, placeholder: "channel…", attrs: { "aria-label": "Filter channels" } });
    text.addEventListener("input", () => {
      this.filters.text = text.value;
      this.render();
    });
    const limit = h("input", { type: "number", name: "limit", value: String(this.limit), step: "any", min: "0", title: "The level beyond which a set is refused (a browser setting)", attrs: { "aria-label": "Limit" } });
    limit.addEventListener("change", () => {
      const v = Number(limit.value);
      if (!(v > 0)) return;
      this.limit = v;
      try {
        safeStorage()?.setItem(LIMIT_KEY, String(v));
      } catch {
        /* no storage */
      }
      this.render();
    });
    this.filterBar.replaceChildren(
      h("span", { className: "group" }, h("span", { className: "glabel", text: "type" }), ...quantities.map((q) => chip(q, this.filters.quantities.has(q), () => toggleIn(this.filters.quantities as Set<string>, q)))),
      h("span", { className: "group" }, h("span", { className: "glabel", text: "instrument" }), ...instruments.map((i) => chip(i, this.filters.instruments.has(i), () => toggleIn(this.filters.instruments as Set<string>, i)))),
      h(
        "span",
        { className: "group" },
        chip("pinned", this.filters.pinnedOnly, () => (this.filters.pinnedOnly = !this.filters.pinnedOnly)),
        chip("near limit", this.filters.nearLimit, () => (this.filters.nearLimit = !this.filters.nearLimit)),
      ),
      text,
      h("label", { className: "glabel" }, "limit ±", limit),
    );
  }

  private renderOffer(): void {
    const o = this.offer;
    if (!o) return this.offerBox.replaceChildren();
    const set = h("button", { type: "button", text: `set ${o.levels.map((l) => l.channel).join(", ")} from the map`, attrs: { "data-offer": "" } });
    set.addEventListener("click", () => void this.set(o.levels));
    this.offerBox.replaceChildren(
      h("span", { className: "clicked", text: `clicked: ${o.text}` }),
      ...(o.levels.length ? [set] : []),
      ...(o.skipped.length ? [h("span", { className: "hint", text: ` (${o.skipped.join(", ")}: not a DC channel of the stand)` })] : []),
    );
  }

  private render(): void {
    // the filter chips follow the rows (a new instrument, a new quantity) without losing their state
    if (this.filterBar.querySelectorAll(".chip").length !== new Set(this.rows.map((r) => r.quantity)).size + new Set(this.rows.map((r) => r.instrument)).size + 2) this.renderFilters();
    const shown = sortLevels(filterLevels(this.rows, this.filters, this.pinned, this.limit), this.sort.key, this.sort.dir, this.pinned);
    for (const th of this.body.querySelectorAll<HTMLElement>("th[data-sort]")) {
      th.classList.toggle("sorted", th.dataset.sort === this.sort.key);
      th.setAttribute("aria-sort", th.dataset.sort === this.sort.key ? (this.sort.dir === 1 ? "ascending" : "descending") : "none");
    }
    this.tbody.replaceChildren(
      ...shown.map((r) => {
        const unit = unitOf(r.quantity);
        const pin = h("button", { type: "button", className: `pin${this.pinned.has(r.channel) ? " on" : ""}`, text: this.pinned.has(r.channel) ? "★" : "☆", title: "pin", attrs: { "aria-pressed": String(this.pinned.has(r.channel)) } });
        pin.addEventListener("click", () => {
          if (this.pinned.has(r.channel)) this.pinned.delete(r.channel);
          else this.pinned.add(r.channel);
          this.savePins();
          this.render();
        });
        const settable = r.setpoint !== null && r.setpoint !== undefined;
        const input = h("input", { type: "number", name: `set_${r.channel}`, step: "any", placeholder: unit, disabled: !settable, attrs: { "aria-label": `Set ${r.channel}` } });
        const button = h("button", { type: "button", text: "set", disabled: !settable });
        const badge = h("span", { className: "badge", hidden: true });
        if (this.settling.has(r.channel)) {
          badge.hidden = false;
          badge.className = "badge settling";
          badge.textContent = "settling";
        }
        const apply = () => {
          const why = checkSet(input.value, this.limit);
          if (why) {
            badge.hidden = false;
            badge.className = "badge limit";
            badge.textContent = why;
            return;
          }
          void this.set([{ channel: r.channel, value: Number(input.value) }]);
        };
        button.addEventListener("click", apply);
        input.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            apply();
          }
        });
        return h(
          "tr",
          { className: `${this.pinned.has(r.channel) ? "pinned" : ""}${nearLimit(r, this.limit) ? " near" : ""}`, attrs: { "data-channel": r.channel } },
          h("td", {}, pin),
          h("td", { text: r.channel }, h("span", { className: "typeTag", text: ` ${r.quantity}` })),
          h("td", { text: r.instrument }),
          h("td", { className: "num setpoint", text: fmt(r.setpoint, unit) }),
          h("td", { className: "num held", text: fmt(r.held, unit) }),
          h("td", { className: "num readback", text: fmt(r.readback, unit) }),
          h("td", {}, input, button, badge),
        );
      }),
    );
    const held = this.rows.filter((r) => r.held !== null && r.held !== undefined);
    this.foot.replaceChildren(
      h("span", { className: "held-summary", text: held.length ? `held: ${held.map((r) => `${r.channel} = ${Number(r.held!.toPrecision(5))} ${unitOf(r.quantity)}`).join(" · ")}` : "held: nothing (the stand is where the last sweep left it)" }),
      h("span", { className: "hint", text: `${shown.length} of ${this.rows.length} channels` }),
    );
    this.renderOffer();
  }
}

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.status} ${e.detail}`;
  return e instanceof Error ? e.message : String(e);
}
