// The workspace event bus (ADR 0054): widgets share no state directly; what one widget needs another
// to know travels here as a typed event, and the data itself lives in the stream stores or on the server.
import type { BindingRow, OpRow } from "../control/sequence";
import type { Run, StandConfig } from "../schema/api";
import type { DatasetStore } from "../stream/store";

/** Every event the shell and its widgets exchange. Add an event here; nowhere else. */
export interface Events {
  /** A Dataset was announced on the source; its store fills as chunks arrive. */
  "stream:dataset": { store: DatasetStore };
  /** The source changed (a replay was loaded, a socket reconnected). */
  "stream:source": { label: string };
  /** Where the stream stands, as the plot sees it: live (chunks arriving), complete, or idle. */
  "stream:state": { state: "idle" | "live" | "complete"; progress: number | null; summary: string };
  /** The stand the server runs (GET /stand), once a widget has fetched it. */
  stand: { stand: StandConfig };
  /** The user pressed Run in the strip: the Sweep widget, which holds the compiled plan, runs it. */
  "run:request": Record<string, never>;
  /** The user pressed abort in the strip. */
  "run:abort": Record<string, never>;
  /** What the next Run would do, one line, from the widget that holds the sweep form. */
  "run:next": { summary: string };
  /** The one run the strip follows: queued → running → completed | aborted | failed; null when none. */
  "run:state": { run: Run | null };
  /** The Sweep widget compiled: the plan's identity for the strip (ADR 0056). */
  "plan:compiled": { planId: string; summary: string };
  /** An editor changed after the last compile: the plan shown is stale (ADR 0056). */
  "plan:changed": Record<string, never>;
  /** The Sweep widget's axes, inner channel and sensor, for the Pulse widget's template. */
  "sweep:axes": { kind: "stage" | "dc" | "capture"; axes: string[]; inner: string; sensor: string };
  /** The Pulse widget's sequence as edited, for the Sweep widget's stage sweep. */
  "pulse:sequence": { rows: OpRow[]; bindings: BindingRow[]; errors: string[] };
  /** The Virtual gates widget's coupling matrix: axis channel → companion → V/V (ADR 0049). */
  "gates:couplings": { matrix: Record<string, Record<string, number>> };
  /** The held operating point changed (set or released) from the Levels widget. */
  "levels:changed": Record<string, never>;
  /** History's "analyse": the Analysis widget selects this record. */
  "analysis:record": { recordId: string; name: string };
  /** A run reached a terminal state: a record may have landed. */
  "records:changed": Record<string, never>;
  /** A point on a map was clicked: coordinate names and values (rule 8: never a channel). */
  "map:click": { point: { name: string; unit: string; value: number }[] };
  /** Open a stored record in a plot pane: the pane pins itself to the Dataset that is the record, by its registry
   * ref (a replay) or by its id (the record's plan id, when the run that made it is still on the stream). */
  "plot:open": { recordId: string; planId: string; paneId: string };
  /** What a plot pane shows now (null when it closes), for "shown in" lists. */
  "plot:view": { paneId: string; datasetId: string | null; registryRef: string | null; name: string };
  /** The layout was re-rendered: panes added, closed or re-ordered. */
  "layout:changed": Record<string, never>;
  /** Something to tell the user: a status line or an error. */
  say: { text: string; error: boolean };
}

export type EventName = keyof Events;
export type Listener<K extends EventName> = (payload: Events[K]) => void;

export class Bus {
  private readonly listeners = new Map<EventName, Set<Listener<EventName>>>();

  on<K extends EventName>(name: K, listener: Listener<K>): () => void {
    let set = this.listeners.get(name);
    if (!set) this.listeners.set(name, (set = new Set()));
    set.add(listener as Listener<EventName>);
    return () => this.off(name, listener);
  }

  off<K extends EventName>(name: K, listener: Listener<K>): void {
    const set = this.listeners.get(name);
    set?.delete(listener as Listener<EventName>);
    if (set && set.size === 0) this.listeners.delete(name);
  }

  emit<K extends EventName>(name: K, payload: Events[K]): void {
    for (const l of [...(this.listeners.get(name) ?? [])]) (l as Listener<K>)(payload);
  }

  /** Listeners registered for `name`, or for every event when omitted (tests: nothing leaks). */
  count(name?: EventName): number {
    if (name) return this.listeners.get(name)?.size ?? 0;
    let n = 0;
    for (const s of this.listeners.values()) n += s.size;
    return n;
  }
}

/** A bus view for one mounted widget: whatever it subscribes to is removed when it unmounts, even if
 * the widget forgot. Emits go straight through. */
export class ScopedBus {
  private readonly offs: (() => void)[] = [];
  constructor(private readonly bus: Bus) {}

  on<K extends EventName>(name: K, listener: Listener<K>): () => void {
    const off = this.bus.on(name, listener);
    this.offs.push(off);
    return off;
  }

  emit<K extends EventName>(name: K, payload: Events[K]): void {
    this.bus.emit(name, payload);
  }

  dispose(): void {
    for (const off of this.offs.splice(0)) off();
  }
}
