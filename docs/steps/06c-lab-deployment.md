# Step 6c — Lab deployment

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.
> Inserted before Step 7 by ADR 0073. Milestone `Deployment` (issues #75–#80 and those added to it).
> Design: ADR 0074 (registry and control path on the lab network), ADR 0075 (stand state and the run
> queue on the server), ADR 0077 (instruments are discovered), ADR 0076 (measurement hub, stretch). Host runbook: Analysis 0003.
> ADR 0074 accepted and amended by ADR 0080 (2026-10-22): sync after every record, goal 1 rehearsed on a
> personal Windows PC first.
> The repo and its issues are public (rule 7): `qdt-db`, `<stand-host>`, `<lab-subnet>` and the like are
> placeholders; real names, addresses and credentials never appear here.

## Goal
The human's four goals (2026-10-19):
1. The registry on a database PC (`qdt-db`), readable from any networked computer as well as the
   measurement PC: Flight Deck, a Python script with the address and credentials, any schema-aware
   application.
2. Orchestration of an enumerated set of measurement tasks, validated on the bench through the scope.
3. Measurement parameters and scan analysis through Flight Deck, to discover missing features.
4. Stretch: jobs submitted to the lab PC and routed to a fridge. Designed (ADR 0076); not an exit
   criterion — routing to a fridge is L3.

## Schema slice
`operations.py`: `ChannelLimit`, `StandState`, `QueuedRun` (ADR 0075); `InstrumentPort`, `InventoryEntry`,
`StandVersion` (ADR 0077). Every field with `description=`.
Frozen at exit with an ADR.

## Deliverables
**Goal 1 — the registry on `qdt-db`**
1. `qdt-db` initialised per Analysis 0003 §8: Postgres as a service that starts with the machine, roles
   `qdt_admin`/`qdt_writer`/`qdt_reader` (ADR 0074), `pg_hba` and firewall scoped to `<lab-subnet>`,
   nightly dump to a second disk, one restore drill. `deploy/qdt-db/README.md` is the runbook (no Docker).
   The host is Windows for now: Postgres as a native service, never inside WSL2 (Analysis 0003 §4; ADR 0080).
   Rehearsed first on a personal PC standing in as `qdt-db`, with a laptop as the measurement PC and a
   simulated stand; the lab PC is a second run of the same runbook (ADR 0080). Placeholder names only.
2. The payload share on `qdt-db` (SMB), mounted by the stand server as `QDT_PAYLOAD_STORE` and surviving
   reboots. The stand server syncs after every record it ingests and once at start; when `qdt-db` or the
   share is unreachable the record stays in the cache, the run's outcome is unchanged, and the next
   successful sync carries everything missed (ADR 0080). No timer. A read-only server never syncs.
3. `qdt-server --read-only`: no backends, no command routes; `GET /records/{id}/payload` with SHA-256;
   the OpenAPI document published with the docs as the read contract. Runs on `qdt-db` as a service.
4. A read path for scripts through `qdt_registry` with the reader role (a reader mode if the client reads
   only its local cache today), shown by a tutorial that is a test (`docs/tutorials/`).
5. Command token: a stand server bound off loopback refuses `POST`/`DELETE` without a bearer token from its
   token file; Flight Deck sends the token it was given and hides commands on a read-only server.
6. The plan §9 IT checklist rewritten from Analysis 0003 and this step (one host `qdt-db`, 5432 from the
   lab subnet, the read server's port from the office subnet, the share, no Docker) and sent.

**Goal 2 — orchestration**
7. The `operations.py` slice; `StandState` versions in the registry; the stand server enforces limits on
   levels and on compile (refuse, never clamp) and re-applies the held point after a restart only on
   confirmation (ADR 0075).
8. The run queue in the stand server: persisted, ordered, reorder/remove while queued, abort while running;
   Flight Deck's queue, Levels and Virtual gates widgets read and write it there (ADR 0075; #78, #79).
9. Instruments are discovered (ADR 0077; #75, #80): per-transport discoverers (VISA, mDNS, an opt-in probe of
   a configured range, the OPX's configured hosts), identity matching to driver factories, port declarations
   on every driver, and the no-write rule for discovery.
10. The instrument pool in the stand server (ADR 0077; #75): one connection and health state per instrument;
    an offline instrument takes down only its ports; polls never rebuild a backend. Bindings saved as stand
    versions (UI ↔ file ↔ registry); an Instruments widget with Discover → review → Save stand.
11. Stand files' `settle_s` audited against their sources before the T-rows run (#76).
12. Bench reports file themselves under this step (#77).

**Goal 3 — through Flight Deck**
13. Walkthrough W-1 (below) run from a second computer; what was missing filed as issues on `Deployment`.

**Housekeeping on the milestone**
14. A documented local Postgres for the Postgres-parametrized tests, without Docker (#112).
15. Windows commands documented (`corepack pnpm`) for the lab PC (#114).

**Stretch (not an exit criterion) — goal 4**
16. ADR 0076's hub, beginning with its scheduling slice and stand registration; a job routed to the bench
    stand through the hub is an L2 demonstration, routing to a fridge is L3.

## L0 tests (CI)
- `--read-only`: no command route exists — every route that needs a stand or writes is absent (404/405:
  `/stand`, `/levels*`, `/sweeps/compile`, `/runs*`, `POST /records/{id}/results`, `/nodes`, `/tuneups*`)
  and the server's OpenAPI document omits them; `POST /stream/replay` stays, it commands nothing
  (ADR 0074 lists replay among what the read server serves; ADR 0081); `GET /server` says which kind
  answered; payload GET returns the bytes and a matching SHA-256; the read server never syncs.
- Token: a non-loopback request without a token is refused, with a token accepted; loopback exempt.
- Script read path: the tutorial reads a record and its payload from an ephemeral Postgres with the reader
  role and fails to write.
- Sync after ingest (ADR 0080): with the server unreachable a run completes and its record is in the
  cache, unsynced; with the server reachable again the next ingest uploads every unsynced record and
  payload; the sync runs after the run's state is set; a read-only server never syncs.
- `StandState`: versions round-trip; the latest is in force; a level and a compiled sweep beyond a limit
  are refused against the simulated stand; the held point is not re-applied without confirmation.
- Queue: order holds through reorder, remove and abort; a queued entry survives a server restart; one
  run at a time.
- Flight Deck e2e: the queue widget reflects server order; commands are absent against a read-only server.
- Discovery on emulators: candidates identified and matched; ports declared; no output written during
  discovery; a factory that raises leaves the pool's other instruments usable and polls do not rebuild;
  a compile using an offline port is refused; a binding saved in the widget equals the exported file and
  the registry's latest stand version.

## L1 tests (bench loopback)
`bench/test_l1_remote_read.py` (`PLANNED_BY = ("docs/steps/06c-lab-deployment.md",)`), run from a computer
that is not the measurement PC, with the registry on `qdt-db`:
- **R-1 remote read:** the record T-3 wrote is listed by the read server, its payload fetched over HTTP
  with a matching SHA-256, and read by a script through `qdt_registry` with the reader role.
- **R-2 measurement PC off:** with the stand server stopped, R-1 passes.
- **R-3 after a reboot:** `qdt-db` rebooted and left alone; R-1 passes (Analysis 0003 §8 step 4).
- **R-4 commands need a token:** a command to the stand server from this computer without a token is
  refused and changes nothing on the scope.

`bench/test_l1_discovery.py` (`PLANNED_BY = ("docs/steps/06c-lab-deployment.md",)`), on the bench:
- **D-1 discover:** discovery lists every bench instrument with its ports; the scope's reading of the QDAC
  channel is unchanged by discovery (nothing written).
- **D-2 one instrument off:** with the SMU powered off, discovery marks it offline, its ports unavailable, and
  T-1 passes on the QDAC; powered on again, the pool reconnects without a server restart.

## L2 tests (instrument-on-instrument)
`bench/test_l2_orchestration.py` (`PLANNED_BY = ("docs/steps/06c-lab-deployment.md",)`). Every row is
submitted as a queue entry to `qdt-server --stand` and run by the server; the scope is the sink; oracles
reuse the proven rows of `docs/BENCH.md` and compute thresholds from datasheets, never site tolerances.
- **T-1 hold a level:** QDAC ch01 held at 0, ±0.5, ±1.5 V → scope ch (DC, 1 MΩ). Oracle: the L1 loopback
  row's (scope mean against setpoint). Then the stand server restarts; the held point is offered, confirmed,
  and the scope reads it again.
- **T-2 limits refuse:** with `StandState` limiting ch01 below 1.5 V, a level and a compiled sweep that
  exceed it are refused. Oracle: the server's refusal, and the scope's mean unchanged from T-1's last level.
- **T-3 host-stepped staircase:** P1 −1 … +1 V in 5 points, host stepped, one scope capture per point.
  Oracle: L2-4's (plane fit `slope_row` 1 within the scope's gain accuracy; every row present).
- **T-4 triggered staircase:** L2-4 as a queue entry. Oracle: L2-4's.
- **T-5 DC + pulse:** L2-1's capture sweep as a queue entry. Oracle: L2-1's.
- **T-6 two lines in one shot:** L2-6 as a queue entry. Oracle: L2-6's.
- **T-7 the queue as a whole:** T-3 … T-6 submitted together from one desk; one entry reordered and one
  removed before it starts; one aborted while running. Oracle: records reach the registry in the final queue
  order; the aborted entry ends `aborted` with no record; the removed entry never runs; the scope reads the
  held point afterwards.

**W-1 Flight Deck walkthrough** (manual, goal 3): from a second computer, T-1 and T-3 … T-7 set up in the
Sweep, Pulse, Levels and Virtual gates widgets, run through the queue, and one curated analysis run on
each record from History. The dated report lists every step that needed a workaround; each becomes an issue.

## Exit criteria
- Every L0 row above green in CI.
- R-1 … R-4, D-1, D-2 and T-1 … T-7 pass on the bench with the registry on `qdt-db`, recorded in a dated report
  (`bench/reports/<date>-step6c.md`).
- W-1 run, its dated report committed, its findings filed as issues on `Deployment`.
- The `operations.py` slice frozen by an ADR.
- (Goal 4 is not an exit criterion; L3 never is.)

## Open decisions
Each closes by an ADR or by the human's decision recorded on its issue.
- **Settled 2026-10-22 (ADR 0080):** ADR 0074 accepted — read server, HTTP read contract, three roles,
  payloads on the share for stand servers and HTTP for every reader (HTTP upload waits for the hub),
  credentials in per-machine environment, command token. Still open: accept or amend **ADR 0075**
  (stand state, server queue) before deliverables 7–8.
- Where the run queue lives (#78): ADR 0075 proposes the stand server.
- Where limits, couplings and the held point live (#79): ADR 0075 proposes versioned `StandState`.
- Accept or amend **ADR 0077** (instruments are discovered) before deliverables 9–10; it closes #75 and,
  by binding to identity rather than address, #80 (DHCP reservations stay good practice, not a requirement).
- The instrument range the LAN probe may touch, and whether IT allows probing at all (mDNS alone otherwise):
  part of deliverable 6's IT ask.
- **Settled 2026-10-22 (ADR 0080):** the lab PC's OS (plan §12 #6, #114) is Windows for now, Postgres as a
  native service, not WSL2; the Linux preference and its reasons stay in Analysis 0003 §4, and the runbook
  gains a Linux section when a Linux host exists.
- A local Postgres test run without Docker (#112): deliverable 14.

## Status
IN PROGRESS (session 29, 2026-10-24). Goal 1 in L0: deliverable 2's code half (sync after every record and at
start), 3 (`--read-only`, `GET /server`, payload GET, Flight Deck without commands, e2e), 4 (reader DSN,
`init`, tutorial 04; payload bytes over HTTP — ADR 0081). **Deliverable 1's rehearsal is done:** the runbook
(`deploy/qdt-db/README.md`) ran end to end, Parts 1–10, on the human's personal PC as `qdt-db` with a Mac
laptop as the measurement PC (2026-10-23/24), nightly dump and payload mirror to a second disk, one restore
drill; `bench/reports/2026-10-24-step6c.md`. Deliverable 2's share is in place on that machine. R-1 … R-3
passed by hand through the runbook's Part 8; the scripted `bench/test_l1_remote_read.py` is still to write.
Remaining for deliverable 1: the second run of the same runbook on the lab PC (ADR 0080). Deliverables 5–16
not started.
