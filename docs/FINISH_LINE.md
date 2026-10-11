# Flight Deck — Finish-Line Sketch

**Status:** SKELETON — human-authored before any UI code (Step 2 entry gate).
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

## TODO (human)
- [X] Add rows for anything the prior Flight Deck / gatepick work did that is still wanted. Reference only; nothing is imported.
