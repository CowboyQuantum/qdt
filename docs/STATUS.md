# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS: what remains waits
on the bench and on the human's decisions. **Step 6d — the Phantom cutover** is DONE (pull request #151 merged,
ADR 0087, 0088). Steps 0–6 and 6b are DONE.
**Branch:** `step-6c/phantom-0.3.0` (pull request against `main`; the human merges).
**Last session:** 2026-10-31 (session 38), no bench.

## Done this session
- **#169, the human's request: Phantom `v0.3.0` adopted (ADR 0090).** The pin moved from `v0.2.0` to
  `v0.3.0` (`6920f19`) in a pull request of its own, as ADR 0087 requires.
  - Both device files were recompiled with the four new gates: the sensor barriers `SB_L` and `SB_R`, and
    the sensor bath gates `SR_L` and `SR_R`. Device a (seed 2) keeps Phantom's reference point. Device b
    (seed 5) needed its own sensor barriers, 0.375 V and 0.425 V, because at the reference point its
    sensor is dead.
  - A fresh stand starts `SG` at a committed level, `qdt_sim.scenarios.SENSOR_SET_V`, through
    `scenarios.start`. The level sits 10 mV below the wing of the broadened peak a period above
    Phantom's set point, where a stability diagram reads well. `make_sim_devices.py` prints it and its
    `--check` holds it, like the hashes.
  - The tune-up windows were re-sized for a 35 mV sensor period and a 9 meV charging energy. The sensor
    node gained a bias window, `bias_v`. The lattice nodes gained `sensor_offset_v`, so they read the
    sensor 10 mV below the wing that the sensor-wing node finds.
  - The new run option `dynamics`, off by default, turns Phantom's charge dynamics on. Flight Deck's
    Sweep and Tune-up widgets show it in their default options.
  - The fixtures were regenerated. The noisy tune-up bounds widened, and each widened bound quotes the
    value that needed it. The quiet scenarios stay inside the old bounds.
  - The guide (`docs/guides/simulated-stand.md`) and its pictures were updated through `pnpm screenshots`.
    The guide now sets `threshold_rel` to 0.1 for the transitions overlays.
- **Phantom issues filed:**
  - Phantom #64 (bug): with dynamics, a dot that must lose two or more electrons at once keeps one too
    many. A stability diagram with dynamics on is wrong over much of the map until that is fixed.
  - Phantom #65 (backlog): recompiling at the sensor set point moves the set point again.
- **qdt #170 filed (backlog):** after a tune-up the stand holds `SG` at the wing, 10 mV above where the
  lattice nodes read it.
- Checks: `uv run pytest` 543 passed; `bash scripts/check_all.sh` green; Flight Deck unit tests 161
  green; end-to-end tests 17 of 18 green, the failure being #166, which fails identically on `main`.

## In flight
- The pull request for `step-6c/phantom-0.3.0` awaits the human's merge; it is watched.
- #152 (blocker): the capture end-to-end test sometimes times out on CI waiting for "replaying". The
  diagnostic from #156 is on `main`; fix it from the next failure's message, with `Fixes #152`.
- The token is not yet in the runbook (Step 6c deliverable 13, the lab computer).
- Open UI findings: #150, #130, #122, #120, #119.

## Known broken
- With `dynamics` on, stability diagrams are wrong where a row steps down by several electrons
  (Phantom #64). The option is off by default, and the guide says so.
- #166: the control end-to-end test fails on a fast machine. #152: the capture end-to-end test is flaky on
  CI. Either can red a pull request's `flightdeck` job. Everything else: `gh issue list`.
- **A hazard for agents on the Mac measurement computer:** its shell sets `QDT_REGISTRY_DSN` and
  `QDT_PAYLOAD_STORE` to the lab registry. The Python server tests remove them (`conftest.py`), but the
  Flight Deck end-to-end tests and the screenshot script spawn `qdt-server` with the shell's environment.
  Run them with `env -u QDT_REGISTRY_DSN -u QDT_PAYLOAD_STORE` until #167 is fixed.

## Next action
**Agent, next session:** if a `flightdeck` job has failed with the #152 diagnostic, fix #152 first. When a
Phantom release fixes #64, adopt it in a pull request of its own (ADR 0087) and check a stability diagram
with dynamics on. Otherwise go back to Step 6c: deliverable 11 (#76), then 14 (#112), then 15 (#114), on a
branch `step-6c/<short-name>`.
**Human:**
- Merge this pull request (#169, Phantom 0.3.0). Then restart the simulated stand
  (`uv run python -m qdt_server`) and try the new gates and `"dynamics": true` in Flight Deck.
- Triage Phantom #64 and #65, and qdt #170.
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
- **2026-10-31 (session 38):** "ok I've made some changes to phantom and there is now a 0.3.0 tag an
  release. can you make the necessary changes in order for me to test this in flight deck?" → #169,
  ADR 0090, Phantom #64 and #65, #170.
- **2026-10-30 (session 37, continued):** "I want better charge dynamics to be simulated for the charge
  sensor as well as gates to modulate those dynamics, meaning the tunnel barriers into the charge sensor
  dot, as well as the baths that the sensor dot couples to." → Phantom #53, #54, qdt #169. Then: "let's
  troubleshoot how to give you the ability to make issues in phantom."
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
