# QDT — Quantum Dot Toolkit: Development Plan & Roadmap

**Status:** v0.4 · **Owner:** Captain · **Date:** 2026-10-11
**Scope:** Personal measurement/simulation/infrastructure toolkit for silicon spin qubit work; local-first pilot for the Diraq database substrate proposal.
**v0.4 changes (ADR 0007):** sequence reordered to **simulation-first** — `Dataset` contract and Flight Deck v0 first against synthetic/replay sources, experiments over `qdt-sim`'s `SimulatedDevice` second, registry and analysis next, and real instrument drivers as the **last mile** (Step 5) with the first bench reports; the test ladder is unchanged. §7's per-step detail moved to `docs/steps/` (one file per step, fixed headings — the operational spec agents read); §7 here is now the ladder plus an index. Requirements are tracked as ADRs over time; only the `Dataset` stream contract (Step 1) and the capability protocols (Step 2) get a deliberate freeze.
**v0.3 changes:** roadmap rewritten from two parallel tracks (v0.2) to an **instrument-up vertical-slice sequence** with a mandatory **test ladder** at every step (new §7); Flight Deck front end restarted from scratch under a frozen `Dataset` contract, with the tuning end-state captured as a **finish-line sketch** that constrains the contract rather than the initial scope (new §8); schema v0 no longer frozen in one session — it grows one slice per step, DDL deferred to Step 4; `qdt-sim` re-sequenced from first deliverable to device-in-the-loop test oracle (Step 6); Track B infrastructure items (telemetry, `qdt-diraq`, IT engagement) moved behind the measurement path (Step 7) and off the critical path. Sections 1–6 carried from v0.2 with edits noted inline.

---

## 1. Purpose

Unify all personal tools under a public engine monorepo (`qdt`, GitHub, Cowboy Quantum org) of independently installable packages with a shared schema package at the root of the dependency tree. All Diraq-specific needs are serviced by a single internal extension package (`qdt-diraq`, Diraq servers only) that plugs into the engine's adapter registry; nothing Diraq-internal ever touches GitHub. The schema layer is the product; the tools are its consumers.

**v0.3 addition:** every roadmap step ends in something that runs on the bench and is proven on the test ladder (§7.1) before the next step begins. Progress is measured in passing hardware-in-the-loop demos, not in documents.

## 2. Naming, brand & license — RESOLVED (unchanged from v0.2)

| Element | Decision |
|---|---|
| Publisher namespace | GitHub org `cowboyquantum` — secured |
| Public repo | `qdt` / "Quantum Dot Toolkit" — confirmed |
| Package prefix | `qdt-` / `qdt_`; no brand in import paths |
| Instrument-control package | `qdt-lab` (import `qdt_lab`) |
| Front end | **Flight Deck** — product name; lives at `apps/flightdeck/` (v0.3) |
| Simulation package | `qdt-sim` (import `qdt_sim`), written fresh (ADR 0020) |
| License (public repo) | Apache-2.0 |

## 3. Repository architecture

### 3.1 `cowboyquantum/qdt` — the engine (GitHub, public, Apache-2.0)

```
qdt/
├── pyproject.toml            # uv workspace root
├── uv.lock
├── LICENSE
├── CLAUDE.md                 # agent conventions (§11)
├── docs/
│   ├── DEVELOPMENT_PLAN.md   # this document
│   ├── FINISH_LINE.md        # Flight Deck finish-line sketch (§8) — written before UI code
│   ├── BENCH.md              # bench fixture: instruments, surrogate DUT wiring, loopback map
│   ├── module-registry.html
│   └── adr/
├── packages/
│   ├── qdt-schemas/          # pydantic only (+ optional [hdf5] extra); grows one slice per step
│   ├── qdt-lab/              # instrument capability protocols, drivers, simulated backends,
│   │                         #   experiment compiler + executor, Dataset stream server
│   ├── qdt-analysis/         # pure-functional: records in, AnalysisResult out; NO I/O
│   ├── qdt-registry/         # record-keeping engine; the ONLY package that touches a database
│   ├── qdt-sim/              # physics models; exposes SimulatedDevice behind qdt-lab protocols
│   ├── qdt-telemetry/        # cryo telemetry collector (Step 7)
│   └── qdt-frameworks/       # schema-validated renderers; NO instance data (Step 8)
├── apps/
│   └── flightdeck/           # TypeScript front end; consumes Dataset streams only
├── bench/                    # hardware-in-the-loop test suites (L1/L2), marked @hardware
└── .github/workflows/
```

