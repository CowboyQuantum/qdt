// Wire decoding (ADR 0010): text messages are StreamTextMessage JSON; each chunk is one Arrow IPC
// message — a one-row batch of list<dtype> columns with the DatasetChunk envelope in schema metadata.
import { tableFromIPC } from "apache-arrow";
import type { DataVariable, Dataset, DatasetChunk, StreamTextMessage } from "../schema/data";

export const CHUNK_METADATA_KEY = "qdt.chunk";

export type Dtype = DataVariable["dtype"];

export type TypedArray =
  | Float32Array
  | Float64Array
  | Int16Array
  | Int32Array
  | BigInt64Array
  | Uint16Array
  | Uint32Array;

export const ARRAY_TYPES: Record<Dtype, { new (n: number): TypedArray; name: string }> = {
  float32: Float32Array,
  float64: Float64Array,
  int16: Int16Array,
  int32: Int32Array,
  int64: BigInt64Array,
  uint16: Uint16Array,
  uint32: Uint32Array,
};

/** One chunk: envelope plus flattened row-major arrays with their shapes. */
export interface Frame {
  chunk: DatasetChunk;
  arrays: Record<string, { values: TypedArray; shape: number[] }>;
}

export function decodeText(text: string): StreamTextMessage {
  const msg = JSON.parse(text) as StreamTextMessage;
  if (msg.type !== "dataset" && msg.type !== "annotation") {
    throw new Error(`unknown text message type ${(msg as { type: unknown }).type}`);
  }
  return msg;
}

/** Port of `Dataset.payload_shapes`: validate a chunk against its definition; shape per payload name. */
export function payloadShapes(dataset: Dataset, chunk: DatasetChunk): Map<string, number[]> {
  if (chunk.dataset_id !== dataset.dataset_id) {
    throw new Error(`chunk belongs to ${chunk.dataset_id}, not ${dataset.dataset_id}`);
  }
  const sizes = new Map(dataset.dims.map((d) => [d.name, d.size]));
  const extent = new Map<string, number>();
  for (const s of chunk.region) {
    if (!sizes.has(s.dim)) throw new Error(`region uses unknown dimension ${s.dim}`);
    const size = sizes.get(s.dim);
    if (size != null && s.stop > size) throw new Error(`region ${s.dim} exceeds size ${size}`);
    extent.set(s.dim, s.stop - s.start);
  }
  const shapes = new Map<string, number[]>();
  for (const name of chunk.variables) {
    const v = dataset.data_vars.find((x) => x.name === name);
    if (!v) throw new Error(`chunk carries unknown variable ${name}`);
    if (v.dims.length !== extent.size || !v.dims.every((d) => extent.has(d))) {
      throw new Error(`variable ${name} spans ${v.dims.join(",")}; region spans ${[...extent.keys()]}`);
    }
    shapes.set(name, v.dims.map((d) => extent.get(d)!));
  }
  const streamed = dataset.coords.filter((c) => c.kind === "streamed" && extent.has(c.dim));
  const explicit = new Set(chunk.explicit_coords);
  if (streamed.length !== explicit.size || !streamed.every((c) => explicit.has(c.name))) {
    throw new Error("chunk must carry exactly the streamed coordinates of its region");
  }
  for (const c of streamed) shapes.set(c.name, [extent.get(c.dim)!]);
  return shapes;
}

export function readEnvelope(bytes: Uint8Array): DatasetChunk {
  const json = tableFromIPC(bytes).schema.metadata.get(CHUNK_METADATA_KEY);
  if (json === undefined) throw new Error("binary message has no qdt.chunk envelope");
  return JSON.parse(json) as DatasetChunk;
}

export function dtypeOf(dataset: Dataset, name: string): Dtype {
  const v = dataset.data_vars.find((x) => x.name === name);
  if (v) return v.dtype;
  const c = dataset.coords.find((x) => x.name === name);
  if (c && c.kind === "streamed") return c.dtype;
  throw new Error(`no payload array named ${name}`);
}

export function decodeChunk(bytes: Uint8Array, dataset: Dataset): Frame {
  const table = tableFromIPC(bytes);
  const json = table.schema.metadata.get(CHUNK_METADATA_KEY);
  if (json === undefined) throw new Error("binary message has no qdt.chunk envelope");
  const chunk = JSON.parse(json) as DatasetChunk;
  const shapes = payloadShapes(dataset, chunk);
  const names = table.schema.fields.map((f) => f.name);
  if (names.length !== shapes.size || !names.every((n) => shapes.has(n))) {
    throw new Error(`payload names ${names} != expected ${[...shapes.keys()]}`);
  }
  const arrays: Frame["arrays"] = {};
  for (const name of names) {
    const shape = shapes.get(name)!;
    const values = table.getChild(name)!.get(0)!.toArray() as TypedArray;
    const expected = ARRAY_TYPES[dtypeOf(dataset, name)];
    if (!(values instanceof expected)) {
      throw new Error(`${name} has ${values.constructor.name}, expected ${expected.name}`);
    }
    if (values.length !== shape.reduce((a, b) => a * b, 1)) {
      throw new Error(`${name} has ${values.length} values for shape ${shape}`);
    }
    arrays[name] = { values, shape };
  }
  return { chunk, arrays };
}
