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

## Findings
OPX run 2026-10-11 (`bench/fixtures/probe01/`, dry run in `quick/`). Environment: qm-qua 1.4.1, QOP 3.7.1
(gateway 3.7.1-14777), OPX1000 with one LF-FEM output, API v2. **Scope not run yet** (no scope access that
day); the Scope column is still the expectation.

| Item | OPX | Scope |
|---|---|---|
| Delivery granularity | Whatever the stream processing says: `save_all` per point shows any number of points per poll (partial lines occur); `buffer(M).save_all` shows only whole lines; `buffer(N,M).save` shows only the whole frame | whole record per query |
| Partial fetch mid-acquisition (whole-frame buffer) | **No.** `count_so_far` stays 0 and `fetch_all` returns `None` until the frame completes (40 polls over 5 s). Near completion `fetch_all` can raise `DataFetchingError: Fetched items count is not a round number: <fill fraction>`: the server tracks partial fill, but the client API will not return it | n/a |
| Delivered points/s at 10³ / 10⁴ / 10⁵ / 10⁶ / unpaced, per line | 1,001 / 10,004 / 100,157 / 999,109 / 3,172,928 | |
| Same, per point | 999 / 9,973 / 99,672 / 991,817 / 2,886,416 | |
| Highest rate without data loss (per line / per point) | No loss anywhere: 10⁶ sustained for 5 s both ways; unpaced ≈ 3.2×10⁶ / 2.9×10⁶ (a 2×10⁶-point burst, ≈ 0.7 s, not 5 s sustained). The OPX → laptop path is not the bottleneck at the 10⁶ target | n/a |
| Inter-arrival median / p95 at 10⁵ per line | 28 / 31 ms (per point: 27 / 30 ms). This is the client's poll loop, not the server's publication period: one `fetch` call costs ≈ 17 ms, so visibility is only resolved to ≈ 30 ms. At 10³ and 10⁴ per line it is the line time (1000 / 101 ms) | |
| Fetch cost (µs per point) | Dominated by a fixed ≈ 16–20 ms per `fetch` call (24 ms at 10⁶, 30–40 ms for 2–4×10⁵-point slices). Per point: 6.0 at 10⁵, 0.65 at 10⁶, 0.26–0.28 unpaced. At 10⁶ a single poller spends ≈ 65 % of wall time fetching | transfer ms per record length |
| Coordinate addressing | Positional confirmed: values equal the flat loop index on every complete fetch (`positional_ok` true, all line runs and the frame); no in-band coordinates | explicit time axis (expected) |
| Time-axis origin spread across captures (samples) | n/a | |
| In-band metadata / timestamp-stream cost | None in band. A `timestamp_stream` on a play gives int64 timestamps in **4 ns clock cycles** (median step 2504 = 10.016 µs at 10⁵ pts/s). Cost negligible: 99,868 vs 100,157 pts/s, same fetch cost | preamble only |
| Push or pull | Pull: poll `count_so_far`, then `fetch(slice)` | pull (expected) |
| Dtype / shape on fetch | int64 for int saves; per line `(n_lines, M)`, frame `(N, M)`, per point 1-D. Fixed-point saves not exercised (all saves were int) | 16-bit signed/unsigned, 1-D |
| Runtime-variable without recompile (input stream / IO1) | Step count, sweep step (hence endpoint) and averaging count all change on **one compiled program** via an int input stream (two runs: 50×3×1000, 120×7×2500, exact). IO1 via pause/resume sets the step count. **Fixed-typed input streams do not compile on QOP 3.7.1** (server `INTERNAL` error), so fractional parameters must go in as scaled ints. API v2 `add_to_queue` returns while "In queue"; pushes must wait for "Running" | n/a |

**Scope column and the freeze (2026-10-11).** The HD3-Series Programmer's Guide already establishes that the
time axis is `xorigin + i·xincrement` per record and that the origin can differ per capture
(`:WAVeform:SEGmented:XLISt? RELXorigin`). The proposed direction (STATUS.md, decided in the freeze ADR) keeps
alignment in the producer: declared coordinates are exact, and the scope driver aligns or resamples records and
may publish the residual offset as a data variable. Under that direction the scope run informs the Step 5
driver (offset magnitude, whether resampling is worth it) and does not gate the freeze.

## What the findings decide
- `DatasetChunk` must carry either explicit coordinates or an *index range + reference to the definition*; the probe says which the OPX path needs and whether partial lines occur.
- The stream server's poller cadence and chunking policy (per line vs per frame).
- The shape of `SweepDefinition.backend_payload` for QUA.
- Whether the synthetic source's emulated envelope (Analysis 0001 targets) is above measured reality — it should be, by ~10×.