### 3.2 `qdt-diraq` — internal extension package (Diraq servers only; unchanged from v0.2)

Adapters (arbok), site DDL migrations, bootstrap seeds, `deploy/` compose bundle, runbook. Consumes `qdt` at pinned tags; never the reverse. Instance data lives in the substrate database, never in git.

### 3.3 Dependency rules (enforced; rule 8 added in v0.3)

1. `qdt-schemas` imports nothing from any other package. Ever.
2. All other packages import `qdt-schemas`; public APIs only between packages.
3. Inter-tool data exchange happens only through schema objects.
4. Database access happens only through `qdt-registry`.
5. `qdt-analysis` is pure-functional: no I/O, no registry dependency.
6. `qdt-frameworks` contains no data.
7. Provenance discipline: anything naming a real stand, device lot, internal system, tolerance, or person → `qdt-diraq` only. Public repo passes the grep test at every commit.
8. **Flight Deck never imports an instrument driver and never knows which instrument produced a `Dataset`.** It consumes the `Dataset` stream contract only. (v0.3)

## 4. Schema layer

### 4.1 Object families — now sequenced by roadmap step

| Step | Family | Objects | Module |
|---|---|---|---|
| 1 | Data | `Dataset`, `DatasetChunk`, `Annotation`, `SourceDescriptor` | `data.py` |
| 2 | Stand + Activity + Pulse | `InstrumentConfig`, `ChannelMap`, `StandConfig`; `SweepDefinition`, `ExecutionPlan`, `SequencerProgram`; `PulseSequence` (ADR 0018) | `stand.py`, `activity.py`, `pulse.py` |
| 3 | Envelope + identity | `MeasurementRecord`, `DeviceRecord`, `CIRecord`, `AssetRecord`, `BaselineRecord` | `identity.py`, `envelope.py` |
| 4 | Modeling | `FitModel`, `AnalysisResult` | `modeling.py` |
| 5 | — | (drivers; no new family) | |
| 6 | Modeling | `SimScenario`, `SimResult`, `CalibrationNode` | `modeling.py` |
| 7 | Cryo | `CooldownRecord`, `FridgeEvent`, `TelemetryChannel`, `TelemetrySample` | `cryo.py` |
| 8 | Governance | `ContractDefinition` | `contracts.py` |

**Rule:** a family is added in the step that first consumes it, and is frozen only after that step's test ladder passes. No DDL exists before Step 3; schema churn is cheapest before then.

### 4.2 The `Dataset` contract (the one interface to get right early)

xarray-shaped: named coordinates with units, named data variables with units and dtype, free-form metadata, and a `source` descriptor. Delivered in two forms: at-rest (`qdt-hdf5-v1` payload, Step 3) and streaming (ordered `DatasetChunk` messages carrying coordinate-addressed partial updates, Step 1). `Annotation` objects (fit curves, detected features, cursors) share the coordinate system of the `Dataset` they decorate and are delivered on the same stream. The finish-line sketch (§8) is the requirements document for this contract.

### 4.3 Envelope / payload hybrid, versioning, exports — unchanged from v0.2

`MeasurementRecord` is a provenance envelope; strictness lives in payload specs; external systems ride the same envelope via entry-point-registered adapters. Two decoupled version numbers (package version, per-object `schema_version`); `migrations.py` holds pure-dict transforms. JSON Schema and DDL exports with no-diff CI checks, from Step 3.

## 5. Deployment architecture — unchanged from v0.2

Prototype on lab PC via Docker Compose (`qdt-diraq/deploy/`); localhost-bound during pre-staging, LAN-bound after firewall rules; hostname indirection via `QDT_REGISTRY_DSN` from day one; graduation = `pg_dump` → restore → repoint one hostname. Prototype data is a seed corpus, not disposable. **v0.3 note:** the registry first exists at Step 3 on personal hardware (localhost compose); lab PC deployment is Step 7.

## 6. CI

