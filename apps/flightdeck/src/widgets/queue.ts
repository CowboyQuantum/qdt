// The Queue widget (ADR 0075, 0086): the stand server's run queue, as the server holds it. The running
// entry, the waiting ones in the order they will run, and the latest finished; each waiting entry can be
// moved up or down or removed, the running one aborted, and the whole queue paused and resumed. After a
// server restart with entries waiting the queue is paused until a person resumes it, and the widget says
// why. Polled while mounted; nothing about the queue is kept in the browser. The Sweep widget submits
// to it (`POST /queue`); a script or another desk may too.
import { ApiError } from "../api/client";
import type { QueuedRun, StandQueue } from "../schema/api";
import { h } from "../workspace/dom";
import type { Widget, WidgetContext } from "../workspace/widget";

const POLL_MS = 1000;

/** The position a waiting entry moves to for one step up (-1) or down (+1), or null at either end or
 * for an entry that is not waiting. Pure. */
export function stepTarget(queue: Pick<StandQueue, "entries">, queueId: string, delta: -1 | 1): number | null {
  const waiting = (queue.entries ?? []).filter((e) => e.state === "queued");
  const i = waiting.findIndex((e) => e.queue_id === queueId);
  if (i < 0) return null;
  const j = i + delta;
  return j < 0 || j >= waiting.length ? null : j;
}

/** One line on what an entry is and became, for its row. Pure. */
export function describeEntry(e: Pick<QueuedRun, "state" | "position" | "run_id" | "record_id" | "message">): string {
  const id = (x: string | null | undefined) => (x ? x.slice(0, 8) : "");
  switch (e.state) {
    case "queued":
      return e.position === 0 ? "runs next" : `waiting, ${e.position} ahead`;
    case "running":
      return e.run_id ? `running as run ${id(e.run_id)}` : "starting";
    case "done":
      return e.record_id ? `done → record ${id(e.record_id)}` : "done";
    default:
      return `${e.state}${e.record_id ? ` → record ${id(e.record_id)}` : ""}${e.message ? `: ${e.message}` : ""}`;
  }
}

/** A summary for the pane foot: how many wait, and whether the queue runs. Pure. */
export function queueSummary(q: Pick<StandQueue, "entries" | "paused">): string {
  const entries = q.entries ?? [];
  const waiting = entries.filter((e) => e.state === "queued").length;
  const running = entries.some((e) => e.state === "running");
  const what = `${running ? "1 running, " : ""}${waiting} waiting`;
  return q.paused ? `paused · ${what}` : what;
}

export const queueWidget: Widget = {
  id: "queue",
  label: "Queue",
  sub: "the stand's run queue: order, pause, abort",
  single: true,
  mount(body, head, ctx) {
    const w = new QueueWidget(body, head, ctx);
    return () => w.unmount();
  },
};

class QueueWidget {
  private queue: StandQueue | null = null;
  /** What the table shows now, so a poll that finds the same queue leaves the rows (and a click) alone. */
  private shown = "";
  private timer: ReturnType<typeof setInterval> | null = null;
  private busy = false;
  private readonly note: HTMLDivElement;
  private readonly tbody: HTMLTableSectionElement;
  private readonly foot: HTMLDivElement;
  private readonly toggle: HTMLButtonElement;
  private readonly offs: (() => void)[] = [];

  constructor(
    private readonly body: HTMLElement,
    private readonly head: HTMLElement,
    private readonly ctx: WidgetContext,
  ) {
    this.toggle = h("button", { type: "button", text: "pause", attrs: { "data-toggle": "" } });
    this.toggle.addEventListener("click", () => void this.act(() => (this.queue?.paused ? this.ctx.api.resumeQueue() : this.ctx.api.pauseQueue())));
    head.append(this.toggle);
    this.note = h("div", { className: "qnote", attrs: { "data-queue-note": "" } });
    this.tbody = h("tbody");
    this.foot = h("div", { className: "foot hint", attrs: { "data-queue-summary": "" } });
    body.append(
      h(
        "div",
        { className: "queue" },
        this.note,
        h(
          "div",
          { className: "tbl" },
          h("table", { className: "dct" }, h("thead", {}, h("tr", {}, ...["#", "sweep", "state", "by", ""].map((t) => h("th", { text: t })))), this.tbody),
        ),
        this.foot,
      ),
    );
    // a run the Sweep widget starts or follows changes the queue: read it again at once
    this.offs.push(ctx.bus.on("run:state", () => void this.refresh(true)));
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

  private async refresh(quiet = false): Promise<void> {
    try {
      this.queue = await this.ctx.api.queue();
      this.render();
    } catch (e) {
      if (!quiet) this.say(`queue: ${describe(e)}`, true);
    }
  }

  /** One command at a time; the server's answer is the queue as it now is. */
  private async act(command: () => Promise<StandQueue>): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    try {
      this.queue = await command();
      this.render();
    } catch (e) {
      this.say(describe(e), true);
      await this.refresh(true);
    } finally {
      this.busy = false;
    }
  }

  private render(): void {
    const q = this.queue;
    if (!q) return;
    const key = JSON.stringify(q);
    if (key === this.shown) return;
    this.shown = key;
    this.toggle.textContent = q.paused ? "resume" : "pause";
    this.toggle.title = q.paused ? "Run the waiting entries, in order" : "Start no further entry; the one running finishes";
    this.note.textContent = q.paused ? `paused${q.note ? `: ${q.note}` : ""}` : "";
    this.note.hidden = !q.paused;
    const entries = q.entries ?? [];
    this.tbody.replaceChildren(
      ...entries.map((e) => {
        const actions: HTMLElement[] = [];
        if (e.state === "queued") {
          for (const [label, delta, attr] of [["↑", -1, "data-up"], ["↓", 1, "data-down"]] as const) {
            const to = stepTarget(q, e.queue_id, delta);
            const b = h("button", { type: "button", text: label, title: delta < 0 ? "run earlier" : "run later", disabled: to === null, attrs: { [attr]: "" } });
            b.addEventListener("click", () => to !== null && void this.act(() => this.ctx.api.moveEntry(e.queue_id, to)));
            actions.push(b);
          }
          const remove = h("button", { type: "button", text: "remove", title: "It never runs", attrs: { "data-remove": "" } });
          remove.addEventListener("click", () => void this.act(() => this.ctx.api.removeEntry(e.queue_id)));
          actions.push(remove);
        } else if (e.state === "running") {
          const abort = h("button", { type: "button", text: "abort", title: "Stop between frames; what it streamed is recorded as aborted", attrs: { "data-abort": "" } });
          abort.addEventListener("click", () => void this.act(() => this.ctx.api.abortEntry(e.queue_id)));
          actions.push(abort);
        }
        return h(
          "tr",
          { className: e.state, attrs: { "data-queue-id": e.queue_id, "data-state": e.state } },
          h("td", { className: "num", text: e.state === "queued" ? String(e.position) : "" }),
          h("td", { className: "name", text: e.request.definition.name }),
          h("td", { text: describeEntry(e) }),
          h("td", { text: e.submitted_by }),
          h("td", {}, ...actions),
        );
      }),
    );
    this.foot.textContent = entries.length ? queueSummary(q) : "the queue is empty: Run in the strip adds the compiled sweep";
  }
}

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.status} ${e.detail}`;
  return e instanceof Error ? e.message : String(e);
}
