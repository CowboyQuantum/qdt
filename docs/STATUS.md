# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.
> The backlog is not here: it is GitHub issues and milestones (ADR 0071).

**Current step:** **6c — Lab deployment** (`docs/steps/06c-lab-deployment.md`), IN PROGRESS: what remains waits
on the bench and on the human's decisions. **Step 6d — the Phantom cutover** is DONE (pull request #151 merged,
ADR 0087, 0088). Steps 0–6 and 6b are DONE.
**Branch:** `step-6c/batched-sense` (pull request against `main`; the human merges).
**Last session:** 2026-11-01 (session 41), no bench.

## Done this session
- **#179, the human's request: a simulated sweep reads a line at a time (ADR 0093).** The human's
  201 × 201 stability diagram took 69 s. A profile put 98 % of it inside Phantom's `Session.sense`,
  called once per pixel, and Phantom's cost is per call: one point per call 1.5 ms, a row per call 65 µs.
  Now a `BatchedLevelSense` protocol sits beside the frozen five, the executor reads a DC sweep's inner
  axis in one `sense_along` call when the inner channel, its companions and the sensed channel are one
  such backend, the simulated physics has an optional `sense_many` (Phantom from one call; None with
  dynamics on), and the sequence interpreter reads each line of a staged sweep in one batch when nothing
  is captured and every measure's dwell is fixed. The 201 × 201 map takes 3.0 s; a 96 × 96 staged one
  0.9 s; the tune-up fixtures regenerate in 20 s instead of 73 s. With noise off the values are the
  point-by-point ones to 12 digits; with noise on a batched sweep is another realisation of the same
  seed, so the noisy fixtures were regenerated (every node accepted, same accuracy). Tests in
  `test_simulated_instrument.py`, `test_experiment.py` and `test_device.py`. The adapter's line cap rose
  from 350 to 370 (360 lines).
