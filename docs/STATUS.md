# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 3 — Measurement registry → `docs/steps/03-registry.md`
**Branch:** `step-2/freeze` (PR against `main` open; the human merges). Next session: `step-3/<short-name>` from `main`.
**Last session:** 2026-10-12, session (12). Closed Step 2: the human confirmed the live honeycomb in Flight
Deck; a pre-freeze review fixed how backends learn channel declarations (ADR 0021); froze the protocols
(ADR 0021) and the stand + activity + pulse slices (ADR 0022); Flight Deck averages repeated scans on display.

## Step 3 exit criteria
| Criterion | State |
|---|---|
| any simulated measurement answerable by query (device, stand, definition) | ✘ not started |
| envelope + identity slices frozen with ADR | ✘ not started |
| L0: ephemeral Postgres round trip; migration fixtures; JSON Schema + DDL no-diff; sweep → record → Flight Deck replay | ✘ not started |

## Done
- Steps 0–2 DONE. ADR 0001–0022. Two deliberate freezes made: the `Dataset` contract (ADR 0015) and the
  capability protocols (ADR 0021). Stand/activity/pulse frozen at `schema_version` 1 (ADR 0022).
- **Backend construction (ADR 0021):** every backend is built by a `BackendFactory`
  `(InstrumentConfig, tuple[ChannelMap, ...])` (usually `from_config`); `build_backends(stand, factories)`
  wires a stand; `StandConfig.instrument_channels`. Conformance test `sense_honours_declared_integration_time`.
  `SimulatedDevice.from_config` checks quantity against role and takes the sensor aperture from the map.
- **Flight Deck:** a 3-D variable with two bounded trailing dims renders as the NaN-aware mean over the
  leading dim (`view.ts` `meanAlongLeading`), so `python -m qdt_sim --repeats N` / `--repeats 0` is viewable.
- `qdt-sim` (ADR 0020), experiments as data (ADR 0018/0019), protocols + twins + conformance (ADR 0016/0017),
  stream + Flight Deck (ADR 0010–0014). 171 Python tests, 25 Flight Deck unit + 2 e2e.

## In flight
- Nothing uncommitted. PR `step-2/freeze` → `main` open; human merges.

## Known broken / not yet real
- Model has no tunnel coupling, spin, valley or Pauli blockade; pulses are quasi-static; `Drive` only
  advances the clock. Each is an ADR when a sweep needs it. Per-shot Python loop: fine to ~10⁵ pixels.
- Flight Deck: first Dataset only; no axes/colorbar/cursors/zoom. Repeat averaging recomputes dirty rows over
  every pass (cost grows with passes; fine at demo sizes). Client store and server history unbounded (Step 6).
- `test_wire_path_keeps_design_target_line_rate` is wall-clock bound off hardware (fails ~2/3 on a 4-vCPU
  container). Decide advisory treatment (cf. ADR 0014).
- Waveform protocols are frozen without a real call site (ADR 0021 accepts the risk). QUA emitter (Step 5).
  Scope captures per stepped point deferred (ADR 0019). Probe 01 scope half unrun. `FINISH_LINE.md` TODO
  (human). `BENCH.md` skeleton; DUT #10.
- Windows dev box: `pnpm` is not on PATH; use `corepack pnpm ...` in `apps/flightdeck` (or `corepack enable`
  from an admin shell).

## Next action
**Human:** merge the `step-2/freeze` PR, check CI.
**Then** a session on `step-3/<short-name>` starts Step 3: settle open decisions #2 (`payload_hdf5` location)
and #4 (offline cache + sync) with the human first. Then add the `identity.py` + `envelope.py` slice
(`MeasurementRecord` first, `migrations.py` begins), stand up `qdt-registry` against a localhost Postgres
(compose; check Docker availability on the dev box) and an ephemeral Postgres in CI, and have the executor
write one `MeasurementRecord` per run of a Step 2 sweep.

## Decisions pending (see plan §12)
- #2 `payload_hdf5` location, #4 offline cache + sync — Step 3, before code. #10 surrogate DUT — by Step 5 entry.
- Whether the stream line-rate test becomes advisory off hardware (see Known broken).
