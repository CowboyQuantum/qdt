// The Levels widget (ADR 0038, 0053, 0057): the stand's operating point by channel. Every channel an
// instrument sets or senses, from `GET /levels/state`: the level the instrument holds, the level the
// server holds for it (every sweep inherits that, ADR 0053) and what the instrument reads back.
// Filterable (type, instrument, text, pinned, near-limit: AND across groups, OR within), sortable,
// pinnable, with an inline set that refuses a level beyond the channel's limit and shows a settling
// state while the server applies it. Click-to-set lands here: the plot offers a point (`map:click`),
// this widget turns it into levels for the stand's DC channels and sets them. Polled while mounted.
// The limits are the stand's (ADR 0075, 0085): read from `GET /stand/state`, changed through
// `POST /stand/state` with a reason, enforced by the server whatever this widget checks. After a
// restart the server offers the held point it had (`GET /levels/pending`); this widget asks a person
// to confirm or discard it. Filters, sort and pins stay per browser.
import { ApiError } from "../api/client";
import type { ChannelLevel, ChannelLimit, ChannelMap, FixedLevel, StandState } from "../schema/api";
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

/** The stand's limits by channel; a channel without one is absent. */
export type Limits = ReadonlyMap<string, Pick<ChannelLimit, "min_v" | "max_v">>;

/** The limits of a stand state by channel. Pure. */
export function limitsOf(state: Pick<StandState, "limits"> | null): Map<string, ChannelLimit> {
  return new Map((state?.limits ?? []).map((l) => [l.channel, l]));
}

/** The fraction of a limit's span that counts as near either end. */
export const NEAR = 0.1;

/** Whether a setpoint lies within `NEAR` of its limit's span from either end. A channel without a
 * limit, or a null setpoint, never is. */
export function nearLimit(row: Pick<ChannelLevel, "setpoint">, limit: Pick<ChannelLimit, "min_v" | "max_v"> | undefined): boolean {
  if (!limit || row.setpoint === null || row.setpoint === undefined) return false;
  const margin = NEAR * (limit.max_v - limit.min_v);
  return row.setpoint >= limit.max_v - margin || row.setpoint <= limit.min_v + margin;
}

/** A limit as a person reads it, e.g. "[-0.5, 1.2] V". */
export function describeLimit(limit: Pick<ChannelLimit, "min_v" | "max_v"> | undefined, unit: string): string {
  return limit ? `[${Number(limit.min_v.toPrecision(5))}, ${Number(limit.max_v.toPrecision(5))}] ${unit}` : "none";
}

/** The stand's limits after setting (or, with `range` null, removing) one channel's: every limit,
 * as `POST /stand/state` takes them. Pure. */
export function withLimit(limits: readonly ChannelLimit[], channel: string, range: { min_v: number; max_v: number } | null): ChannelLimit[] {
  const rest = limits.filter((l) => l.channel !== channel).map(({ channel: c, min_v, max_v }) => ({ channel: c, min_v, max_v }));
  return range ? [...rest, { channel, ...range }].sort((a, b) => a.channel.localeCompare(b.channel)) : rest;
}

/** Why a typed limit cannot be set, or null when it can. */
export function checkLimit(minText: string, maxText: string): string | null {
  const lo = Number(minText.trim());
  const hi = Number(maxText.trim());
  if (minText.trim() === "" || maxText.trim() === "" || !Number.isFinite(lo) || !Number.isFinite(hi)) return "give both ends as numbers";
  if (hi < lo) return "the highest level is below the lowest";
  return null;
}

