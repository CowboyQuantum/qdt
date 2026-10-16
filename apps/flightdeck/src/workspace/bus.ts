// The workspace event bus (ADR 0054): widgets share no state directly; what one widget needs another
// to know travels here as a typed event, and the data itself lives in the stream stores or on the server.
import type { StandConfig } from "../schema/api";
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
  /** The user pressed Run in the strip: whoever holds the next sweep runs it. */
  "run:request": Record<string, never>;
  /** What the next Run would do, one line, from the widget that holds the sweep form. */
  "run:next": { summary: string };
  /** A point on a map was clicked: coordinate names and values (rule 8: never a channel). */
  "map:click": { point: { name: string; unit: string; value: number }[] };
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
