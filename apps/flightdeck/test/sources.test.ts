// Source equivalence (FINISH_LINE "multiple simultaneous sources"; ADR 0005): the same Dataset through
// replay, through a WebSocket, and through the real Python stream server assembles identically — and
// identically to the Python reference consumer.
import { type ChildProcess, spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { createServer } from "node:net";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { WebSocketServer } from "ws";
import { ReplaySource } from "../src/sources/replay";
import { consume, type Source } from "../src/sources/source";
import { WebSocketSource } from "../src/sources/websocket";
import { parseRecording } from "../src/stream/recording";
import type { DatasetStore } from "../src/stream/store";
import { expectMatchesOracle, FIXTURE_NAMES, FIXTURES, oracle, recording, REPO } from "./helpers";

/** Consume until every announced Dataset is complete (live servers keep the socket open). */
async function untilComplete(source: Source): Promise<Map<string, DatasetStore>> {
  const abort = new AbortController();
  const stores: DatasetStore[] = [];
  const check = () => stores.length && stores.every((s) => s.complete) && abort.abort();
  return consume(
    source,
    (s) => {
      stores.push(s);
      s.onUpdate(check);
    },
    abort.signal,
  );
}

const freePort = () =>
  new Promise<number>((resolve) => {
    const srv = createServer().listen(0, "127.0.0.1", () => {
      const { port } = srv.address() as { port: number };
      srv.close(() => resolve(port));
    });
  });

describe.each(FIXTURE_NAMES)("source equivalence on %s", (name) => {
  it("replay and a WebSocket carrying the same messages both match the Python oracle", async () => {
    const wss = new WebSocketServer({ host: "127.0.0.1", port: 0 });
    await new Promise((r) => wss.once("listening", r));
    wss.on("connection", (sock) => {
      for (const m of parseRecording(recording(name))) sock.send(m, { binary: typeof m !== "string" });
    });
    const url = `ws://127.0.0.1:${(wss.address() as { port: number }).port}`;
    try {
      const replay = await consume(new ReplaySource(recording(name), name));
      const live = await untilComplete(new WebSocketSource(url));
      const o = oracle(name);
      expectMatchesOracle(replay.get(o.dataset_id)!, o);
      expectMatchesOracle(live.get(o.dataset_id)!, o);
    } finally {
      for (const c of wss.clients) c.terminate();
      await new Promise((r) => wss.close(r));
    }
  });
});

// The cross-language end-to-end path: qdt_lab.stream's Python server -> WebSocket -> TS decoder.
const python = [`${REPO}.venv/Scripts/python.exe`, `${REPO}.venv/bin/python`].find(existsSync);

describe("Python stream server -> Flight Deck", () => {
  let server: ChildProcess | undefined;
  let url = "";

  beforeAll(async () => {
    if (!python) throw new Error("no repo .venv — run `uv sync --all-packages` first");
    const port = await freePort();
    url = `ws://127.0.0.1:${port}`;
    const fixture = `${FIXTURES}synthetic_map_64.qdtrec`;
    server = spawn(python, ["-m", "qdt_lab.stream", "--replay", fixture, "--speed", "0", "--port", `${port}`]);
    await new Promise<void>((resolve, reject) => {
      server!.stdout!.on("data", (d: Buffer) => d.toString().includes("serving") && resolve());
      server!.on("exit", (code) => reject(new Error(`stream server exited with ${code}`)));
    });
  });

  afterAll(() => {
    server?.kill();
  });

  it("delivers the recording identically to the Python oracle", async () => {
    const stores = await untilComplete(new WebSocketSource(url));
    const o = oracle("synthetic_map_64");
    expectMatchesOracle(stores.get(o.dataset_id)!, o);
  });
});

describe("paced replay", () => {
  it("follows recorded timing at speed 1 and is faster unpaced", async () => {
    // the records fixture was recorded at 50 records/s: 8 records span ~140 ms
    const t0 = performance.now();
    await consume(new ReplaySource(recording("synthetic_records_8"), "r", 1));
    const paced = performance.now() - t0;
    const t1 = performance.now();
    await consume(new ReplaySource(recording("synthetic_records_8"), "r"));
    const unpaced = performance.now() - t1;
    expect(paced).toBeGreaterThan(100);
    expect(unpaced).toBeLessThan(paced);
  });
});
