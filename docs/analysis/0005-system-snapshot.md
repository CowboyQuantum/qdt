# Analysis 0005 — System snapshot: architecture, roadmap, workflows (the chat's conception, 2026-10-19)

**Date:** 2026-10-19 · **Against:** `main` at `d27252f` (ADRs to 0077) · **Step:** 6c
**Kind:** analysis note. Not a decision. A record of how the chat collaborator understands qdt at this
point, kept so later reviews can see what changed. Where it disagrees with an ADR, a step file or
`CLAUDE.md`, those win. Open questions at the end are settled in the human's review; answers are
recorded there, not by editing the body.
**Companion:** `docs/examples/qdt-flow-player.html` steps through eight use cases interactively.

## 1. Architecture

qdt is nine Python packages and one TypeScript app arranged around one rule: `qdt-schemas` defines every
object that crosses a boundary and imports nothing else from qdt.

```
                      Flight Deck (browser): widgets · shared dataset store · WebGL2
                          │ REST: schema objects            ▲ Dataset chunks over WebSocket
                          ▼                                 │
          qdt-server — the composition root (REST :8700 · WebSocket :8765)
          │            │              │               │                │
          ▼            ▼              ▼               ▼                ▼
       qdt-lab ◄── qdt-sim       qdt-tuning     qdt-analysis      qdt-registry
       protocols   simulated     calibration    pure fits         local cache
       executor    double dot    DAG            no I/O            only DB access
          │ protocol calls                                         │ sync()
          ▼                                                        ▼
   ┄ Instruments: QDAC-II · OPX · scope · SMU ┄       ┄ Postgres + payload store ┄
  ═══════════ qdt-schemas: every boundary object; imports nothing from qdt ═══════════
```

| Part | What it does | Key ADRs |
|---|---|---|
| `qdt-schemas` | Every boundary object, frozen per slice with `schema_version`; migrations; JSON Schema, DDL and OpenAPI exports diffed in CI | 0001, 0022, 0028, 0033, 0036 |
| `qdt-lab` protocols | Capability protocols: `LevelSource`/`LevelSense`, `WaveformSource`/`WaveformSense`, `Sequencer`, `TriggeredLevelSource` | 0016, 0017, 0021, 0064 |
| `qdt-lab` drivers | QDAC-II, OPX (QUA from the emitted stage), Keysight scope, Keithley SMU; emulators; one conformance suite; vendor SDKs as extras | 0006, 0041, 0043, 0063, 0065 |
| `qdt-lab` experiment | `SweepDefinition` → `ExecutionPlan` → emitted program → executor → Dataset stream → recorder | 0019, 0047, 0060, 0066–0070 |
| `qdt-lab` stream | The frozen Dataset wire: envelope-only chunks, region addressing, Arrow payloads | 0009, 0010, 0015 |
| `qdt-sim` | Constant-interaction double dot with a biased-SET sensor and clocked noise, behind the protocols | 0020, 0030 |
| `qdt-registry` | Local SQLite cache and payload store first, sync to Postgres; append-only; the only DB access | 0024–0026, 0050 |
| `qdt-analysis` | Curated pure methods with standard errors | 0029, 0031, 0045, 0046, 0062 |
| `qdt-tuning` | Calibration nodes with decision rules and input bindings; `TuneUp` runs them in order | 0048–0050, 0052 |
| `qdt-server` | Composition root: FastAPI over schema objects; serves Flight Deck; one stand per process | 0032, 0034, 0053, 0057 |
| `apps/flightdeck` | Widget workspace over a shared store; WebGL2 with a CPU reference; generated TS types | 0012, 0013, 0054–0059, 0061 |
| `qdt-telemetry`, `qdt-frameworks` | Skeletons for Steps 7 and 8 | 0051 |

**How the parts talk.** Commands and queries: browser → server REST; bodies are schema objects. Data:
executor → stream server → WebSocket → Flight Deck's store → renderers, addressed by coordinate region.
Records: recorder → registry cache → `sync()` → Postgres and payload store; replay uses the live wire.
Instruments: executor → protocol → driver → transport; only the emitter speaks a vendor language.

**Restrictions and their reasons.**

