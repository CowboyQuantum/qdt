# Flight Deck — Finish-Line Sketch

**Status:** AUTHORED 2026-10-11 — human-owned; Step 1 entry gate. Revise rows by ADR, not silently.
**Purpose:** This is *not scope*. It is the requirements document for the `Dataset` /
`DatasetChunk` / `Annotation` stream contract and the front end's source/view architecture.
Each row states an end-state capability and the constraint it imposes on the contract *now*.

| End-state capability | Constraint on the contract / architecture now | Verified by |
|---|---|---|
| Live 2D with cursors and line cuts | Streaming partial updates; coordinate-addressable chunks | L0 replay + snapshot |
| Derivative / filtered / normalized views as toggles | Typed arrays on the client; transforms client-side, no round-trip | L0 unit |
| Fit and feature overlays | `Annotation` layer sharing the data's coordinate system, same stream | Step 5 |
| Gate-voltage navigation / click-to-set | View can emit set-parameter requests upward (only "up" edge) | Step 6 |
| Multiple simultaneous sources (live, registry, sim) | `Source` abstraction from day one; source-equivalence test | L0 |
| Side-by-side compare across cooldowns | Datasets addressable by registry ref, not file path | Step 4 |
| Tune-up / DAG state display | Lifecycle state is a schema object, rendered, never stored in the UI | Step 6 |
| Workspace: several plot panes at once, composable side columns, one Run | View state per pane over one shared `DatasetStore`; layout is UI state, not lifecycle; Run binds to a compiled plan's identity | Step 6b (ADR 0054) |
| Craft sweeps and pulse sequences, run them, run curated analyses, browse records — all in the UI (ADR 0032) | A request/response API beside the stream (`qdt-server`); every UI-initiated action is a schema object (`SweepDefinition`, `Run`, `MethodSpec`); the UI never holds an instrument or registry handle (rule 8) | Step 4b e2e (`apps/flightdeck/e2e/control.test.ts`) and `scripts/demo_control_path.py`; slice frozen (ADR 0036) |

## Design targets (Analysis 0001, ADR 0008)
Ceiling of plausible dot-tuning need. The synthetic source emulates this envelope; the L0 throughput test asserts it.

| Target | Value | Why |
|---|---|---|
| Largest 2D map | 2048 × 2048, float32 | ~4× linear over a typical high-resolution stability diagram |
| Sustained stream rate | 10⁶ points/s | ~10× over practical OPX processed-result rates |
| Live-mode latency | ≤ 50 ms glass-to-glass | below the threshold at which a live map feels laggy |

These replace the former "open inputs" (largest map, fastest chunk). Those are *sizes*, boundable by arithmetic; what still needs measurement is *shape* — see `docs/probes/01-stream-semantics.md`.

## TODO (human)
- [X] Add rows for anything the prior Flight Deck / gatepick work did that is still wanted. Reference only; nothing is imported.
- [ ] Confirm or adjust the design targets above against your own expectation of the largest map you will tune with.
