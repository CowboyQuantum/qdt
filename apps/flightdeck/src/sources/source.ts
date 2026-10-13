// The `Source` abstraction: every source yields raw wire messages (ADR 0010); one shared decoder turns
// them into events. Sources differ only in transport, so source equivalence holds by construction and
// is still tested (test/sources.test.ts).
import type { Annotation, Dataset } from "../schema/data";
import { decodeChunk, decodeText, type Frame, readEnvelope } from "../stream/decode";
import type { WireMessage } from "../stream/recording";
import { DatasetStore } from "../stream/store";

export type StreamEvent =
  | { kind: "dataset"; dataset: Dataset }
  | { kind: "annotation"; annotation: Annotation }
  | { kind: "frame"; frame: Frame };

export interface Source {
  /** Human-readable description of the transport, e.g. "replay: map.qdtrec". Never an instrument. */
  readonly label: string;
  /** Raw wire messages in order; ends when the transport closes. */
  messages(signal?: AbortSignal): AsyncIterable<WireMessage>;
}

export class Decoder {
  private readonly datasets = new Map<string, Dataset>();

  decode(message: WireMessage): StreamEvent {
    if (typeof message === "string") {
      const msg = decodeText(message);
      if (msg.type === "dataset") {
        this.datasets.set(msg.dataset.dataset_id, msg.dataset);
        return { kind: "dataset", dataset: msg.dataset };
      }
      if (!this.datasets.has(msg.annotation.dataset_id)) {
        throw new Error(`annotation for unannounced dataset ${msg.annotation.dataset_id}`);
      }
      return { kind: "annotation", annotation: msg.annotation };
    }
    const id = readEnvelope(message).dataset_id;
    const dataset = this.datasets.get(id);
    if (!dataset) throw new Error(`chunk for unannounced dataset ${id}`);
    return { kind: "frame", frame: decodeChunk(message, dataset) };
  }
}

export async function* events(source: Source, signal?: AbortSignal): AsyncIterable<StreamEvent> {
  const decoder = new Decoder();
  for await (const m of source.messages(signal)) yield decoder.decode(m);
}

/** Drive a source into one DatasetStore per announced Dataset. `onStore` fires when a Dataset appears. */
export async function consume(
  source: Source,
  onStore: (store: DatasetStore) => void = () => {},
  signal?: AbortSignal,
): Promise<Map<string, DatasetStore>> {
  const stores = new Map<string, DatasetStore>();
  for await (const e of events(source, signal)) {
    if (e.kind === "dataset") {
      const store = new DatasetStore(e.dataset);
      stores.set(e.dataset.dataset_id, store);
      onStore(store);
    } else if (e.kind === "annotation") {
      stores.get(e.annotation.dataset_id)!.addAnnotation(e.annotation);
    } else {
      stores.get(e.frame.chunk.dataset_id)!.apply(e.frame);
    }
  }
  return stores;
}