- Per-package jobs with path filters.
- **L0 suite always runs** (§7.1): conformance tests over simulated backends, Flight Deck snapshot and source-equivalence tests, experiment dry-runs, ephemeral-Postgres round trips, migration fixtures, export no-diff.
- **`bench/` suites (L1/L2) are `@hardware`-marked**, excluded from CI, run from the bench via `uv run pytest bench/ -m hardware`, and their last-run results are committed as a dated report so the repo records when hardware was last proven.
- `qdt-diraq` CI (internal): pinned upstream install, round-trip suite, adapter contract tests, compose config validation.

## 7. Roadmap — instrument-up, one proven slice per step

### 7.1 The test ladder (applies to every step)

| Level | Name | What it is | Where it runs |
|---|---|---|---|
| L0 | Simulated | Software doubles implementing the same interfaces as real backends | CI, every commit |
| L1 | Bench loopback | Real instrument, room temperature, numeric oracle (set 1.000 V, read 1.000 ± tol) | Bench, `@hardware` |
| L2 | Surrogate DUT | Passive bench board (resistor divider, RC leg, diode) between sources and acquisition; analytically known nonlinear response → golden curves for sweeps, fits, and renders | Bench, `@hardware` |
| L3 | Fridge | Real device; confirms what L0–L2 already proved | Fridge, rare |

**Step exit rule:** L0 in CI and green; L1 and L2 pass as a scripted demo; the step's schema slice frozen; an ADR for any decision made. L3 is never a step exit criterion.

### 7.2 Steps (ADR 0007 order) — operational detail lives in `docs/steps/`

| Step | Name | What is proven at exit | Detail |
|---|---|---|---|
| 0 | Bootstrap | CI green; docs + enforcement scaffolding; FINISH_LINE.md authored | `steps/00-bootstrap.md` |
| 1 | `Dataset` contract + Flight Deck v0 | Contract frozen against the finish line and a measured L1 probe; 2D live from synthetic/replay | `steps/01-dataset-contract-and-flightdeck.md` |
| 2 | Experiments over a simulated device | `SweepDefinition` runs on `qdt-sim`'s `SimulatedDevice`; protocols frozen; stability diagram streams live | `steps/02-experiments-over-simulated-device.md` |
| 3 | Registry | Records land with provenance; first DDL; registry is a Flight Deck source | `steps/03-registry.md` |
| 4 | Analysis overlays | Fits/detections as `Annotation`s with dual provenance; injection–recovery in CI | `steps/04-analysis-overlays.md` |
| 5 | Instrument drivers — last mile | Real OPX/QDAC/scope/SMU behind the protocols; L1 loopback; L2 surrogate DUT; first bench reports | `steps/05-instrument-drivers-last-mile.md` |
| 6 | Closed-loop tuning | DAG runs unattended against sim; first fridge contact as confirmation | `steps/06-closed-loop-tuning.md` |
| 7 | Other sources | Telemetry, internal extension, lab PC, IT, substrate pilot demo | `steps/07-other-sources.md` |
| 8 | Frameworks | Governance as data; HTML demoted to renderers | `steps/08-frameworks.md` |

