# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS: what remains waits
on the bench and on the human's decisions. **Step 6d — the Phantom cutover** is DONE (pull request #151 merged,
ADR 0087, 0088). Steps 0–6 and 6b are DONE.
**Branch:** `step-6c/device-diagram` (pull request against `main`; the human merges).
**Last session:** 2026-10-29 (session 37), no bench.

## Done this session
- **The read server showed no scans after 2026-10-26: diagnosed, no code change.**
  - The Mac's payload share had dropped after a login and was never mounted again. Every upload failed, so
    17 scans waited in the Mac's local cache. The re-init on `qdt-db` was not the cause.
  - The human mounted the share again and confirmed that the scans now appear.
  - Filed #162: the Mac mounts the share only at login, and nothing shows that scans are waiting.
  - Filed #163: the mount helper's log holds the share password in plain text.
- **#164, the human's request: the Device widget (ADR 0089).**
  - New schema types `GateOutline` and `DeviceLayout` in `qdt_schemas.identity`. They are served and never
    stored, so they need no fixture or migration.
  - `qdt_sim.scenarios.layout` renames Phantom's knowable layout into them, with each gate on its stand
    channel. The `qdt-sim` source cap rose from 300 to 320 lines (now 311), and ADR 0089 says why.
  - `GET /device/layout` on the stand server returns it, or 404 for a stand without one (every real stand).
  - The Flight Deck widget "Device" draws the gates to scale as SVG, coloured by the sitting level, with a
    legend, a colour bar, a scale bar and a colormap menu. It polls and follows `levels:changed`.
  - Tests: schema and adapter tests, a server route test, 8 unit tests (`test/device.test.ts`), and an
    end-to-end test (`e2e/device.test.ts`). The guide has a new section on the widget, without a picture.
- **#165, the human's request: a setup page before a stand starts.** Filed as a `decision` issue with three
  questions and a recommendation. No code, because it would reverse ADR 0088's committed device files and
  change how a stand server starts.
- **#166 filed:** `e2e/control.test.ts` fails on `main` on a fast machine, because the run completes before
  the test sees "queued" or "running".
- Checks: `uv run pytest` 541 passed; `bash scripts/check_all.sh` green; Flight Deck unit tests 161 green;
  end-to-end tests 17 of 18 green, the failure being #166, which fails identically on `main`.

## In flight
- The pull request for `step-6c/device-diagram` awaits the human's merge; it is watched.
- #152 (blocker): the capture end-to-end test sometimes times out on CI waiting for "replaying". The
  diagnostic from #156 is on `main`; fix it from the next failure's message, with `Fixes #152`.
- The token is not yet in the runbook (Step 6c deliverable 13, the lab computer).
- Open UI findings: #150, #130, #122, #120, #119.

## Known broken
- #166: the control end-to-end test fails on a fast machine. #152: the capture end-to-end test is flaky on
  CI. Either can red a pull request's `flightdeck` job. Everything else: `gh issue list`.
- **A hazard for agents on the Mac measurement computer:** its shell sets `QDT_REGISTRY_DSN` and
  `QDT_PAYLOAD_STORE` to the lab registry. The Python server tests remove them (`conftest.py`), but the
  Flight Deck end-to-end tests spawn `qdt-server` with the shell's environment. Run them with
  `env -u QDT_REGISTRY_DSN -u QDT_PAYLOAD_STORE` until #167 is fixed. In session 37 a read-only check found no test records
  and no test stand states on the lab registry.

## Next action
**Agent, next session:** if a `flightdeck` job has failed with the #152 diagnostic, fix #152 first. Otherwise
go back to Step 6c: deliverable 11 (#76), then 14 (#112), then 15 (#114), on a branch `step-6c/<short-name>`.
**Human:**
- Merge this pull request (#164, the Device widget).
- Decide #165 (the setup page): which devices it offers, whether it is a launcher, and whether it lists real
  stands.
- Consider changing the payload share's password, since the mount log exposed it (#163).
- Triage #162, #163, #166 and #167.
- Decide #150 (click-to-set on a pulsed axis) and #147 (the two L2 oracles).
- Run `bench/test_l2_orchestration.py` on the bench with `QDT_STAND_FILE` set.
- Still open from earlier sessions:
  - Send plan §9 to IT.
  - Send the `ipconfig` output for #80.
  - Decide ADR 0077 before Step 6c deliverables 9 and 10.
  - Put the runbook on the lab computer.
  - Write the pre-deployment records.
  - Run restore drill #2 on 2026-10-31 (#133).

## Direction recorded (human)
- **2026-10-29 (session 37):** "I'm having some trouble with the read server not displaying the scans I take
  anymore. I've made sure to re init the registry on the database computer, but scans from today (10/29/26)
  still do not show." → diagnosis, #162, #163. Then: "ok now this is working."
- **2026-10-29 (session 37):** "I want a more streamlined experience for this. For example, when starting a
  stand, perhaps there should be a menu page where I can select parameters for a stand setup (including the
  use of phantom and what kind of device architecture). Additionally, I think we need a widget that draws an
  approximate (but to scale) diagram of the device that has the voltages on the gates (maybe with a color
  map)" → #164 (built, ADR 0089), #165 (decision).
- **2026-10-29 (session 36, continued):** "Yes the sweep should open with where the voltages are currently
  sitting. And yes make a script to regenerate the guide screenshots" → #157, #158.
- **2026-10-29 (session 36):** "Can you write some docs that render in the GitHub that explain how to start the
  simulated stand and control it with flight deck?" → `docs/guides/simulated-stand.md`.
- **2026-10-28 (session 35):** after #149 merged and was offered as next: "Start this" → #140 and #142.
- **2026-10-28 (session 34):** "Phantom cutover now. The tag 0.2.0 has been made" → ADR 0087, Step 6d, #141.
- Earlier direction, verbatim: `git show 56db293:docs/STATUS.md` (sessions 32–36), `git show 812d631:docs/STATUS.md`
  (sessions 30–31), `git show f748fe2:docs/STATUS.md` and `git show d7c7a01:docs/STATUS.md`, § Direction
  recorded, and `git show b94193f:docs/STATUS.md` (sessions ≤ 25).

## Decisions pending
- All `decision` issues (`gh issue list --label decision`), now including #165 (the setup page), #150
  (click-to-set on a pulsed axis) and #147 (the two L2 oracles).
- Step 6c's ADR 0077, needed before deliverables 9 and 10 (#80).
- Held by the human: the cadence of Phantom releases against qdt's pin (Analysis 0007, answer 3). Each pin
  bump is its own pull request (ADR 0087).