- **Session 40, merged as pull request #178 (Phantom 0.6.0, ADR 0092):**
  - **The human's request: Phantom `v0.6.0` adopted (ADR 0092).** Phantom answered the two issues qdt filed
    from the human's observations on 0.4.0 (#69, #70) with `v0.5.0` and `v0.6.0` the same day. In 0.5.0 the
    barrier between the dots has one transmission, every gate's action on it is screened so a plunger moves
    it a quarter as much as `B_M`, and `B_M` keeps acting past the merge. In 0.6.0 each dot is a puddle that
    grows with its electrons, so the honeycomb's cells shrink towards high occupancy and the superdot front
    moves across occupancy with `B_M`. The pin moved from `v0.4.0` to `v0.6.0` (`9b1c059`) in a pull request
    of its own (ADR 0087).
    - Both device files were recompiled from their unchanged recipes (device-file format 7). The sensor's
      starting levels did not move. No source change in the adapter's physics path.
    - The stand's default stability window is now two separate dots across almost the whole window (1 %
      merged at the start, against 40 % on 0.4.0). `B_M` merges it from the upper right down: a fifth at
      0.24 V, three quarters at 0.30 V, all of it from 0.40 V; 0.14 V separates the dots everywhere. The
      transition along the plungers is about 100 mV wide (15 mV on 0.4.0). A test pins these shares.
    - **Phantom's truth lattice is stale (Phantom #75).** With the puddles the honeycomb at the operating point
      is 3/2 as dense as the compiled matrix `Device.truth` reports, and qdt's analysis reads the denser
      one. `qdt_sim.scenarios.lattice_truth` is now the slope of Phantom's gate-induced charge at the start,
      the one computed number in the adapter, to go back to a rename when Phantom's truth carries it. The
      adapter's line cap rose from 340 to 350 (347 lines).
    - **#176, a blocker found on the way, fixed:** a virtual gate's coupled companion moved from 0 V, not
      from the held operating point, so the `virtual-lattice` node swept dot 2 at about 12 electrons instead
      of 28, with the sensor far off its peak. On 0.4.0 nobody saw it because the lattice did not depend on
      the occupancy. Now the server keeps the held level for a companion, a companion that nothing holds
      moves from the stand's live setpoint, and `run_tuneup`/`run_node` take an operating point to inherit.
      The virtual lattice's residual went from 0.049 to 0.005. Regression tests in
      `packages/qdt-server/tests/test_operating_point.py` and the API tune-up test.
    - Fixtures regenerated. The noisy virtual-lattice scenario that 0.4.0 forced out is back: the noisy
      two-node chain is accepted for 8 of noise seeds 0–9, seed 1 among them. Bounds set to what the uneven
      honeycomb needs: the tune-up's `l_22` 1.5 % → 5 %, the analysis test's dot 2 2 % → 3 %; the straightening
      bound 0.015 → 0.01 and the tutorial's ratio 0.06 → 0.03 came back in. Each bound quotes its value.
    - The guide (`docs/guides/simulated-stand.md`) has new numbers throughout, a rewritten `B_M` section
      (0.24, 0.30, 0.40 and 0.14 V), a troubleshooting row for the uneven cells, and regenerated pictures.
      This covers #175's guide part.
    - Timings: a 48 × 48 stability diagram takes 3.7 s (2.7 s on 0.4.0), 26 s with dynamics (unchanged).
  - **Filed:** Phantom #75 (the truth lattice ignores the puddles), qdt #176 (fixed here), qdt #177
    (`detect_transitions` misreads dot 1's density by 35–40 % on noise seeds 6 and 7 of the analysis test's map).
  - Checks (session 41): `uv run pytest` 554 passed, 4 skipped, in 92 s (245 s before the batched reads). `bash scripts/check_all.sh` stops on
    Windows at the provenance check's match inside the git-ignored `.ruff_cache` and at `check_vocabulary`'s
    backslash paths (#137, #125); `check_bench_rows.py` fails to decode a file on Windows (#137). Every
    remaining check passes when run by hand. Flight Deck unit tests 161 of 161.

## In flight
- The pull request for `step-6c/batched-sense` awaits the human's merge; it is watched.
- The token is not yet in the runbook (Step 6c deliverable 13, the lab computer).
- Open UI findings: #152, #150, #130, #122, #120, #119.

## Known broken
- With `dynamics` on, stability diagrams are wrong where a row steps down by several electrons
  (Phantom #64, still open on 0.6.0). The option is off by default, and the guide says so.
- `detect_transitions` misreads dot 1 on two of ten noise seeds of the noisy 64 × 64 map (#177); the test
  keeps seeds 1 and 2.
- #152: the capture end-to-end test sometimes fails on CI waiting for "replaying". A rerun passes.
- #166: the control end-to-end test fails on a fast machine.
- **A hazard for agents on the Mac measurement computer:** its shell sets `QDT_REGISTRY_DSN` and
  `QDT_PAYLOAD_STORE` to the lab registry. The Python server tests remove them (`conftest.py`), but the
  Flight Deck end-to-end tests and the screenshot script spawn `qdt-server` with the shell's environment.
  Run them with `env -u QDT_REGISTRY_DSN -u QDT_PAYLOAD_STORE` until #167 is fixed.
- On Windows, `check_all.sh` needs the steps after `check_vocabulary` run by hand (#125, #137), the
  end-to-end tests need a fresh `pnpm build` and fail where a read server holds port 8700 (#135), and
  `pnpm screenshots` must be stopped after it writes its pictures (#160). Everything else: `gh issue list`.

## Next action
**Agent, next session:** fix #152 first, on a branch `step-6c/<short-name>`, with a regression test and
`Fixes #152`: where Flight Deck's strip writes a run's status into `#message`, a run that has already
completed must not replace a later message such as "replaying". Then go back to Step 6c: deliverable 11
(#76), then 14 (#112), then 15 (#114). When a Phantom release carries the truth lattice (#75) or fixes #64,
adopt it in a pull request of its own (ADR 0087) and return `lattice_truth` to a rename.
**Human:**
- Merge this pull request (#179, batched reads). Then restart the simulated stand
  (`uv run python -m qdt_server`; on the rehearsal computer with `--port 8701 --stream-port 8766`) and
  follow the guide's section *Merge and separate the dots with the middle barrier*: `B_M` at 0.24, 0.30,
  0.40 and 0.14 V, a stability diagram each time.
- Reopen #152 if it is still closed; the agent's attempt was refused by the permission check.
- Triage Phantom #75, #64 and #65, and qdt #170, #174, #177.
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
  - Run restore drill #2, due 2026-10-31 (#133).

## Direction recorded (human)
- **2026-11-01 (session 41):** "Can I ask what's limiting the runtime of a scan. 201x201 is kind of
  painfully long. check the last scan for the total runtime and provide a timing profile for it" → the
  profile, #179; then "let's address this now" → ADR 0093.
- **2026-11-01 (session 40):** "I want you to move to phantom v0.6.0. What does that entail before you go do
  it?" then "ok start this work" → ADR 0092, Phantom #75, qdt #176 (fixed), #177. Earlier the same day,
  on the 0.4.0 stand: "the dots did not fully merge at all" → Phantom #70's second comment, answered by 0.5.0.
- **2026-10-31 (session 39):** "I want you to address issue #169", then, told that #169 was already done
  by pull request #171 and that #172 asks for Phantom 0.4.0: "I did mean 172" → ADR 0091, Phantom #69.
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
- Earlier direction, verbatim: `git show d6dc8c0:docs/STATUS.md` (session 39), `git show 78fa1b3:docs/STATUS.md` (sessions 34–36), `git show 56db293:docs/STATUS.md`
  (sessions 32–36), `git show 812d631:docs/STATUS.md` (sessions 30–31), `git show f748fe2:docs/STATUS.md` and
  `git show d7c7a01:docs/STATUS.md`, § Direction recorded, and `git show b94193f:docs/STATUS.md` (sessions ≤ 25).

## Decisions pending
- All `decision` issues (`gh issue list --label decision`), including #165 (the setup page), #150
  (click-to-set on a pulsed axis) and #147 (the two L2 oracles).
- Whether a virtual gate's companion should follow the axis's offset from its origin rather than its
  value (ADR 0092 keeps ADR 0049's rule; the virtual-lattice window then sits one electron below the
  first node's on dot 2).
- Step 6c's ADR 0077, needed before deliverables 9 and 10 (#80).
- Held by the human: the cadence of Phantom releases against qdt's pin (Analysis 0007, answer 3). Each pin
  bump is its own pull request (ADR 0087).
