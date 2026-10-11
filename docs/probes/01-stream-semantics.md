# Probe 01 — Stream semantics (OPX + scope)

**Step:** 1 · **Gates:** the `Dataset` contract *freeze* (not the draft) · **Effort:** one afternoon
**Deliverable:** this file's "Findings" section filled in, plus the raw timing CSVs under `bench/fixtures/probe01/`.

## What this is
A one-off measurement of *how* results come out of the two live sources we will have, so that
`DatasetChunk`'s addressing model and `SweepDefinition`'s backend-payload slot are designed against
observed behavior. It is **not** a driver, not a bench test, and writes no production code.

## What you need
- The OPX, reachable from a laptop with `qm-qua` installed. **No device, no fridge, and no saved output
  file.** The OPX does not produce output files; results are fetched over its Python API from a job's
  result handles. Nothing needs to be connected to the analog inputs — a `measure` on an open input returns
  noise, which is fine, and the cleanest variant skips the ADC entirely by streaming computed values.
- The Keysight scope, reachable over VISA (USB or LAN).
- ~2 hours of OPX time, ~30 minutes of scope time.

## Procedure — OPX
Write one short QUA program and one Python timing script. Record, for each variant:

1. **Granularity.** Three stream-processing variants of the same 2D loop (outer N, inner M):
   - `save_all` per point;
   - `buffer(M).save_all` (one line per result);
   - `buffer(N, M).save` (one frame).
   For each: how many points are visible in the result handle after each poll, and does a partial buffer
   ever become visible before the buffer completes?
2. **Cadence.** Poll the result handle in a tight loop (`wait_for_values(k)` / `fetch` of new slices) and log
   wall-clock time and point count per poll. Report sustained points/s and the median/95th-percentile
   inter-arrival time. This is the probe's one quantitative output and feeds Analysis 0001 §5.
3. **Addressing.** Confirm results are positional (loop-order index) with no in-band coordinates. Note what a
   timestamp stream gives you and at what cost.
4. **Dtype and shape.** What Python dtype and array shape each variant yields on fetch (fixed-point → float64?).
5. **QUA constraints.** Try to vary, without recompiling: a sweep endpoint, a step count, an averaging count.
   Record which are possible via IO variables / input streams and which force a recompile. This decides what
   the generic outer loop may change at runtime versus what the payload slot must carry.

## Procedure — scope
1. Trigger a capture, query the waveform (`:WAV:DATA?` with `:WAV:PRE?` for the preamble), and log the
   record length, transfer time, and the derived time axis.
2. Repeat at the largest record length you expect to use and at a few Hz; note the sustained frame rate.
3. Note that this source is *pull*, whole-record, with an explicit coordinate axis — the opposite of the OPX on
   all three counts.

## Findings (fill in)
| Item | OPX | Scope |
|---|---|---|
| Delivery granularity | | |
| Partial fetch mid-acquisition | | |
| Sustained points/s (median / p95 inter-arrival) | | |
| Coordinate addressing | positional (expected) | explicit time axis (expected) |
| In-band metadata | | |
| Push or pull | pull (expected) | pull (expected) |
| Dtype / shape on fetch | | |
| Runtime-variable without recompile | | n/a |

## What the findings decide
- `DatasetChunk` must carry either explicit coordinates or an *index range + reference to the definition*; the probe says which the OPX path needs and whether partial lines occur.
- The stream server's poller cadence and chunking policy (per line vs per frame).
- The shape of `SweepDefinition.backend_payload` for QUA.
- Whether the synthetic source's emulated envelope (Analysis 0001 targets) is above measured reality — it should be, by ~10×.
