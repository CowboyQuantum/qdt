// The Tune-up widget (ADR 0048–0050, 0058): the calibration nodes the stand can run (GET /nodes), the
// run options, start and stop, and the DAG state rendered from the server's `TuneUp` (FINISH_LINE: the
// lifecycle is a schema object, rendered, never stored in the UI). Each node's sweep runs through the
// server's RunManager and shows on the stream like any run.
import { ApiError } from "../api/client";
import type { CalibrationNode, TuneUp } from "../schema/api";
import { h } from "../workspace/dom";
import type { Widget, WidgetContext } from "../workspace/widget";

const short = (id: string) => id.slice(0, 8);
const TERMINAL = new Set(["completed", "stopped", "failed"]);

/** One line per node of a tune-up: its status so far, its message, and an accepted node's outputs
 * (ADR 0050). Pure, so the DAG state the finish line asks for is testable without a DOM. */
export function tuneupLines(t: TuneUp): { node: string; status: string; message: string; outputs: string }[] {
  const byNode = new Map((t.outcomes ?? []).map((o) => [o.node_id, o]));
  return t.nodes.map((n) => {
    const o = byNode.get(n.node_id);
    const status = o ? o.status : t.current_node === n.node_id ? "running" : t.state === "running" || t.state === "queued" ? "waiting" : "not run";
    const outputs = o && o.status === "accepted" ? Object.entries(o.outputs ?? {}).map(([k, v]) => `${k}=${Number(v).toPrecision(4)}`).join(" ") : "";
    return { node: n.node_id, status, message: o?.message ?? "", outputs };
  });
}

export const tuneupWidget: Widget = {
  id: "tuneup",
  label: "Tune-up",
  sub: "calibration nodes, run in order on the server; the DAG state",
  single: true,
  mount(body, head, ctx) {
    const w = new TuneUpWidget(body, head, ctx);
    return () => w.unmount();
  },
};

class TuneUpWidget {
  private nodes: CalibrationNode[] = [];
  private tuneup: TuneUp | null = null;
  private readonly nodeList: HTMLDivElement;
  private readonly options: HTMLInputElement;
  private readonly state: HTMLDivElement;
  private readonly offs: (() => void)[] = [];
  private alive = true;

  constructor(
    private readonly body: HTMLElement,
    private readonly head: HTMLElement,
    private readonly ctx: WidgetContext,
  ) {
    this.nodeList = h("div", { className: "nodes" });
    this.options = h("input", { name: "options", value: '{"seed": 1, "noise": true}', attrs: { "aria-label": "Run options" } });
    this.state = h("div", { className: "tuneup-state" });
    const start = h("button", { type: "button", text: "run tune-up", attrs: { "data-start": "" } });
    start.addEventListener("click", () => void this.start());
    const stop = h("button", { type: "button", text: "stop", attrs: { "data-stop": "" } });
    stop.addEventListener("click", () => void this.stop());
    head.append(start, stop);
    body.append(
      h(
        "div",
        { className: "form-widget tuneup" },
        h("div", { className: "hint", text: "the server orders the nodes by their dependencies and stops at the first that is not accepted (ADR 0048–0050); each node's sweep is a run on the stream" }),
        this.nodeList,
        h("label", {}, "options ", this.options),
        this.state,
      ),
    );
    void this.ctx.api
      .nodes()
      .then((nodes) => {
        this.nodes = nodes;
        this.renderNodes();
      })
      .catch((e: unknown) => this.say(`server: ${describe(e)}`, true));
  }

  unmount(): void {
    this.alive = false;
    for (const off of this.offs.splice(0)) off();
    this.body.replaceChildren();
    this.head.replaceChildren();
  }

  private say(text: string, error = false): void {
    this.ctx.bus.emit("say", { text, error });
  }

  private renderNodes(): void {
    this.nodeList.replaceChildren(
      ...this.nodes.map((n) =>
        h(
          "label",
          { className: "node" },
          h("input", { type: "checkbox", name: "node", value: n.node_id, checked: true }),
          h("span", { className: "node-id", text: n.node_id }),
          h("span", { className: "node-deps", text: n.depends_on?.length ? ` ← ${n.depends_on.join(", ")}` : "" }),
          h("span", { className: "hint", text: ` ${n.description ?? ""}` }),
        ),
      ),
    );
  }

  private selectedNodeIds(): string[] {
    return [...this.nodeList.querySelectorAll<HTMLInputElement>("input[name=node]:checked")].map((i) => i.value);
  }

  private async start(): Promise<void> {
    const node_ids = this.selectedNodeIds();
    if (!node_ids.length) return this.say("pick at least one node", true);
    if (this.tuneup && !TERMINAL.has(this.tuneup.state)) return this.say(`tune-up ${short(this.tuneup.tuneup_id)} is still ${this.tuneup.state}`, true);
    try {
      const options = JSON.parse(this.options.value || "{}") as Record<string, string | number | boolean>;
      this.tuneup = await this.ctx.api.startTuneUp({ node_ids: node_ids as [string, ...string[]], options });
      this.render();
      this.say(`tune-up ${short(this.tuneup.tuneup_id)} queued`);
      void this.follow(this.tuneup.tuneup_id);
    } catch (e) {
      this.say(describe(e), true);
    }
  }

  private async stop(): Promise<void> {
    if (!this.tuneup || TERMINAL.has(this.tuneup.state)) return this.say("no tune-up running", true);
    try {
      this.tuneup = await this.ctx.api.stopTuneUp(this.tuneup.tuneup_id);
      this.render();
      this.say(`tune-up ${short(this.tuneup.tuneup_id)} stopping after the current node`);
    } catch (e) {
      this.say(describe(e), true);
    }
  }

  private async follow(tuneupId: string): Promise<void> {
    while (this.alive) {
      await new Promise((r) => setTimeout(r, 1000));
      let t: TuneUp;
      try {
        t = await this.ctx.api.tuneup(tuneupId);
      } catch (e) {
        this.say(describe(e), true);
        return;
      }
      if (!this.alive || this.tuneup?.tuneup_id !== tuneupId) return;
      this.tuneup = t;
      this.render();
      if (TERMINAL.has(t.state)) {
        this.say(`tune-up ${short(tuneupId)} ${t.state}${t.message ? `: ${t.message}` : ""}`, t.state === "failed");
        this.ctx.bus.emit("records:changed", {});
        return;
      }
    }
  }

  private render(): void {
    const t = this.tuneup;
    if (!t) return this.state.replaceChildren();
    this.state.replaceChildren(
      h("div", { className: "tuneup-head", text: `${short(t.tuneup_id)} ${t.name} · ${t.state}${t.message ? ` · ${t.message}` : ""}` }),
      h(
        "ol",
        { className: "dag" },
        ...tuneupLines(t).map((l) =>
          h("li", { className: `node-${l.status}` }, h("b", { text: l.node }), ` · ${l.status}`, l.message ? ` · ${l.message}` : "", l.outputs ? h("div", { className: "outputs", text: l.outputs }) : ""),
        ),
      ),
    );
  }
}

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.status} ${e.detail}`;
  return e instanceof Error ? e.message : String(e);
}
