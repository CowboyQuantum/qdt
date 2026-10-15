# Step 6 — Closed-loop tuning

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Calibration DAG nodes (experiment + analysis + decision) run unattended against `SimulatedDevice`, then are confirmed on hardware. Flight Deck gains gate-voltage navigation.

## Schema slice
`modeling.py`: `SimScenario`, `SimResult`, `CalibrationNode`.

## Deliverables
- DAG runner; nodes verified against sim before any L3 contact
- DAPS forward model + bias study as sim scenarios + analysis routines
- Flight Deck click-to-set (the one 'up' edge)

## L0 tests (CI)
- every DAG node passes against `SimulatedDevice` in CI; committed scenario outcomes reproduced

## L1 tests (bench loopback)
- none

## L2 tests (instrument-on-instrument)
- none

## Exit criteria
- a multi-node tune-up runs unattended against the sim
- first L3 contact as confirmation, not discovery

## Open decisions
Carried from Step 5, each with its evidence; an ADR closes each one.
- **A `PlayedWaveform` activity.** Nothing in a sweep plays a waveform: L2-3's pulse train was played
  beside the capture sweep by the test (ADR 0047, BENCH.md L2-3). A tune-up node that steps a DC level
  and records a scope response needs the play inside the sweep, in the same additive shape as
  `CapturedWaveform`.
- **Sub-ms stepping.** Probe 04: a QDAC `set` over USB serial reaches the output within 4.5 ms (steady to
  ±0.2 ms) and settles to 1 % in 3 µs; `settle_s = 0.01` direct, `0.05` through the combiner. Faster
  untriggered stepping has to move the step onto the sequencer (the OPX's DC offset, or a QDAC list with
  a hardware trigger) or measure the Ethernet link. Decide what the DAG's inner loop needs before any
  driver work.
- **How a sense range is declared** (channel map vs. inferred). The 2450 autoranges its current
  measurement to 10 nA at 0 V and then charges a cable at 10 nA; the QDAC-II's LOW range measures nothing
  on the bench unit (BENCH.md). L2-2 sets both over the drivers' transports. A `ChannelMap` field is the
  obvious home; an unattended node cannot set front panels.
- **A rest level at a sweep's end.** A sweep leaves its last level on the QDAC (ADR 0038 holds levels,
  never zeroes them). A DAG that chains nodes needs to say where a node leaves the device.
- **Flight Deck's time-series view remainder.** Axes and labels on the trace, the method list filtered
  by `applies_to`, an analysis output curve beside the trace (ADR 0046, 0047). A tune-up's DAG state
  display (FINISH_LINE.md) joins it as a rendered schema object.
- **Physics the DAG needs.** Tunnel coupling and transport through the double dot (bias triangles) are
  deferred Step 6 ADRs (ADR 0020, 0030); which nodes need them decides their order.
- **Default operating point per device** (not in ADR 0038); whether the diamond estimator should survive
  warm edges; the dot model's zero-clipping (ADR 0020).

## Status
IN PROGRESS (opened 2026-10-15 on the human's word after Step 5 closed). Session 1: the file gained its
Open decisions from Step 5's bench record; nothing built yet. First task: the schema slice's shape
(`SimScenario`, `SimResult`, `CalibrationNode`, ADR 0033 reserved the names) and the first node, against
`SimulatedDevice` only (ADR 0007).