**Sequencing notes.** Steps 0–4 are serial and run entirely against simulated backends on personal hardware. Step 5 is the first point where instrument reality can push back; the Step 1 probe is the hedge. Step 7 is off the critical path and is the only step gated by manager sign-off (Open Decision #5). Steps 6 and 7 can interleave.

## 8. Flight Deck finish-line sketch

Written as `docs/FINISH_LINE.md` in Step 0, before any UI code (Step 1 entry gate). It is **not scope** — it is the requirements document for the `Dataset` contract and the front end's architecture, stated as constraints:

| End-state capability | Constraint it imposes now |
|---|---|
| Live 2D with cursors and line cuts | Streaming partial updates; coordinate-addressable data |
| Derivative, filtered, normalized views as toggles | Well-typed arrays on the client; transforms are client-side, no server round-trip |
| Fit and feature overlays (diamonds, transitions, charge sensor lines) | `Annotation` layer sharing the data's coordinate system, on the same stream |
| Gate-voltage navigation / click-to-set | View can emit set-parameter requests upward (the only "up" edge in the stack) |
| Multiple simultaneous sources (live, registry, sim) | `Source` abstraction from day one; source-equivalence test in CI |
| Side-by-side compare (today vs. last cooldown) | Datasets are addressable by registry ref, not by file path |
| Tune-up progress / DAG state display | Lifecycle state is a schema object, rendered, never stored in the UI |

Prior Flight Deck / gatepick work is reference material for what the UI felt like; nothing is imported.

## 9. IT engagement checklist — unchanged from v0.2; sent at Step 7

Admin/install rights on lab PC; Docker approval (Engine-in-WSL2 vs Desktop licensing); firewall inbound 5432/8100 (+9000/9001) scoped to lab subnet; VLAN reachability; DHCP reservation / DNS name `qdt-db`; Bluefors log access mode; backup landing location; declared prototype→VM trajectory; Windows Update policy.

## 10. Out of scope — a *general* pulse compiler (waveform algebra, phase-tracked frames, branching, real-time feedback); rewriting arbok; public PyPI; Diraq-identifying content in the public repo; hardening Windows/WSL beyond unbroken-record minimum. **In scope since ADR 0018:** a minimal backend-neutral `PulseSequence` (`pulse.py`) with per-backend emitters, so a sweep takes its per-shot sequence as data and the same sequence runs on any sequencer with an emitter (OPX/QUA, other AWGs, custom ISAs).

## 11. Claude Code handoff

- This plan, `docs/steps/`, `FINISH_LINE.md`, and `BENCH.md` are the transfer medium, committed at Step 0.
- `CLAUDE.md` encodes: the eight dependency rules; the test-ladder exit rule; schema-slice-per-step discipline (no DDL before Step 3); simulation philosophy (numpy/scipy/xarray, no QuTiP); provenance grep test; house style for `qdt-frameworks`; `@hardware` marker convention and the committed bench-report rule.
- **Session granularity = one `docs/steps/` deliverable.** Suggested first sessions: (1) Step 0 finish — push, CI, LICENSE; (2) Step 1 contract draft from FINISH_LINE.md + synthetic source + ADR; (3) Step 1 Flight Deck stack benchmark → ADR for #8/#9; (4) Flight Deck v0 replay + 1D/2D; (5) Step 2 protocols + `Simulated*` + conformance; (6) Step 2 `qdt-sim` import + `SimulatedDevice`.
- ADRs are written as decisions land, including by Claude Code.

## 12. Open decisions

| # | Decision | State |
|---|---|---|
| 1 | Org + repo name | RESOLVED: `cowboyquantum/qdt` |
| 2 | `payload_hdf5` location | `qdt-schemas[hdf5]` extra vs `qdt-io`; decide at Step 3 |
| 3 | DAG contract scoping ×3 | Step 8 only |
| 4 | Offline/prober operation | Working assumption: client local cache + sync; confirm at Step 3 |
| 5 | Manager sign-off | Pending as of Oct 2026. **Gates Step 7 only.** Steps 0–6 proceed on personal hardware and bench. |
| 6 | Lab PC OS | Resolve via IT ask at Step 7 |
| 7 | Bluefors log access mode | Resolve via IT ask at Step 7 |
| 8 | Stream transport for `Dataset` | RESOLVED (ADR 0008): WebSocket + Arrow IPC; see `docs/analysis/0001-stream-budget.md` |
| 9 | Flight Deck stack | RESOLVED (ADR 0013): TypeScript; raw WebGL2 2D renderer, no library; see `docs/analysis/0002-renderer-benchmark.md` |
| 10 | Surrogate DUT design | Resistor divider + RC leg + diode (proposed); finalize in `BENCH.md` by Step 5 entry |

## 13. Success criteria

1. Every step on the roadmap has a scripted bench demo that passed, with a committed dated report.
2. Any measurement, simulation, or fit answerable by query — device, stand config, definition, model, parameters — no archaeology.
3. One-commit schema evolution with CI proving all consumers updated.
4. A new instrument reaches full use by implementing a protocol and passing the conformance suite; a new data source reaches Flight Deck by implementing `Source` and passing source-equivalence.
5. A full tune-up DAG runs unattended against `qdt-sim` before touching a fridge.
6. Substrate pilot demo runs entirely off this repo's schema exports; graduation ask evidenced by runtime.
7. A second person can clone, install, and produce a conforming record within a day.
8. Seam stays auditable: public repo passes the grep test at every commit.
