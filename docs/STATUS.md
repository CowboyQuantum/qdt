# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 4 — Analysis as a consumer → `docs/steps/04-analysis-overlays.md`
**Branch:** `step-3/close` (PR #8 against `main`; the human merges). Next session: `step-4/<short-name>` from `main`.
**Last session:** 2026-10-13, session (12, continued). Closed Step 3: Flight Deck shows a replay's record
id (ADR 0027); the Postgres suite ran locally against the compose server; a pre-freeze review fixed a
path-traversal hole in `PayloadRef.path`; identity + envelope + `qdt-hdf5-v1` frozen (ADR 0028).

## Step 4 exit criteria
| Criterion | State |
|---|---|
| a fit runs from a query, writes an `AnalysisResult`, and its overlay renders on the originating dataset | ✘ not started |
| `modeling.py` slice (`FitModel`, `AnalysisResult`) frozen with ADR | ✘ not started |
| L0: injection–recovery on synthetic and `SimulatedDevice` data; `AnalysisResult` needs measurement ref + scenario ref | ✘ not started |

## Done
- Steps 0–3 DONE. ADR 0001–0028. Frozen: `Dataset` contract (0015), protocols (0021), stand/activity/pulse
  (0022), identity/envelope/`qdt-hdf5-v1` (0028). All at `schema_version` 1.
- **Registry (Step 3):** `qdt_registry.Registry`: SQLite cache + payload store, validated `ingest`,
  `find/get/object/device/payload`, append-only idempotent `sync` to Postgres + a payload directory
  (ADR 0024, 0026); `python -m qdt_registry find|sync|serve` (`serve` needs `[serve]`). `RunRecorder` and
  `stream.PayloadSource` in qdt-lab. Tutorial 02. DDL + `records.schema.json` exports with no-diff checks.
- **Flight Deck:** repeat averaging; title shows `· record <id>` for registry replays (the only permitted
  `.source` read, ADR 0027).
- 218 Python tests (+2 Postgres-parametrized when `QDT_TEST_PG_DSN` is set; CI sets it), 26 Flight Deck
  unit tests, 2 e2e.

## In flight
- Nothing uncommitted. PR #8 (`step-3/close` → `main`) open.

## Known broken / not yet real
- Local Postgres: `docker compose -f deploy/registry.compose.yml up -d`, then
  `QDT_TEST_PG_DSN=postgresql+psycopg://qdt:qdt@127.0.0.1:5432/qdt_test`. Use `127.0.0.1`: `localhost`
  stalls ~5 s per connection on Windows. Docker Desktop must be running. VS Code terminals started before the
  Docker install lack `docker` on PATH until VS Code restarts.
- The server payload store is a directory (ADR 0026); a second machine needs object storage or upload (Step 7).
- `RunRecorder` keeps every frame in memory until `finish`; fine at demo sizes.
- Two wall-clock-bound CI gates flake on shared runners: the Flight Deck renderer bench's rendered rate
  (failed on `main` at cc2aec1: 890k vs 950k points/s) and `test_wire_path_keeps_design_target_line_rate`.
  Decide advisory treatment (cf. ADR 0014).
- Carried over: model physics gaps (ADR 0020); waveform protocols frozen without a call site (ADR 0021);
  QUA emitter and real drivers (Step 5); `FINISH_LINE.md` TODO (human); `BENCH.md` skeleton; DUT #10.
- Windows: `pnpm` is not on PATH; use `corepack pnpm ...` in `apps/flightdeck`.

## Next action
**Human:** merge PR #8, check CI. Optional: see a replay with the record id in Flight Deck (record a run
per Tutorial 02 into `~/.qdt/registry`, then `uv run python -m qdt_registry serve <id>` and
`corepack pnpm dev` in `apps/flightdeck`).
**Then** Step 4 on `step-4/<short-name>`: first ask the human what `AnalysisResult`'s "scenario ref"
identifies (nothing in the repo defines it; a `qdt_sim` scenario name + seed is the candidate). Then design
`modeling.py` (`FitModel`, `AnalysisResult` with mandatory measurement ref + scenario ref) by ADR; build
`qdt-analysis` pure functions, starting with charge-transition detection on `SimulatedDevice` stability
diagrams (injection–recovery: the dot model knows the true transition lines); emit results as
`Annotation`s on the originating Dataset; add the overlay in Flight Deck.

## Decisions pending
- What `AnalysisResult`'s "scenario ref" identifies (Step 4, before code). #10 surrogate DUT by Step 5 entry.
  Advisory treatment of the two wall-clock CI gates.