/** AND across filter groups, OR within each. Pure. */
export function filterLevels(rows: readonly ChannelLevel[], f: LevelFilters, pinned: ReadonlySet<string>, limits: Limits): ChannelLevel[] {
  const q = f.text.trim().toLowerCase();
  return rows.filter(
    (r) =>
      (!f.quantities.size || f.quantities.has(r.quantity)) &&
      (!f.instruments.size || f.instruments.has(r.instrument)) &&
      (!q || `${r.channel} ${r.instrument}`.toLowerCase().includes(q)) &&
      (!f.pinnedOnly || pinned.has(r.channel)) &&
      (!f.nearLimit || nearLimit(r, limits.get(r.channel))),
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

/** Why a typed level cannot be set, or null when it can. The server checks the same limit. */
export function checkSet(text: string, limit: Pick<ChannelLimit, "min_v" | "max_v"> | undefined, unit = "V"): string | null {
  const v = Number(text.trim());
  if (text.trim() === "" || !Number.isFinite(v)) return "not a number";
  if (limit && (v < limit.min_v || v > limit.max_v)) return `beyond the stand's limit ${describeLimit(limit, unit)}`;
  return null;
}

const PINNED_KEY = "flightdeck.levels.pinned.v1";
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
  /** The stand state in force (ADR 0085) and its limits by channel; null until read. */
  private state: StandState | null = null;
  private limits = new Map<string, ChannelLimit>();
  /** The held point the server offers after a restart (ADR 0085); empty when nothing waits. */
  private pending: FixedLevel[] = [];
  private settling = new Set<string>();
  /** Why a channel's last set was refused, until the next set or a keystroke. */
  private readonly notes = new Map<string, string>();
  private readonly rowEls = new Map<string, RowEls>();
  private offer: { levels: FixedLevel[]; skipped: string[]; text: string } | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private readonly tbody: HTMLTableSectionElement;
  private readonly filterBar: HTMLDivElement;
  private readonly offerBox: HTMLDivElement;
  private readonly pendingBox: HTMLDivElement;
  private readonly limitBox: HTMLDivElement;
  private readonly limitChannel: HTMLSelectElement;
  private readonly limitMin: HTMLInputElement;
  private readonly limitMax: HTMLInputElement;
  private readonly limitReason: HTMLInputElement;
  private readonly limitNote: HTMLSpanElement;
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
    } catch {
      /* no storage */
    }
    this.tbody = h("tbody");
    this.filterBar = h("div", { className: "filters" });
    this.offerBox = h("div", { className: "offer" });
    this.pendingBox = h("div", { className: "pending", attrs: { "data-pending": "" } });
    this.foot = h("div", { className: "foot" });
    // the stand's limits (ADR 0085): one channel at a time, with a reason the stand state keeps
    this.limitChannel = h("select", { name: "limit_channel", attrs: { "aria-label": "Channel to limit" } });
    this.limitMin = h("input", { type: "number", name: "limit_min", step: "any", placeholder: "lowest", attrs: { "aria-label": "Lowest level allowed" } });
    this.limitMax = h("input", { type: "number", name: "limit_max", step: "any", placeholder: "highest", attrs: { "aria-label": "Highest level allowed" } });
    this.limitReason = h("input", { type: "text", name: "limit_reason", placeholder: "why (kept with the stand state)", attrs: { "aria-label": "Why the limit changes" } });
    this.limitNote = h("span", { className: "hint", attrs: { "data-limit-note": "" } });
    const setLimit = h("button", { type: "button", text: "set limit", attrs: { "data-set-limit": "" } });
    setLimit.addEventListener("click", () => void this.changeLimit(true));
    const removeLimit = h("button", { type: "button", text: "remove limit", attrs: { "data-remove-limit": "" } });
    removeLimit.addEventListener("click", () => void this.changeLimit(false));
    this.limitChannel.addEventListener("change", () => this.fillLimit());
    this.limitBox = h("div", { className: "limits" }, h("span", { className: "glabel", text: "limit" }), this.limitChannel, this.limitMin, this.limitMax, this.limitReason, setLimit, removeLimit, this.limitNote);
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
      [null, "limit"],
      [null, "set"],
    ];
    body.append(
      h(
        "div",
        { className: "dc" },
        this.pendingBox,
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
        this.limitBox,
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
      const [rows, state, pending] = await Promise.all([this.ctx.api.levelState(), this.ctx.api.standState(), this.ctx.api.pendingLevels()]);
      this.rows = rows;
      this.state = state;
      this.limits = limitsOf(state);
      this.pending = pending;
      this.render();
    } catch (e) {
      if (!quiet) this.say(`levels: ${describe(e)}`, true);
    }
  }

  /** Re-apply (or not) the held point the server offers after a restart (ADR 0085). */
  private async decidePending(confirm: boolean): Promise<void> {
    try {
      if (confirm) await this.ctx.api.confirmLevels();
      else await this.ctx.api.discardLevels();
      this.say(confirm ? "re-applied the held point from before the restart" : "the held point from before the restart was not re-applied");
      this.ctx.bus.emit("levels:changed", {});
    } catch (e) {
      this.say(describe(e), true);
    }
    await this.refresh();
  }

  /** Set or remove the chosen channel's limit: the stand state's next version, with the reason. */
  private async changeLimit(set: boolean): Promise<void> {
    const channel = this.limitChannel.value;
    const reason = this.limitReason.value.trim();
    const why = !channel ? "choose a channel" : !reason ? "say why the limit changes" : set ? checkLimit(this.limitMin.value, this.limitMax.value) : this.limits.has(channel) ? null : `${channel} has no limit`;
    if (why) {
      this.limitNote.textContent = why;
      return;
    }
    const range = set ? { min_v: Number(this.limitMin.value), max_v: Number(this.limitMax.value) } : null;
    try {
      const state = await this.ctx.api.changeStandState({ limits: withLimit(this.state?.limits ?? [], channel, range), reason });
      this.limitNote.textContent = "";
      this.limitReason.value = "";
      this.say(set ? `${channel} limited to ${describeLimit(range!, "")}(stand state v${state.version})` : `${channel}'s limit removed (stand state v${state.version})`);
    } catch (e) {
      this.limitNote.textContent = describe(e);
    }
    await this.refresh();
  }

  /** The editor shows the chosen channel's limit, so changing one end starts from the other. */
  private fillLimit(): void {
    const l = this.limits.get(this.limitChannel.value);
    this.limitMin.value = l ? String(l.min_v) : "";
    this.limitMax.value = l ? String(l.max_v) : "";
  }

  private async set(levels: FixedLevel[]): Promise<void> {
    for (const l of levels) {
      this.settling.add(l.channel);
      this.notes.delete(l.channel);
    }
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

  /** Rows are kept per channel and updated in place: a poll never replaces an input the user is typing in,
   * and a refusal note stays until the next set. The order changes only when the sort or filter does. */
  private render(): void {
    // the filter chips follow the rows (a new instrument, a new quantity) without losing their state
    if (this.filterBar.querySelectorAll(".chip").length !== new Set(this.rows.map((r) => r.quantity)).size + new Set(this.rows.map((r) => r.instrument)).size + 2) this.renderFilters();
    const shown = sortLevels(filterLevels(this.rows, this.filters, this.pinned, this.limits), this.sort.key, this.sort.dir, this.pinned);
    for (const th of this.body.querySelectorAll<HTMLElement>("th[data-sort]")) {
      th.classList.toggle("sorted", th.dataset.sort === this.sort.key);
      th.setAttribute("aria-sort", th.dataset.sort === this.sort.key ? (this.sort.dir === 1 ? "ascending" : "descending") : "none");
    }
    const trs = shown.map((r) => {
      const unit = unitOf(r.quantity);
      let e = this.rowEls.get(r.channel);
      if (!e) {
        e = this.createRow(r);
        this.rowEls.set(r.channel, e);
      }
      const pinned = this.pinned.has(r.channel);
      e.pin.textContent = pinned ? "★" : "☆";
      e.pin.classList.toggle("on", pinned);
      e.pin.setAttribute("aria-pressed", String(pinned));
      e.tr.className = `${pinned ? "pinned" : ""}${nearLimit(r, this.limits.get(r.channel)) ? " near" : ""}`;
      e.limit.textContent = describeLimit(this.limits.get(r.channel), unit);
      e.instrument.textContent = r.instrument;
      e.setpoint.textContent = fmt(r.setpoint, unit);
      e.held.textContent = fmt(r.held, unit);
      e.readback.textContent = fmt(r.readback, unit);
      const settable = r.setpoint !== null && r.setpoint !== undefined;
      e.input.disabled = !settable;
      e.input.placeholder = unit;
      e.button.disabled = !settable;
      const note = this.settling.has(r.channel) ? "settling" : (this.notes.get(r.channel) ?? "");
      e.badge.hidden = !note;
      e.badge.className = `badge${this.settling.has(r.channel) ? " settling" : note ? " limit" : ""}`;
      e.badge.textContent = note;
      return e.tr;
    });
    const current = [...this.tbody.children];
    if (current.length !== trs.length || current.some((tr, i) => tr !== trs[i])) this.tbody.replaceChildren(...trs);
    const held = this.rows.filter((r) => r.held !== null && r.held !== undefined);
    const st = this.state;
    this.foot.replaceChildren(
      ...(st ? [h("span", { className: "hint stand-state", attrs: { "data-stand-state": "" }, title: `stand state v${st.version}, set by ${st.set_by}: ${st.reason}`, text: `stand state v${st.version} · ${st.set_by} · ${st.reason}` })] : []),
      h("span", { className: "held-summary", text: held.length ? `held: ${held.map((r) => `${r.channel} = ${Number(r.held!.toPrecision(5))} ${unitOf(r.quantity)}`).join(" · ")}` : "held: nothing (the stand is where the last sweep left it)" }),
      h("span", { className: "hint", text: `${shown.length} of ${this.rows.length} channels` }),
    );
    this.renderOffer();
    this.renderPending();
    this.renderLimitChannels();
  }

  private renderPending(): void {
    if (!this.pending.length) return this.pendingBox.replaceChildren();
    const unit = (c: string) => unitOf(this.rows.find((r) => r.channel === c)?.quantity ?? "voltage");
    const confirm = h("button", { type: "button", text: "re-apply", title: "Set these levels on the stand now and hold them", attrs: { "data-confirm": "" } });
    confirm.addEventListener("click", () => void this.decidePending(true));
    const discard = h("button", { type: "button", text: "discard", title: "Hold nothing; the stand stays where it is", attrs: { "data-discard": "" } });
    discard.addEventListener("click", () => void this.decidePending(false));
    this.pendingBox.replaceChildren(
      h("span", { text: `held before the server restarted, not re-applied: ${this.pending.map((l) => `${l.channel} = ${Number(l.value.toPrecision(5))} ${unit(l.channel)}`).join(" · ")}` }),
      confirm,
      discard,
    );
  }

  /** The channels a limit may name: every row the stand sets; the choice survives a poll. */
  private renderLimitChannels(): void {
    const names = this.rows.filter((r) => r.setpoint !== null && r.setpoint !== undefined).map((r) => r.channel);
    const have = [...this.limitChannel.options].map((o) => o.value);
    if (have.length === names.length && have.every((v, i) => v === names[i])) return;
    const chosen = this.limitChannel.value;
    this.limitChannel.replaceChildren(...names.map((n) => h("option", { value: n, text: n })));
    if (names.includes(chosen)) this.limitChannel.value = chosen;
    this.fillLimit();
  }

  private createRow(r: ChannelLevel): RowEls {
    const pin = h("button", { type: "button", className: "pin", text: "☆", title: "pin" });
    pin.addEventListener("click", () => {
      if (this.pinned.has(r.channel)) this.pinned.delete(r.channel);
      else this.pinned.add(r.channel);
      this.savePins();
      this.render();
    });
    const input = h("input", { type: "number", name: `set_${r.channel}`, step: "any", attrs: { "aria-label": `Set ${r.channel}` } });
    const button = h("button", { type: "button", text: "set" });
    const badge = h("span", { className: "badge", hidden: true });
    const apply = () => {
      const why = checkSet(input.value, this.limits.get(r.channel), unitOf(r.quantity));
      if (why) {
        this.notes.set(r.channel, why);
        this.render();
        return;
      }
      this.notes.delete(r.channel);
      void this.set([{ channel: r.channel, value: Number(input.value) }]);
    };
    button.addEventListener("click", apply);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        apply();
      }
    });
    input.addEventListener("input", () => {
      if (this.notes.delete(r.channel)) this.render();
    });
    const instrument = h("td");
    const setpoint = h("td", { className: "num setpoint" });
    const held = h("td", { className: "num held" });
    const readback = h("td", { className: "num readback" });
    const limit = h("td", { className: "num limit" });
    const tr = h(
      "tr",
      { attrs: { "data-channel": r.channel } },
      h("td", {}, pin),
      h("td", { text: r.channel }, h("span", { className: "typeTag", text: ` ${r.quantity}` })),
      instrument,
      setpoint,
      held,
      readback,
      limit,
      h("td", {}, input, button, badge),
    );
    return { tr, pin, instrument, setpoint, held, readback, limit, input, button, badge };
  }
}

interface RowEls {
  tr: HTMLTableRowElement;
  pin: HTMLButtonElement;
  instrument: HTMLTableCellElement;
  setpoint: HTMLTableCellElement;
  held: HTMLTableCellElement;
  readback: HTMLTableCellElement;
  limit: HTMLTableCellElement;
  input: HTMLInputElement;
  button: HTMLButtonElement;
  badge: HTMLSpanElement;
}

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.status} ${e.detail}`;
  return e instanceof Error ? e.message : String(e);
}
