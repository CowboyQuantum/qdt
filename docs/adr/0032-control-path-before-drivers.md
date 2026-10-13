# 0032 — The control path (server + UI) comes before instrument drivers, as Step 4b

**Status:** Accepted (amends the ADR 0007 order: inserts Step 4b before Step 5)
**Date:** 2026-10-13
**Step:** 4b

## Context
After Steps 1–4 the *data path* is complete and simulated end to end: a `SweepDefinition` with a
`PulseSequence` compiles and runs on `SimulatedDevice`, streams live to Flight Deck, lands in the registry
with provenance, and curated analyses attach results, overlays and array outputs to records. Every one of
those actions is started from a terminal: `python -m qdt_sim`, `scripts/demo_analysis.py`,
`python -m qdt_registry serve`. Flight Deck has one channel in (the Dataset stream) and no channel out;
the only planned "up" edge was click-to-set in Step 6.

On 2026-10-13 the human stated the end state: all of this happens seamlessly in a web app, with users
running curated analyses (not authoring them) from the UI (ADR 0031), and asked that a full-fledged demo
against the simulated backend, where a user crafts sweeps and pulse sequences in the UI and the backend
writes records to the database, come **before** the instrument drivers. ADR 0007 put drivers last for
good reason (simulation first; instrument reality pushes back late); nothing in that argument needs
drivers before the control path, and a working UI makes the Step 5 bench work visible.

## Decision
Insert **Step 4b — Control path** between Steps 4 and 5 (`docs/steps/04b-control-path.md`). Numbering
of Steps 5–8 is unchanged, so every ADR and document that says "drivers are Step 5" stays true.

Step 4b builds the request/response side of the stack:

- A server package, `packages/qdt-server` (`python -m qdt_server`), the one process that holds backends
  and a `Registry`. It exposes an HTTP API for commands and queries (stands and devices; validate and
  compile a `SweepDefinition`; start, watch and abort a run; find records; list curated methods; run a
  method; fetch results and outputs) and keeps the existing `StreamServer` for data. It imports
  `qdt-lab`, `qdt-registry` and `qdt-analysis` through their public APIs and in Step 4b wires only the
  `simulated` backend.
- Flight Deck gains the control UI: a sweep editor and a pulse-sequence editor driven by the generated
  JSON Schema, a run panel with the live view, a records browser, and an analysis panel (choose a curated
  method, fill its parameter form, run, toggle overlays, open outputs). Rule 8 is amended, not relaxed:
  Flight Deck talks to the server's API and the stream only, and still never imports a driver or learns
  which instrument produced a Dataset.
- A new schema family, `control.py`: `Run` (the lifecycle of one execution: plan reference, state,
  timestamps, record id once recorded, error) and `MethodSpec` (a catalogue entry for a curated method:
  name, version, parameter schema, the Dataset shapes it applies to, the estimates it promises; it embeds
  the `FitModel` a result will carry). Lifecycle state is a schema object rendered by the UI and never
  stored in it, as the finish-line sketch already requires.

The web framework and the API's wire shape are decided by ADR in the first build session of 4b, not
here. The exit criterion is a scripted demo and a CI end-to-end test: from a fresh browser with only the
server running against the simulator, a user crafts a sweep with a pulse sequence, runs it, watches it
live, finds the record, runs a curated analysis, and sees overlays and the output map, with no terminal
beyond starting the server.

## Consequences
- Easier: the Step 5 bench work has a UI to run from on day one, and every later step (DAG state display,
  click-to-set, telemetry) extends an existing control channel instead of inventing one.
- Easier: the method catalogue the web app needs (ADR 0031) gets its home.
- Harder: Step 5 slips by the duration of 4b (estimated six to eight sessions). The L1/L2 ladder rows of
  Step 5 are unchanged.
- Harder: a server is a deployment surface. Step 4b runs it on one machine with no authentication;
  multi-user, auth and the lab PC are Step 7 (deployment) concerns and are recorded there, not solved in
  4b.
- Must now: `FINISH_LINE.md` gains a row for the control path (by this ADR); plan §7.2 and §4.1 gain the
  step and its family; rule 8 in `CLAUDE.md` names the server API as Flight Deck's second channel; the
  import-boundary check keeps forbidding drivers in `apps/flightdeck` and forbids `qdt_lab.drivers` in
  the UI only (the server may hold drivers from Step 5).

## Alternatives considered
- Drivers first, as ADR 0007 ordered — rejected by the human: a full demo on the simulator is wanted
  before instrument reality, and the UI is the product surface users will judge.
- Put the control API into `qdt-lab`'s stream server — rejected: `qdt-lab` never touches a database
  (rule 4), and the control path must hold a `Registry`; a separate process keeps the rules intact.
- A notebook-driven workflow (Jupyter cells that call the Python APIs) as the user interface — rejected
  by the human's end state: the scripted and notebook paths stay for developers, not users.
- Renumber Steps 5–8 to make the new step "5" — rejected: ADRs are immutable and several say "Step 5 =
  drivers"; a `4b` keeps every reference true.
