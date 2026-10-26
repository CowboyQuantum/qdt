# CLAUDE.md — qdt (Quantum Dot Toolkit)

This file is standing law for every agent session. It is short on purpose.
It tells you the rules and where to look; it does not explain the project.
If you need to know *why*, read `docs/adr/`. If you need to know *what's next*, read `docs/STATUS.md`.

## Session protocol (mandatory)

**Start** — read, in this order, and nothing else until the task requires it:
1. this file
2. `docs/STATUS.md` — current step, what is done, in flight, broken, next action
3. the current step's file in `docs/steps/` (STATUS.md names it) — fixed headings: Goal, Schema slice, Deliverables, L0/L1/L2 tests, Exit criteria, Open decisions, Status
4. the nested `CLAUDE.md` of any package you will touch

Then restate the task in one sentence and confirm it matches STATUS.md's "next action".
If it does not, stop and say so — do not silently change the plan.

**During** — one branch per session (`step-N/<short-name>`). Commit small, conventional-commit messages scoped by package: `feat(qdt-lab): ...`, `test(qdt-schemas): ...`, `docs(adr): ...`.
Run `/session-check` before claiming anything is done.

**End** — before you stop:
1. CI-equivalent green locally: `uv run pytest` and `uv run scripts/check_all.sh`
2. rewrite `docs/STATUS.md` (rewrite, never append — history lives in git)
3. write an ADR for any decision a future session could reasonably ask "why?" about (`/adr`)
4. commit. A session that ends uncommitted did not happen.
5. push the branch and open a pull request against `main` with a review-focus list. The human merges from the PR (often from a phone); never push `main` yourself.

## Hard rules (violations fail CI; see `scripts/`)

1. `qdt-schemas` imports nothing from any other `qdt-*` package. Ever.
2. All other packages import `qdt-schemas`; cross-package use goes through public APIs only.
3. Inter-tool data exchange happens only through schema objects.
4. Database access happens only in `qdt-registry`. No other package opens a connection or writes SQL.
5. `qdt-analysis` is pure-functional: schema objects in, `AnalysisResult` out. No I/O, no registry dependency.
6. `qdt-frameworks` contains no instance data; renderers only.
7. Provenance: nothing in this repo names a real test stand, device lot, internal system, tolerance, or person. `scripts/provenance_check.sh` is the grep test. Site-specific content lives in the internal extension package, not here.
8. `apps/flightdeck` never imports an instrument driver and never knows which instrument produced a `Dataset`. It consumes the `Dataset` stream contract and, from Step 4b, the `qdt-server` request API (ADR 0032); it never holds an instrument or registry handle.

## Discipline

