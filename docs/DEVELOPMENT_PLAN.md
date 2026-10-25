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
│   ├── BENCH.md              # bench fixture: instruments, loopback map, L2 instrument-on-instrument wiring
│   ├── module-registry.html
│   └── adr/
├── packages/
│   ├── qdt-schemas/          # pydantic only (+ optional [hdf5] extra); grows one slice per step
│   ├── qdt-lab/              # instrument capability protocols, drivers, simulated backends,
│   │                         #   experiment compiler + executor, Dataset stream server
│   ├── qdt-analysis/         # pure-functional: records in, AnalysisResult out; NO I/O
│   ├── qdt-registry/         # record-keeping engine; the ONLY package that touches a database
│   ├── qdt-sim/              # physics models; exposes SimulatedDevice behind qdt-lab protocols
│   ├── qdt-telemetry/        # cryo context ingest from existing fridge monitoring (Step 7, ADR 0051)
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
| 3 | Envelope + identity | `MeasurementRecord`, `DeviceRecord` (`CIRecord`, `AssetRecord`, `BaselineRecord` deferred until consumed, ADR 0025) | `identity.py`, `envelope.py` |
| 4 | Modeling | `FitModel`, `Estimate`, `AnalysisResult` | `modeling.py` |
| 4b | Control | `Run`, `MethodSpec` (ADR 0032) | `control.py` |
| 5 | — | (drivers; no new family) | |
| 6 | Modeling | `SimScenario`, `SimResult`, `CalibrationNode` | `modeling.py` |
| 6c | Operations | `ChannelLimit`, `StandState`, `QueuedRun` (ADR 0075); `InstrumentPort`, `InventoryEntry`, `StandVersion` (ADR 0077) | `operations.py` |
| 7 | Cryo | `CooldownRecord`, `FridgeEvent` (`TelemetryChannel`, `TelemetrySample` deferred — ADR 0051) | `cryo.py` |
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
| L2 | Instrument-on-instrument | The bench's instruments reading each other through off-the-shelf parts (a bias tee; the scope's 1 MΩ input): a DC + pulse map with a plane oracle, current readout into a known load, a real exponential (ADR 0040; no custom board) | Bench, `@hardware` |
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
| 4b | Control path (ADR 0032) | A user crafts a sweep + pulse sequence, runs it on the simulator, finds the record, runs a curated analysis — all from Flight Deck via `qdt-server` | `steps/04b-control-path.md` |
| 5 | Instrument drivers — last mile | Real OPX/QDAC/scope/SMU behind the protocols; L1 loopback; L2 instrument-on-instrument; first bench reports | `steps/05-instrument-drivers-last-mile.md` |
| 6 | Closed-loop tuning | DAG runs unattended against sim; first fridge contact as confirmation | `steps/06-closed-loop-tuning.md` |
| 6b | Flight Deck workspace | Three columns of widget panes, plots in the centre, one Run (ADR 0054–0059) | `steps/06b-flightdeck-workspace.md` |
| 6c | Lab deployment (ADR 0073) | Registry on `qdt-db` readable from any lab computer; an enumerated task set orchestrated by the server and verified on the bench through the scope; parameters and scan analysis exercised through Flight Deck | `steps/06c-lab-deployment.md` |
| 7 | Other sources | Cryo context, CI register, internal extension, pilot demo | `steps/07-other-sources.md` |
| 8 | Frameworks | Governance as data; HTML demoted to renderers | `steps/08-frameworks.md` |

**Sequencing notes.** Steps 0–4b are serial and run entirely against simulated backends on personal hardware (4b inserted by ADR 0032: the full UI demo on the simulator comes before drivers). Step 5 is the first point where instrument reality can push back; the Step 1 probe is the hedge. Step 6c (lab deployment, ADR 0073) is inserted before Step 7 the way 4b was before 5; Step 7 is off the critical path; no step is gated by an approval outside the repo (ADR 0072). Steps 6c and 7 can interleave.

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

## 9. IT engagement checklist — a deliverable of Step 6c (ADR 0072, 0073)

Rewritten 2026-10-25 from Analysis 0003, ADR 0074/0080/0082 and the Step 6c rehearsal (the runbook
`deploy/qdt-db/README.md` ran end to end on a personal PC standing in as `qdt-db`, 2026-10-23/24). This is
the text to send; the placeholders (`qdt-db`, `<lab-subnet>`, `<office-subnet>`) are filled in by the
sender, never here (rule 7). Nothing in this list gates a step (ADR 0072): the lab deployment is a second
run of a runbook that already works.

**What is being deployed.** One ordinary Windows PC, `qdt-db`, runs three things as native services or
scheduled tasks that start with the machine and need nobody logged in: PostgreSQL (the measurement
database), a shared folder (the measurement data files, written by the measurement PC only), and the
project's read server (a Python process that serves the database read-only over HTTP, with a web page for
browsing measurements). The measurement PC keeps driving the instruments as today and copies each record
to `qdt-db` as it is taken; it keeps working when `qdt-db` is away. No Docker, no WSL, no VM, no container
platform, no new server hardware beyond the one PC. We operate it; IT is asked for the items below.

