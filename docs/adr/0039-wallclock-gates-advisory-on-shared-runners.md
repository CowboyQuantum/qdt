# 0039 — Wall-clock rate targets are advisory on shared CI runners; a floor at half the target still gates

**Status:** Accepted
**Date:** 2026-10-14
**Step:** 4b follow-up (supersedes 0014)

## Context
ADR 0014 made the renderer bench's latency advisory in CI, after it swung 78–334 ms on identical code.
It kept the rendered-rate target (≥ 95 % of 10⁶ pts/s) as a gate. Two Python tests gate the stream path
the same way:
- `test_wire_path_keeps_design_target_line_rate`
- `test_unpaced_map_sustains_the_design_rate`

On 2026-10-14 the rate gate failed on PR #21: 860k, then 914k pts/s. Local runs of that build and of
`main` both rendered ~998k under SwiftShader, with identical layout. A re-run of **unchanged `main`**
then failed too, at 925k, where the same commit had measured 986k the day before. The gate was measuring
the runner. A red check that a re-run may or may not clear trains people to ignore red checks, and it
blocks merges for nothing.

The human chose to make these targets advisory on shared runners (STATUS decision, 2026-10-14) rather
than lower them.

## Decision
On CI's shared runners, report every wall-clock rate target without gating on it, except for a floor at
half the target:
- **Renderer bench:** a new `--rate-advisory` flag, used with `--assert --latency-advisory`.
  - A rendered rate below 95 % prints a note.
  - Only a rate below 50 % of `--rate` fails, which means a broken renderer, not a slow runner.
- **Python rate tests:** a `wallclock_rate` fixture in `packages/qdt-lab/tests/conftest.py`.
  - Strict by default, so local runs gate on the full target.
  - With `QDT_WALLCLOCK_ADVISORY=1`, which CI's L0 job sets, a rate below target warns, and only a rate
    below half the target fails.

## Consequences
- Easier:
  - CI goes red only for real failures: logic, contracts, pixels, or a path running at under half its
    design rate.
  - Slow-runner noise is visible as notes and warnings in the log.
- Harder:
  - A 10–40 % performance regression no longer fails CI. It shows up as a note, in local runs (strict by
    default), and in the committed bench reports.
- Must now:
  - Treat `apps/flightdeck/bench/results/` (Analysis 0002) as the performance evidence, and re-run
    `pnpm bench --gpu hardware --out bench/results/<date>-hardware.json` when the renderer or the stream
    path changes (as ADR 0014 already required).
  - Any new wall-clock test uses `wallclock_rate` (or the bench flags), never a bare
    `assert rate > target`.

## Alternatives considered
- **Lower the targets.** Rejected by the human. Any fixed number on shared runners either flakes or is
  too loose to mean anything, and it would blur the design target from Analysis 0001.
- **Retry the bench up to N times.** Rejected. It hides the variance and triples the slowest CI step.
- **Remove the gates entirely.** Rejected. The 50 % floor still catches a renderer that silently falls
  back, or a stream that stalls. Those are real failures that CI should flag.
- **A dedicated, quiet runner for performance.** Not available. It would be the right home for a strict
  gate if one existed.
