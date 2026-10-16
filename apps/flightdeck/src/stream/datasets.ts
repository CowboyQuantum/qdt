// Every announced Dataset is kept and selectable (CLAUDE.md): one source at a time feeds this
// collection, every pane reads from it, and the newest store is what the user just asked for.
import { consume, type Source } from "../sources/source";
import type { DatasetStore } from "./store";

export class Datasets {
  private readonly stores = new Map<string, DatasetStore>();
  private readonly listeners = new Set<(store: DatasetStore) => void>();
  private readonly sourceListeners = new Set<(label: string) => void>();
  private abort: AbortController | null = null;
  private _label = "";

  /** The transport's label (never an instrument); "" until a source starts. */
  get label(): string {
    return this._label;
  }

  get(id: string): DatasetStore | undefined {
    return this.stores.get(id);
  }

  all(): DatasetStore[] {
    return [...this.stores.values()];
  }

  /** Fires for every store the source announces, newest last. */
  onStore(listener: (store: DatasetStore) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onSource(listener: (label: string) => void): () => void {
    this.sourceListeners.add(listener);
    return () => this.sourceListeners.delete(listener);
  }

  /** Replace the source: the previous one is aborted and its stores dropped. */
  start(source: Source, onError: (e: unknown) => void): void {
    this.abort?.abort();
    this.abort = new AbortController();
    this._label = source.label;
    this.stores.clear();
    for (const l of this.sourceListeners) l(source.label);
    consume(
      source,
      (store) => {
        this.stores.set(store.dataset.dataset_id, store);
        for (const l of this.listeners) l(store);
      },
      this.abort.signal,
    ).catch(onError);
  }
}
