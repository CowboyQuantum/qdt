# 0004 — Instrument-up sequencing with mandatory test ladder

**Status:** Accepted — step ordering superseded by 0007; test ladder stands
**Date:** 2026-10-09
**Step:** all

## Context
Plan v0.2 sequenced schema-first with physics and infrastructure in parallel tracks, and stalled on paper. The owner asked for a sequence in which every step is testable on a bench without a fridge.

## Decision
Build vertical slices in the order connectivity → visualization → experiment formulation → remote database → analysis → sim-in-the-loop tuning → other sources → frameworks. Every step exits only when L0 (simulated) is in CI, L1 (bench loopback) and L2 (surrogate DUT) pass as a scripted demo with a committed dated report, the step's schema slice is frozen, and ADRs are written. L3 (fridge) is never an exit criterion. The schema grows one family per step; no DDL before Step 4.

## Consequences
- Easier: every step produces a runnable demo; schema churn happens before DDL exists; fridge time is confirmation, not discovery
- Harder: schema is not frozen early; serial dependency between Steps 0–4
- Must now: maintain the surrogate DUT and BENCH.md; commit bench reports

## Alternatives considered
- Keep v0.2 two-track — rejected: no bench-testable increment before the schema was complete.
- Skip L2 — rejected: loses the physical oracle for 2D sweeps and fits.
