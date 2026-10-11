// WebSocket source: the stream server of qdt_lab.stream (ADR 0008, 0010). Every producer — synthetic,
// replay, simulated device, instrument — reaches Flight Deck through this one transport (rule 8).
import type { WireMessage } from "../stream/recording";
import type { Source } from "./source";

export class WebSocketSource implements Source {
  readonly label: string;

  constructor(private readonly url: string) {
    this.label = `websocket: ${url}`;
  }

  async *messages(signal?: AbortSignal): AsyncIterable<WireMessage> {
    const ws = new WebSocket(this.url);
    ws.binaryType = "arraybuffer";
    const queue: WireMessage[] = [];
    let wake: (() => void) | null = null;
    let closed = false;
    let error: Error | null = null;
    const notify = () => (wake?.(), (wake = null));
    ws.onmessage = (e: MessageEvent) => {
      queue.push(typeof e.data === "string" ? e.data : new Uint8Array(e.data as ArrayBuffer));
      notify();
    };
    ws.onerror = () => ((error = new Error(`websocket error on ${this.url}`)), notify());
    ws.onclose = () => ((closed = true), notify());
    signal?.addEventListener("abort", () => ws.close(), { once: true });
    try {
      while (true) {
        while (queue.length) yield queue.shift()!;
        if (error) throw error;
        if (closed || signal?.aborted) return;
        await new Promise<void>((r) => (wake = r));
      }
    } finally {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close();
    }
  }
}
