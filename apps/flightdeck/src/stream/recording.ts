// `.qdtrec` recordings (ADR 0010): magic "QDTREC1\n", then records of
// kind (1 byte, "T" text | "B" binary) | length (uint64 LE) | message bytes — exactly the wire sequence.

export type WireMessage = string | Uint8Array;

const MAGIC = new TextEncoder().encode("QDTREC1\n");

export function parseRecording(bytes: Uint8Array): WireMessage[] {
  if (bytes.length < MAGIC.length || !MAGIC.every((b, i) => bytes[i] === b)) {
    throw new Error("not a qdt recording");
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const text = new TextDecoder();
  const out: WireMessage[] = [];
  let pos = MAGIC.length;
  while (pos < bytes.length) {
    if (pos + 9 > bytes.length) throw new Error("recording is truncated");
    const kind = String.fromCharCode(bytes[pos]!);
    const length = Number(view.getBigUint64(pos + 1, true));
    pos += 9;
    if (pos + length > bytes.length) throw new Error("recording is truncated");
    const body = bytes.subarray(pos, pos + length);
    pos += length;
    if (kind === "T") out.push(text.decode(body));
    else if (kind === "B") out.push(body);
    else throw new Error(`unknown record kind ${kind}`);
  }
  return out;
}