| # | Ask | Detail |
|---|---|---|
| 1 | **A dedicated Windows PC as `qdt-db`**, with local administrator rights for the person installing it | Installs: PostgreSQL (native Windows service), Node.js, `uv`. Sizing per Analysis 0003 §7: 16 GB RAM, 4 cores, SSD for the database, a large disk for data files (4 TB, growable). Wired gigabit. Never sleeps; restarts after power loss. |
| 2 | **A fixed address and the name `qdt-db`** | DHCP reservation or static address, and a DNS entry `qdt-db`; until DNS exists, a `hosts` entry on each client. The measurement PC and every desk find the database and the read server by this name. |
| 3 | **Inbound firewall on `qdt-db`, scoped to `<lab-subnet>`** | TCP **5432** (PostgreSQL: the measurement PC as writer, desks and scripts as reader); TCP **445** (the data-file share, mounted by the measurement PC only); TCP **8700** and **8765** (the read server's HTTP API with the web page, and its data stream). Rules are created by the runbook with `New-NetFirewallRule`; IT confirms the subnet and that the host firewall is allowed to hold them. |
| 4 | **The read server's ports from `<office-subnet>` too**, if people will browse measurements from office desks | TCP 8700 and 8765 only; 5432 and 445 stay lab-only. The read server cannot operate anything (ADR 0074). |
| 5 | **Inbound on the measurement PC from `<lab-subnet>`**: TCP 8700 and 8765 | For Flight Deck on a second desk driving the stand (Step 6c goal 3). Commands from another computer need a bearer token the stand server's owner issues and can revoke (ADR 0082); reads need only the network. |
| 6 | **Windows Update policy for `qdt-db`** | Restarts allowed at an agreed hour; every service starts on its own after a reboot (proven by the runbook's "after a reboot" check, bench row R-3). No agent that sleeps or hibernates the machine. |
| 7 | **A backup landing place off the machine** | A share on another machine or a NAS reachable from `qdt-db`, at least the size of the data-file disk, for the nightly database dump and data-file mirror (the rehearsal used a second internal disk, which is not enough for the lab). A restore drill is repeated on a calendar (the first two: 2026-10-24, 2026-10-31). |
| 8 | **An account the services run under** | A local account on `qdt-db` whose scheduled tasks run at boot without a logged-in user, and the right to store the three database passwords outside the repository on each machine (Analysis 0003 §6). No domain changes needed. |
| 9 | **The instrument network** | Which subnet the instruments sit on, DHCP reservations for them (good practice; the software binds to identity, not address, ADR 0077), and **whether an opt-in probe of a configured, bounded instrument address range is allowed** at all. If not, discovery uses mDNS and configured hosts only. *Open decision of Step 6c (ADR 0077): the range the probe may touch.* |
| 10 | **Encryption in transit, when a client is on another subnet** | TLS on 5432 and on 8700/8765 the moment any reader is outside `<lab-subnet>` (Analysis 0003 §5); a certificate for `qdt-db` from IT's issuer, or IT's statement that the office subnet is trusted. |

**Not asked now** (Step 7, plan §12 row 7): the access mode for the lab's existing fridge monitoring and
logs (ADR 0051), and the prototype → managed-VM trajectory (Analysis 0003 §9: a dump, a mirror and one
name change move the whole thing; no client code changes).

**Retired from the earlier version of this list:** Docker approval (Engine-in-WSL2 vs Desktop licensing) —
nothing runs in a container; ports 8100, 9000, 9001 — the HTTP payload upload waits for the hub (ADR 0076)
and 9000/9001 were MinIO defaults, which Analysis 0003 rejected.

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
| 2 | `payload_hdf5` location | RESOLVED (ADR 0023): `qdt-schemas[hdf5]` extra, lazy imports |
| 3 | DAG contract scoping ×3 | Step 8 only |
| 4 | Offline/prober operation | RESOLVED (ADR 0024): local cache first, idempotent sync to Postgres, client-minted UUIDs |
| 5 | Withdrawn | **Closed by ADR 0072** (2026-10-19): no step is gated by an approval outside the repo. |
| 6 | Lab PC OS | Resolve in Step 6c (ADR 0073; issue #114) |
| 7 | Bluefors log access mode | Resolve via IT ask at Step 7 |
| 8 | Stream transport for `Dataset` | RESOLVED (ADR 0008): WebSocket + Arrow IPC; see `docs/analysis/0001-stream-budget.md` |
| 9 | Flight Deck stack | RESOLVED (ADR 0013): TypeScript; raw WebGL2 2D renderer, no library; see `docs/analysis/0002-renderer-benchmark.md` |
| 10 | Surrogate DUT design | **Closed by ADR 0040:** no board; L2 is instrument-on-instrument (bias tee, the scope's 1 MΩ input) |
| 11 | §10 scope: frames, named envelopes, balanced branching | Parked; inputs in `docs/analysis/0004-pulse-scope-and-custom-isa.md`; admit one at a time by ADR with the quartet |
| 12 | Backend capability declaration on `InstrumentConfig` | Parked; required before any primitive not every backend executes (Analysis 0004) |

## 13. Success criteria

1. Every step on the roadmap has a scripted bench demo that passed, with a committed dated report.
2. Any measurement, simulation, or fit answerable by query — device, stand config, definition, model, parameters — no archaeology.
3. One-commit schema evolution with CI proving all consumers updated.
4. A new instrument reaches full use by implementing a protocol and passing the conformance suite; a new data source reaches Flight Deck by implementing `Source` and passing source-equivalence.
5. A full tune-up DAG runs unattended against `qdt-sim` before touching a fridge.
6. Substrate pilot demo runs entirely off this repo's schema exports; graduation ask evidenced by runtime.
7. A second person can clone, install, and produce a conforming record within a day.
8. Seam stays auditable: public repo passes the grep test at every commit.
