// The History widget (ADR 0054, 0055): stored records from GET /records, searchable, with which plot
// pane shows each one, and "open" into an existing plot pane or a new one. Opening asks the server to
// replay the record on the stream (the same path the panel's "show" used) and tells the pane to pin
// itself to the Dataset whose registry ref is the record (ADR 0027: the one permitted read of `.source`).
import { ApiError } from "../api/client";
import type { MeasurementRecord } from "../schema/api";
import { h } from "../workspace/dom";
import type { Widget, WidgetContext } from "../workspace/widget";

const short = (id: string) => id.slice(0, 8);
const when = (iso: string) => iso.slice(0, 19).replace("T", " ");

/** Records matching a free-text query over name, device, campaign, outcome and id; newest first. Pure. */
export function filterRecords(records: readonly MeasurementRecord[], query: string): MeasurementRecord[] {
  const q = query.trim().toLowerCase();
  const hit = (r: MeasurementRecord) => !q || [r.definition_name, r.device_id, r.campaign ?? "", r.outcome, r.record_id, r.started_at].join(" ").toLowerCase().includes(q);
  return [...records].filter(hit).sort((a, b) => (a.started_at < b.started_at ? 1 : a.started_at > b.started_at ? -1 : 0));
}

/** Which plot panes show a record, by label, from what the panes announced. Pure. */
export function shownIn(recordId: string, views: ReadonlyMap<string, string | null>, panes: readonly { id: string; label: string }[]): string[] {
  return panes.filter((p) => views.get(p.id) === recordId).map((p) => p.label);
}

export const historyWidget: Widget = {
  id: "history",
  label: "History",
  sub: "stored records; open one in a plot",
  mount(body, head, ctx) {
    const w = new History(body, head, ctx);
    return () => w.unmount();
  },
};

class History {
  private records: MeasurementRecord[] = [];
  /** paneId → registry ref shown there (null: the pane shows something unstored). */
  private readonly views = new Map<string, string | null>();
  private readonly search: HTMLInputElement;
  private readonly target: HTMLSelectElement;
  private readonly tbody: HTMLTableSectionElement;
  private readonly note: HTMLDivElement;
  private readonly offs: (() => void)[] = [];

  constructor(
    private readonly body: HTMLElement,
    private readonly head: HTMLElement,
    private readonly ctx: WidgetContext,
  ) {
    this.search = h("input", { type: "search", name: "search", placeholder: "search name, device, id…", attrs: { "aria-label": "Search records" } });
    this.target = h("select", { name: "target", attrs: { "aria-label": "Open records in" } });
    this.tbody = h("tbody");
    this.note = h("div", { className: "hint" });
    const refresh = h("button", { type: "button", text: "refresh", attrs: { "data-refresh": "" } });
    refresh.addEventListener("click", () => void this.refresh());
    head.append(refresh);
    body.append(
      h(
        "div",
        { className: "hist" },
        h("div", { className: "bar" }, this.search, h("label", {}, "open in ", this.target)),
        h(
          "div",
          { className: "list" },
          h(
            "table",
            { className: "ht" },
            h("thead", {}, h("tr", {}, ...["when", "name", "device", "outcome", "shown in", "", ""].map((t) => h("th", { text: t })))),
            this.tbody,
          ),
        ),
        this.note,
      ),
    );
    this.search.addEventListener("input", () => this.render());
    this.fillTarget();
    this.offs.push(
      ctx.bus.on("plot:view", ({ paneId, registryRef, datasetId }) => {
        if (datasetId === null) this.views.delete(paneId);
        else this.views.set(paneId, registryRef);
        this.render();
      }),
      ctx.bus.on("layout:changed", () => {
        this.fillTarget();
        this.render();
      }),
      ctx.bus.on("records:changed", () => void this.refresh()),
      // a run's Dataset completing means a record is about to be stored (the run finishes after its last
      // chunk): refresh soon and again a little later, so the row appears without a manual refresh
      ctx.bus.on("stream:dataset", ({ store }) => {
        const off = store.onUpdate((u) => {
          if (!u.final) return;
          off();
          for (const ms of [500, 3000]) setTimeout(() => void this.refresh(), ms);
        });
      }),
    );
    void this.refresh();
  }

  unmount(): void {
    for (const off of this.offs.splice(0)) off();
    this.body.replaceChildren();
    this.head.replaceChildren();
  }

  private fillTarget(): void {
    const had = this.target.value;
    const panes = this.ctx.layout.plotPanes();
    this.target.replaceChildren(new Option("a new pane", "new"), ...panes.map((p) => new Option(p.label, p.id)));
    this.target.value = panes.some((p) => p.id === had) ? had : "new";
  }

  async refresh(): Promise<void> {
    try {
      this.records = await this.ctx.api.records();
      this.note.textContent = "";
    } catch (e) {
      this.note.textContent = `records: ${e instanceof ApiError ? `${e.status} ${e.detail}` : String(e)}`;
    }
    this.render();
  }

  private render(): void {
    const panes = this.ctx.layout.plotPanes();
    const rows = filterRecords(this.records, this.search.value);
    this.tbody.replaceChildren(
      ...rows.map((r) => {
        const open = h("button", { type: "button", text: "open", attrs: { "data-open": r.record_id } });
        open.addEventListener("click", () => void this.open(r));
        const analyse = h("button", { type: "button", text: "analyse", title: "Select this record in the Analysis widget", attrs: { "data-analyse": r.record_id } });
        analyse.addEventListener("click", () => this.ctx.bus.emit("analysis:record", { recordId: r.record_id, name: r.definition_name }));
        const shown = shownIn(r.record_id, this.views, panes);
        return h(
          "tr",
          { className: shown.length ? "open" : "", attrs: { "data-record": r.record_id } },
          h("td", { className: "id", text: when(r.started_at), title: r.record_id }),
          h("td", { text: r.definition_name }),
          h("td", { text: r.device_id }),
          h("td", { text: r.outcome }),
          h("td", { className: "shown", text: shown.join(", ") }),
          h("td", {}, open),
          h("td", {}, analyse),
        );
      }),
    );
    if (!rows.length && !this.note.textContent) this.note.textContent = this.records.length ? "no record matches" : "no records yet";
  }

  /** Open a record where the target select says: a new pane (refused when the centre is full) or an existing one. */
  private async open(r: MeasurementRecord): Promise<void> {
    let paneId = this.target.value;
    if (paneId === "new") {
      const id = this.ctx.layout.addPlotPane();
      if (!id) {
        this.ctx.bus.emit("say", { text: "no room for another plot pane", error: true });
        return;
      }
      paneId = id;
      this.fillTarget();
    }
    const onStream = this.ctx.datasets.all().some((s) => s.dataset.source.registry_ref === r.record_id || s.dataset.dataset_id === r.plan_id);
    this.ctx.bus.emit("plot:open", { recordId: r.record_id, planId: r.plan_id, paneId });
    if (onStream) return;
    try {
      await this.ctx.api.replay({ record_id: r.record_id });
      this.ctx.bus.emit("say", { text: `replaying ${short(r.record_id)} on the stream`, error: false });
    } catch (e) {
      this.ctx.bus.emit("say", { text: e instanceof ApiError ? `${e.status} ${e.detail}` : String(e), error: true });
    }
  }
}