- **Test ladder is the exit criterion.** A step is done when L0 is in CI and green, L1/L2 pass as a scripted bench demo with a dated report in `bench/reports/`, the step's schema slice is frozen, and ADRs are written. L3 (fridge) is never an exit criterion. See plan §7.1.
- **Schema grows one slice per step.** Add a family in the step that first consumes it (plan §4.1). No DDL before Step 3. Two deliberate freezes: the `Dataset` stream contract (Step 1) and the capability protocols (Step 2) — each with an ADR; everything else evolves via ADRs. Every pydantic field has a `description=`; `scripts/check_descriptions.py` enforces it.
- **Schema change = one commit:** schema + every consumer + migration + tests.
- **Simulation-first (ADR 0007).** Steps 1–4 run entirely against `Simulated*` backends and `qdt-sim`'s `SimulatedDevice`. Real drivers are Step 5. Keep simulated backends honest: the conformance suite is the spec they must share with real hardware.
- **Dependency fences:** vendor SDKs are optional extras on `qdt-lab` (`[opx]`, `[qdac]`, `[keysight]`, `[smu]`), never core deps. Upper-bound only pydantic, numpy, sqlalchemy, xarray. `uv.lock` is truth; `uv lock --check` in CI. Workspace packages version in lockstep.
- **Simulation philosophy:** numpy/scipy/xarray; custom propagators; no QuTiP.
- **Work traces to the plan (ADR 0071).** Write code only for a deliverable or test row in the current step file, an accepted ADR, or an issue the human labelled `roadmap`/`blocker`. Anything else you notice (a bug, a gap, a bench idea, a pending decision) becomes a GitHub issue, not a fix: what you saw, how to reproduce it, where, which milestone; labels `found-by-agent` + `blocker`|`roadmap`|`backlog` (+ `bench`/`fridge`/`decision`). Only a `blocker` (stops the current step's exit) is fixed in-session, with a regression test and `Fixes #N`. Issues are public: rule 7 applies.
- **Hardware tests** live in `bench/`, marked `@pytest.mark.hardware`, excluded from CI. Run `uv run pytest bench/ -m hardware` from the bench and commit the report. Each declares `PLANNED_BY` (an accepted ADR or a step file that names it; `scripts/check_bench_rows.py`): write the row into the plan before the test.
- **Tutorials are tests.** `docs/tutorials/*.py` run in CI against simulated backends.
- **Docs are generated where possible** (mkdocs + mkdocstrings; schema docs from field descriptions; TS types from JSON Schema). Do not hand-write what can be generated.
- **Never** `DROP TABLE`, delete a migration, edit a merged ADR, or append to STATUS.md.

## Writing for the human (replies, STATUS, ADRs, runbooks, issues, pull requests)

Everything an agent writes is read by a person who did not watch the work and may be reading on a phone.
- Write complete, explicit sentences. A list item is a sentence that says what the thing is and why it
  matters, never a bare noun.
- Expand every acronym the first time it appears in a reply or a document, however common it seems:
  "Server Message Block (SMB)", "multicast Domain Name System (mDNS)", "Virtual Local Area Network (VLAN)".
- Do not compress ideas into comma-separated triplets of bare terms or commands, such as "reorder, remove,
  abort" or "mDNS, LXI, VISA". Give each item its own clause that says what it does.
- When the human corrects how something is written, record the correction here, not only in a session's
  memory, so every context inherits it.

## Commands

```
uv sync --all-packages --all-extras      # full dev install
uv run pytest                             # L0 suite (what CI runs)
uv run pytest bench/ -m hardware          # L1/L2, bench only
bash scripts/check_all.sh                 # provenance + descriptions + imports + vocabulary + lock + lint
uv run mkdocs serve                       # docs at localhost:8000
(cd apps/flightdeck && pnpm test)        # front end; run pnpm from apps/flightdeck so corepack picks the pinned version
uv run python -m qdt_lab.stream           # synthetic stream on ws://127.0.0.1:8765; then `pnpm dev` in apps/flightdeck
uv run python -m qdt_server               # control path: API on :8700 (/docs), stream on :8765, simulated backend (Step 4b)
```

## Where to look

| Need | Read |
|---|---|
| Why is it built this way | `docs/adr/` (numbered; read before proposing architecture changes) |
| The numbers behind a decision | `docs/analysis/` (analysis notes an ADR cites; no decisions live here) |
| One-off measurements that gate a freeze | `docs/probes/` (specs) and `bench/probes/` (scripts) |
| What is next | `docs/STATUS.md` |
| The backlog, bugs, bench ideas, pending decisions | GitHub issues and milestones (`gh issue list --milestone Deployment`; ADR 0071) |
| The current step's spec | `docs/steps/<NN-name>.md` (index: `docs/steps/README.md`) |
| The roadmap narrative and test ladder | `docs/DEVELOPMENT_PLAN.md` (§7.1 ladder, §7.2 index) |
| Flight Deck end-state constraints | `docs/FINISH_LINE.md` |
| Bench wiring, loopback map, L2 instrument-on-instrument | `docs/BENCH.md` |
| How to add an instrument driver | `packages/qdt-lab/CLAUDE.md` |
| How the UI talks to the backend | `packages/qdt-server/CLAUDE.md` (ADR 0032, 0034) |
| How to add/change a schema | `packages/qdt-schemas/CLAUDE.md` |
| Personal, uncommitted overrides | `CLAUDE.local.md` (gitignored) |
