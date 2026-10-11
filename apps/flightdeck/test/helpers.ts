// Shared test helpers: committed replay fixtures and their cross-language content oracles
// (written by scripts/make_stream_fixtures.py from the reference Python consumer).
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect } from "vitest";
import type { TypedArray } from "../src/stream/decode";
import type { DatasetStore } from "../src/stream/store";

export const REPO = fileURLToPath(new URL("../../../", import.meta.url));
export const FIXTURES = `${REPO}packages/qdt-lab/tests/fixtures/stream/`;
export const FIXTURE_NAMES = ["synthetic_map_64", "synthetic_records_8"] as const;

export interface Oracle {
  dataset_id: string;
  n_chunks: number;
  annotation_ids: string[];
  arrays: Record<string, { shape: number[]; dtype: string; sha256: string }>;
}

export const recording = (name: string) => new Uint8Array(readFileSync(`${FIXTURES}${name}.qdtrec`));
export const oracle = (name: string): Oracle =>
  JSON.parse(readFileSync(`${FIXTURES}${name}.expected.json`, "utf8")) as Oracle;

export function sha256(a: TypedArray): string {
  return createHash("sha256").update(new Uint8Array(a.buffer, a.byteOffset, a.byteLength)).digest("hex");
}

/** Assert a store's contents equal the Python oracle bit-for-bit. */
export function expectMatchesOracle(store: DatasetStore, o: Oracle): void {
  expect(store.dataset.dataset_id).toBe(o.dataset_id);
  expect(store.lastSeq + 1).toBe(o.n_chunks);
  expect(store.complete).toBe(true);
  expect([...store.annotations.keys()]).toEqual(o.annotation_ids);
  for (const [name, spec] of Object.entries(o.arrays)) {
    const a = store.get(name);
    expect(a.shape, name).toEqual(spec.shape);
    expect(sha256(a.values), name).toBe(spec.sha256);
  }
}
