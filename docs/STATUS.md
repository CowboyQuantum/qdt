# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`, ADR 0073), NOT STARTED in
code; its design ADRs are in `main` (0074 accepted and amended by 0080; 0075–0079 proposed). Steps 0–6 and
6b are DONE. Milestone `Deployment`.
**Branch:** `step-6c/accept-0074` (PR against `main`: ADR 0080, Step 6c amended, this file; the human merges).
PRs #116 (ADR 0072) and #117 (the chat instance's patch: ADRs 0073–0079, Step 6c, Analyses 0005–0006)
merged 2026-10-22. Every merged branch was deleted 2026-10-22; `origin/step-6/sweep-stepping` (PR #64,
closed unmerged) remains on purpose.
**Last session:** 2026-10-22 (session 27), no bench.

## Done this session
- **PR #117 unblocked:** CI failed only on ruff in the patch's two new scripts (`check_vocabulary.py`,
  `issues_generality.py`); fixed, green, merged by the human. The roadmap patch STATUS asked for is in.
- **ADR 0080 (accepted):** ADR 0074 accepted as written, amended twice at the human's direction: the stand
  server syncs after every record it ingests and once at start, falling back to its cache when `qdt-db` or
  the share is unreachable (no timer; catch-up by insert-if-absent; a read-only server never syncs); goal 1
  is rehearsed on a personal Windows PC standing in as `qdt-db` before the lab PC, with one runbook for both.
  The host is Windows for now (native Postgres service, SMB share); the Linux preference stays in Analysis
  0003 §4. The ADR also records why other applications read over HTTP and not SQL.
- **Step 6c amended:** deliverables 1–2 and the L0 list carry the sync and the Windows host; two open
  decisions (ADR 0074, the lab PC's OS) are marked settled.
- No code changed beyond the lint fix. 466 Python tests (+5 Postgres-parametrized), 4 skipped; Flight Deck
  unchanged. The stale `git am` state noted last session is gone.

## In flight
- This PR awaits the human.

## Known broken
Open blockers: none (`gh issue list --label blocker`). Everything else: `gh issue list`.

## Next action
**Step 6c, goal 1, deliverables 1–4, as a demo on the human's own machines:** a personal Windows desktop
as `qdt-db`, a laptop as the measurement PC running `qdt-server` on the simulated stand with Flight Deck.
The demo: take a measurement on the laptop; it reaches the desktop's Postgres by the automatic sync; read it
on the desktop both in Flight Deck (against `qdt-server --read-only`) and from a Python script. Branch
`step-6c/goal-1-<short-name>`. Order, each its own commit and each with its L0 rows from the step file:
1. **Deliverable 2's code half first** (it is the smallest and the demo needs it): after
   `self.registry.ingest` in `packages/qdt-server/src/qdt_server/runs.py` (the `_set(... "completed")`
   block), a `sync` in a thread that logs and swallows a failed connection; one more at the end of
   `create_app`'s lifespan setup in `app.py`. L0: unreachable → run completes, record in cache unsynced;
   reachable → next ingest uploads everything; the read-only server never syncs.
2. **Deliverable 3:** `--read-only` in `__main__.py`/`Settings`: no backends, no command routes
   (`POST`/`DELETE` 404/405), `GET /records/{id}/payload` with a SHA-256 header, reads through the registry
   with the reader DSN. Flight Deck hides commands when the server reports read-only (deliverable 5's UI
   half; the token itself can wait). L0 rows as in the step file.
3. **Deliverable 4:** `Registry.payload` for a record not in the local store (reader mode: fetch over HTTP
   from the read server, or read the share); `docs/tutorials/test_04_remote_read.py` against an ephemeral
   Postgres with the reader role, failing to write. Closes #112 on the way if a documented local Postgres
   without Docker falls out of it (deliverable 14).
4. **Deliverable 1:** `deploy/qdt-db/README.md` — the Windows runbook from Analysis 0003 §8: native Postgres
   service, database `qdt`, roles `qdt_admin`/`qdt_writer`/`qdt_reader`, `pg_hba` and firewall scoped to a
   placeholder subnet, the SMB share for `QDT_PAYLOAD_STORE`, nightly dump, restore drill, the smoke test
   (write on the laptop, read on the desktop). Placeholder names only (rule 7). The human runs it on the
   desktop; what the agent cannot verify from the laptop is listed as the human's checklist.
Then the human runs the demo; every step that needed a workaround becomes an issue on `Deployment`.
Not in scope for this demo: the command token (deliverable 5), the IT ask (6), goals 2–4.

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
- **2026-10-22 (chat instance, via PR #117):** ADRs 0078 (boundaries: clients over HTTP in their own repos,
  libraries inside qdt, nothing extracted now) and 0079 (general electronic test with a spin-qubit layer)
  proposed; Analyses 0005–0006 with the human's answers.
- **2026-10-19 (session 26):** ADR 0071 (work traces to the plan; findings become issues), ADR 0072 (no
  outside approval gate), ADR 0073 (deployment is Step 6c) and the four deployment goals; the verbatim
  record is in `git show 5f2dd72:docs/STATUS.md`, § Direction recorded.
- Earlier direction (sessions ≤ 25): `git show b94193f:docs/STATUS.md`, § Direction recorded.

## Decisions pending
All are `decision` issues (`gh issue list --label decision`), plus Step 6c's remaining open decisions:
ADR 0075 (before deliverables 7–8), ADR 0077 (before 9–10), the LAN probe range (with deliverable 6), and
how the script read path fetches payload bytes (HTTP from the read server, or the share; decided in
deliverable 4 with a line in its ADR or tutorial).
