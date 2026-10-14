# Step 4b — Control path: craft, run and analyse from Flight Deck

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`. Inserted before Step 5 by ADR 0032.

## Goal
A user does the whole simulated loop from the browser: picks a stand and device, crafts a sweep with a pulse sequence, runs it against `SimulatedDevice`, watches it live, finds the record in the registry, runs a curated analysis, and sees its overlays and output. No terminal beyond starting the server.

## Schema slice
`control.py`: `Run` (lifecycle of one execution: plan reference, state, timestamps, record id once recorded, error), `MethodSpec` (catalogue entry for a curated method: name, version, parameter schema, applicable Dataset shapes, promised estimates; embeds the `FitModel` a result carries). Frozen at exit.

## Deliverables
- `packages/qdt-server` (`python -m qdt_server`): HTTP API for commands and queries (stands/devices; validate + compile a `SweepDefinition`; start/watch/abort a run; find records; list methods; run a method; fetch results and outputs) beside the existing `StreamServer` for data. Simulated backend only in this step. Framework and wire shape by ADR in the first build session.
- Flight Deck: sweep editor and pulse-sequence editor (forms driven by the generated JSON Schema), run panel with the live view, records browser, analysis panel (method, parameter form, run, overlay toggle, open output), two views side by side (record + output).
- Rule 8 kept: the UI speaks only to the server's API and the stream; it never imports a driver.
- A scripted demo (`scripts/demo_control_path.py` or the server's `--demo`) and an updated `docs/FINISH_LINE.md` row.

## L0 tests (CI)
- API contract tests against `SimulatedDevice`: validate/compile errors map to responses; a run goes queued → running → completed and produces a record the registry finds; a method run stores a result with its output.
- `Run` and `MethodSpec` round-trip; a `MethodSpec` for each curated method exists and its parameter schema accepts the method's `DEFAULTS` and rejects a wrong type.
- Flight Deck unit tests for the editors (schema → form → valid object) and e2e (Playwright): form → run → live map → record listed → analysis → overlays.
- Source equivalence and the rule-8 import check still pass.

## L1 tests (bench loopback)
- none

## L2 tests (instrument-on-instrument)
- none

## Exit criteria
- The e2e above passes in CI and as a scripted demo on one machine with only the server running.
- `control.py` frozen with an ADR.

## Open decisions
- Web framework and API style — resolved by ADR 0034: FastAPI, REST for commands and queries, the existing WebSocket for data.
- Where the pulse-sequence editor stops — resolved by ADR 0035: a form over `PulseSequence` (rows, number-or-symbol cells, bindings); no timeline, no segment editing in 4b.
- Authentication: none in 4b (single machine); multi-user and the lab PC are Step 7.

## Status
DONE (2026-10-13, ADR 0036). Session 1: ADR 0034, `control.py`, `packages/qdt-server`, API contract
tests. Session 2: OpenAPI export (drift-checked) and `pnpm gen:api` → `src/schema/api.ts`;
`src/api/client.ts`; `src/control/` (sweep builders, method parameter forms, the panel: craft, run,
runs, records, analysis, overlays, outputs); every announced Dataset selectable; `e2e/control.test.ts`.
Session 2b: view options (derivative / gradient transforms, swap axes, axis labels). Session 3: the
pulse-sequence editor (`src/control/sequence.ts`, ADR 0035), 1-D sweeps, `POST /runs/{id}/abort` and
an abort button, `qdt-server --ui` and `scripts/demo_control_path.py`, the `control.py` freeze (ADR 0036).
