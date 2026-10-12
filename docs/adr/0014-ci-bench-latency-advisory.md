# 0014 — CI gates the renderer bench on rendered rate; latency is advisory there

**Status:** Accepted
**Date:** 2026-10-11
**Step:** 1

## Context
The Flight Deck `bench --assert` step (2048², 10⁶ pts/s, steady-state p95 ≤ 50 ms) was added to CI with
ADR 0013 and never passed. CI has no GPU, so it renders with SwiftShader on a small shared runner. Two runs of
identical code gave a steady p95 of 334 ms and 78 ms. A MacBook gave 1250 ms and the Analysis 0002 machine
11 ms. The rendered rate met its target (≥ 95 % of 10⁶ pts/s) every time. On software rendering, latency
tracks the host's load and CPU, not the code.

## Decision
In CI, run `pnpm bench … --assert --latency-advisory`: gate on rendered rate, print latency without gating.
The ≤ 50 ms exit criterion is evidenced by the committed hardware-GPU results in
`apps/flightdeck/bench/results/` (Analysis 0002), rerun when the renderer changes.

## Consequences
- Easier: CI is green on what it can measure reliably; a throughput regression still fails it.
- Harder: a latency regression is not caught automatically; it shows only as a printed number in CI logs
  or in a hardware rerun.
- Must now: rerun `pnpm bench --gpu hardware --out bench/results/<date>-hardware.json` and commit it when
  the render path changes; plain `--assert` (latency gated) remains the local/hardware check.

## Alternatives considered
- Loosen the CI latency threshold (e.g. 500 ms) — rejected: a bound wide enough to survive 78–1250 ms
  swings catches nothing useful.
- Larger or GPU CI runners — rejected for now: costs money and still shares hardware; revisit if latency
  regressions become a real risk.
- Keep gating latency on SwiftShader — rejected: fails on unchanged code, which teaches people to ignore CI.