| Rule | Engineering reason |
|---|---|
| 1. `qdt-schemas` imports nothing from qdt | The contract must be the root of the dependency tree |
| 2–3. Schema objects through public APIs | Packages can move to another process or language without hidden coupling |
| 4. Only `qdt-registry` opens a database | One owner for DDL, migrations, roles and the cache; everything else tests without Postgres |
| 5. `qdt-analysis` is pure | Results reproducible from inputs, runnable anywhere |
| 6. `qdt-frameworks` holds no instance data | Governance renders from data; no second copy |
| 7. Provenance | The repo is public; site specifics live internally |
| 8. Flight Deck never knows the instrument | Live, replay, simulated and stored data share one path |
| Frozen slices, `schema_version`, migrations | Records written today load years from now |
| Extras, lockstep versions, generated TS types | Vendor pins can't break the core; the UI can't drift from the API |
| Test ladder; L3 never an exit | CI proves logic, the bench proves instruments, the fridge confirms |
| `PLANNED_BY`; work traces to the plan (ADR 0071) | Hardware time and agent sessions stay on the plan |

**Real versus not.** Proven on the bench: four drivers, L1 loopbacks, L2-1…L2-6. Simulator only: the
tune-up (L3 waits for the first fridge session). Single-machine assumptions in code: no auth, one stand per
server, limits and queue in the browser (#78, #79), per-request backends (#75), local payload path.
Proposed: 0074, 0075, 0076, 0077.

**Pressure points.** `qdt-server` depends on nearly everything (right for a composition root; keep logic
out). Seventy-nine ADRs need a map before the index. The stream's second port. `QueuedRun` (0075) should
seed `Job` (0076), not parallel it.

## 2. Roadmap

Steps 0–6b are done and everything runs on one machine; Step 6c (lab deployment) is next.

| Demo (Step 6c) | What someone sees | Rows |
|---|---|---|
| A. Registry on the network | Records browsed, scripted and fetched from any lab computer, measurement PC off, after an unattended reboot | R-1…R-4 |
| B. Orchestrated tasks | T-1…T-7 queued on the stand server, run unattended, confirmed on the scope | T-1…T-7 |
| C. Discovery and resilience | Discover lists the bench; one instrument off takes only its ports | D-1, D-2 |
| D. Flight Deck walkthrough | The task set from a second computer; workarounds become issues | W-1 |
| E. Hub (stretch) | Login, lease, job through one URL | ADR 0076 |

Missing: the human's acceptance of 0074, 0075, 0077; the lab PC OS (#114); the IT probe scope; `qdt-db`
set-up and the payload share. Code in dependency order: pool and discovery (0077); stand state and server
queue (0075); read server, payload GET, script read path, token (0074); milestone fixes (#76, #77, #112,
#114); the three bench test files. Outside 6c: the release mirror and the `jig` extraction.

## 3. Workflows

**Consumers.** Flight Deck (History, plot panes, analysis overlays); Python via `qdt_registry` +
`payload_hdf5`; other applications over HTTP (`exports/openapi.json`; the read server as the public contract
in 6c); replay down the live wire. Guarantees: versioned objects, upgrade on load, append-only hashed
records, results that name their inputs.

**Producers.** Measurement engineer through the widgets; script author through REST or
`qdt_lab.experiment`; analysis author (pure method + `MethodSpec` + injection–recovery); calibration author
(node proven on `qdt-sim`); instrument integrator (protocol + emulator + conformance + L1/L2 rows); external
systems (Step 7) through envelope adapters.

**Steering.** Goals and findings → chat → ADRs and step files → patch → sessions (`/session-start` →
issue → `/session-check` → `/session-end`) → bench and walkthrough reports → issues. Decisions in ADRs, scope
in step files, work in issues, handoff in STATUS, evidence in reports, numbers in analyses. Tightening
proposed: STATUS follows every landing; chat patches through PRs; issue templates for people; a map before
the index; one issue per session.

## 4. Open questions (settled in review; answers recorded below)

1. Audience of the guide pages.
2. One page or three in the repo.
3. Diagram kinds in section 1.
4. Dates on the roadmap.
5. Which agent-loop changes become an ADR.
6. Guide in the release mirror or workshop only.

### Answers
_(recorded after the human's review)_
