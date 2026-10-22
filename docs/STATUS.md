# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS: goal 1's first
slice is in L0 (deliverables 2 code half, 3, 4); the `qdt-db` runbook (deliverable 1) is written and awaits
its first run on the human's personal Windows PC. Steps 0–6 and 6b are DONE. Milestone `Deployment`.
**Branch:** `step-6c/goal-1-remote-registry` (PR against `main`; the human merges). Earlier today: #117
(the chat instance's ADRs 0073–0079) and #118 (ADR 0080, 0074 accepted) merged.
**Last session:** 2026-10-22 (session 27, continued), no bench.

## Done this session
- **Sync after every record and at start (ADR 0080).** `RunManager.sync`/`sync_later`: after a record is
  ingested (after the run's state is set) and once in the lifespan, in a thread, one at a time; without
  `QDT_REGISTRY_DSN` nothing is tried; unreachable → one warning (no DSN in it), the rows stay unsynced,
  the next success carries everything. The registry keeps its remote engine only once `_prepare` answered,
  so a server down at the first attempt still gets its tables and DDL check later. The server test suite
  clears the two env vars so a developer's server never receives test records.
- **The read server (ADR 0074, 0081).** `python -m qdt_server --read-only` / `Settings.read_only`: no
  backends, no stand, no `RunManager`; needs `QDT_REGISTRY_DSN` (reader role) and `QDT_PAYLOAD_STORE`.
  Every route that needs a stand or writes sits on an `APIRouter` included only on a stand server; replay
  stays. `GET /server` → `ServerInfo`; `GET /records/{id}/payload` streams the HDF5 bytes with
  `X-Content-SHA256` on both kinds. `openapi.json` and Flight Deck's `api.ts` regenerated.
- **Flight Deck against a read server:** `api.server()` at boot; only plot, empty and history registered;
  no Run cluster in the strip (absent), stand reads "registry"; the layout under `READ_ONLY_LAYOUT_KEY`.
  `e2e/readonly.test.ts`: a stand server measures and syncs, a read server serves it to a fresh Flight Deck
  with no command anywhere, History opens the record on the read server's stream.
- **The script read path (ADR 0081).** `Registry.devices(remote=)`, `payload_file`/`payload`/`output(remote=)`,
  `init_server()` and `python -m qdt_registry init`. `docs/tutorials/test_04_remote_read.py`: read A through
  `qdt_registry` with a reader DSN (a write as the reader is refused; no bytes without the share), read B
  over HTTP from a read server connected as the reader, hash-checked, arrays equal to the laptop's.
  Locally the reader is a SQLite file opened `mode=ro`; in CI it is Postgres with the real role.
- **`deploy/qdt-db/roles.sql`** (three roles, default privileges), run by CI against `qdt_test` before the
  suite, with `QDT_TEST_PG_READER_DSN`. **Not yet run against a real Postgres by the agent** (no Docker on
  this machine): this PR's CI run is its first; if `l0` fails there, that is where.
- **`deploy/qdt-db/README.md`:** the Windows runbook (native service, roles, `pg_hba`/firewall on a
  placeholder subnet, schema step, SMB share and UNC mount, the read server as a start-up task with `--ui`,
  the measurement PC's two variables, nightly dump + mirror, restore drill, the §6 smoke test that is the
  goal 1 demo, the human's checklist, the Postgres half of the tests without Docker). Closes #112, #114.
- **Docs:** ADR 0081 (what the slice settled); Step 6c L0 row reworded (replay stays), status IN PROGRESS;
  steps index; tutorials index. 476 Python tests (+6 Postgres-parametrized), 4 skipped; Flight Deck 142
  unit, 15 e2e. `check_all` green.

## In flight
- This PR awaits the human; its CI run is the first run of `roles.sql` on Postgres.

## Known broken
Open blockers: none (`gh issue list --label blocker`). Everything else: `gh issue list`.

## Next action
**Human (the demo, deliverable 1 and 2's share):** run `deploy/qdt-db/README.md` §1–§3 on the personal PC
and §4 on the laptop, then the §6 smoke test: a sweep on the laptop's Flight Deck, the record in the
desktop's Flight Deck (no Run button) and in a script (tutorial 04's pattern). Every step that needs a
workaround becomes an issue on `Deployment` (`found-by-human` is fine; label it `blocker` if it stops the
demo). Tick §7's checklist. **Agent, next session:** blockers from the demo first; otherwise deliverable 5
(the command token: a stand server bound off loopback refuses `POST`/`DELETE` without a bearer token from
its token file; loopback exempt; Flight Deck sends the token it was given), with the step file's L0 rows.
Branch `step-6c/<short-name>`.

## Direction recorded (human)
- **2026-10-22 (session 27):** the next focus is "set up the measurement database backend on my desktop PC
  and have it running … launch Flight Deck from my laptop with a simulated backend … take a measurement …
  view that measurement on my desktop computer by querying the database … with both an instance of Flight
  Deck on my desktop and through a Python script" (Step 6c goal 1, deliverables 1–4). "I think I want to
  accept ADR 0074" (ADR 0080). "For this demo, the database PC is not the real lab database PC. I want to
  demo this on my personal PC before trying to clone this repo on the lab PC." "I don't want to do manual
  sync — please add a sync attempt after every measurement, and if the database PC is not reachable
  default to the local cache." "Both my personal PC and the lab PC are Windows, for now. We can keep the
  desire to have the lab be a Linux box with documented reasons, but for now it's Windows."
- **2026-10-22 (chat instance, via PR #117):** ADRs 0078 (boundaries) and 0079 (general electronic test)
  proposed; Analyses 0005–0006 with the human's answers.
- **2026-10-19 (session 26):** ADR 0071, 0072, 0073 and the four deployment goals; the verbatim record is in
  `git show 5f2dd72:docs/STATUS.md`, § Direction recorded.
- Earlier direction (sessions ≤ 25): `git show b94193f:docs/STATUS.md`, § Direction recorded.

## Decisions pending
All are `decision` issues (`gh issue list --label decision`), plus Step 6c's remaining open decisions:
ADR 0075 (before deliverables 7–8), ADR 0077 (before 9–10), the LAN probe range (with deliverable 6).
How a script gets payload bytes is settled: HTTP from the read server (ADR 0081).
