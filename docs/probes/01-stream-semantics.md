# Probe 01 — Stream semantics (OPX + scope)

**Step:** 1 · **Gates:** the `Dataset` contract *freeze* (not the draft) · **Effort:** one afternoon
**Deliverable:** this file's "Findings" section filled in, plus the raw timing CSVs under `bench/fixtures/probe01/`.

## What this is
A one-off measurement of *how* results come out of the two live sources we will have, so that
`DatasetChunk`'s addressing model and `SweepDefinition`'s backend-payload slot are designed against
observed behavior. It is **not** a driver, not a bench test, and writes no production code.

## What you need
- **The OPX1000**, reachable from a laptop, with `qm-qua` matching its QOP version. You also need the
  slot of an LF-FEM. There is **no device, no fridge, and no saved output file**: results are fetched over
  the Python API from a job's result handles. The programs stream computed values (no ADC), and the only
  analog activity is zero-amplitude pulses on one LF-FEM output.
- **The Keysight HD304MSO**, reachable over VISA (LAN preferred). No signal is needed (auto trigger).
- About 30 minutes of OPX time including setup (the full script runs in ~2 min) and ~10 minutes of scope time.
- **Lab guide:** `bench/probes/probe01/LAB_GUIDE.md`. It includes an offline check you can run before the lab day.

## Rate ladder: why 10³–10⁶ points/s
The probe measures what the OPX → host path sustains across the plausible range of use. It does not
measure one assumed rate. A measurement's delivered rate is roughly

    points/s ≈ 1 / (t_integration × N_averages + t_settle + t_overhead)

| Regime | Typical per-point cost | Delivered points/s |
|---|---|---|
| DC transport / slow stepping (gates stepped by a DC source, ms settle) | 1–10 ms | 10²–10³ |
| RF-reflectometry charge sensing, stepped | 10–100 µs integration, some averaging | 10⁴–10⁵ |
| Fast/"video-mode" maps (OPX sweeps both axes, minimal averaging) | 1–5 µs | 2×10⁵–10⁶ |
| Raw/near-raw bursts | < 1 µs | above 10⁶, short bursts only |

The ladder (10³, 10⁴, 10⁵, 10⁶ and unpaced) covers every row. The unpaced run finds the ceiling. The
answer for your own measurements is the row matching your integration time and averaging. The design target
(10⁶ points/s) sits at the top of the video-mode row.

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
Environment: qm-qua ___, QOP ___, scope firmware ___ (from the script output).

| Item | OPX | Scope |
|---|---|---|
| Delivery granularity | | whole record per query |
| Partial fetch mid-acquisition (whole-frame buffer) | | n/a |
| Delivered points/s at 10³ / 10⁴ / 10⁵ / 10⁶ / unpaced, per line | | |
| Same, per point | | |
| Highest rate without data loss (per line / per point) | | n/a |
| Inter-arrival median / p95 at 10⁵ per line | | |
| Fetch cost (µs per point) | | transfer ms per record length |
| Coordinate addressing | positional (expected) | explicit time axis (expected) |
| Time-axis origin spread across captures (samples) | n/a | |
| In-band metadata / timestamp-stream cost | | preamble only |
| Push or pull | pull (expected) | pull (expected) |
| Dtype / shape on fetch | | 16-bit signed/unsigned, 1-D |
| Runtime-variable without recompile (input stream / IO1) | | n/a |

## What the findings decide
- `DatasetChunk` must carry either explicit coordinates or an *index range + reference to the definition*; the probe says which the OPX path needs and whether partial lines occur.
- The stream server's poller cadence and chunking policy (per line vs per frame).
- The shape of `SweepDefinition.backend_payload` for QUA.
- Whether the synthetic source's emulated envelope (Analysis 0001 targets) is above measured reality — it should be, by ~10×.
