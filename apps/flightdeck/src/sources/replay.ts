// Replay source over a `.qdtrec` recording, optionally paced by the recorded `produced_at` times.
import { readEnvelope } from "../stream/decode";
import { parseRecording, type WireMessage } from "../stream/recording";
import type { Source } from "./source";

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => (clearTimeout(t), resolve()), { once: true });
  });

export class ReplaySource implements Source {
  readonly label: string;
  private readonly recording: WireMessage[];

  /** `speed` scales recorded timing (1 = as recorded); null replays as fast as possible. */
  constructor(
    bytes: Uint8Array,
    name = "recording",
    private readonly speed: number | null = null,
  ) {
    this.recording = parseRecording(bytes);
    this.label = `replay: ${name}`;
  }

  async *messages(signal?: AbortSignal): AsyncIterable<WireMessage> {
    let t0Wall: number | null = null;
    let t0Rec = 0;
    for (const m of this.recording) {
      if (signal?.aborted) return;
      if (this.speed !== null && typeof m !== "string") {
        const stamp = Date.parse(readEnvelope(m).produced_at);
        if (t0Wall === null) [t0Wall, t0Rec] = [performance.now(), stamp];
        const delay = t0Wall + (stamp - t0Rec) / this.speed - performance.now();
        if (delay > 0) await sleep(delay, signal);
      }
      yield m;
    }
  }
}
