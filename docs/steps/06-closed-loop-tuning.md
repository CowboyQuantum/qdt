# Step 6 — Closed-loop tuning

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Calibration DAG nodes (experiment + analysis + decision) run unattended against `SimulatedDevice`, then are confirmed on hardware. Flight Deck gains gate-voltage navigation.

## Schema slice
`modeling.py`: `SimScenario`, `SimResult`, `CalibrationNode`.

## Deliverables
- DAG runner; nodes verified against sim before any L3 contact
- ~~DAPS forward model + bias study as sim scenarios + analysis routines~~ — **struck 2026-10-15 by the human ("let's strike the DAPS development for now")**; not a Step 6 deliverable; revisit by its own decision when wanted
- Flight Deck click-to-set (the one 'up' edge)

## L0 tests (CI)
- every DAG node passes against `SimulatedDevice` in CI; committed scenario outcomes reproduced

## L1 tests (bench loopback)
- none

## L2 tests (instrument-on-instrument)
- none

## Exit criteria
- a multi-node tune-up runs unattended against the sim
- first L3 contact as confirmation, not discovery

## Open decisions
Carried from Step 5, each with its evidence; an ADR closes each one.
- ~~A `PlayedWaveform` activity.~~ Closed by ADR 0060 (2026-10-16): the shot is the timeline. A `capture` op
  opens a scope window inside the shot; `step`/`ramp` on a sequencer line are the stimulus; there is no
  `PlayedWaveform`. A node that steps a DC level and records a scope response is a stepped axis with a
  shot of step + capture. Open after it: the sequencer-to-scope trigger line (the OPX slice) and a capture
  on the sequencer's own input.
- ~~**Sub-ms stepping.**~~ Closed by ADR 0064 (2026-10-16): the DAG's inner loop is a triggered DC step.
  `TriggeredLevelSource` beside the frozen five; `SweepAxis.stepping = "triggered"` for the innermost
  stepped axis, loaded as a QDAC-II list and advanced by the OPX's marker on `do2`; the program owns
  the axis. Probe 05 ran 2026-10-16 (ADR 0065): the scope acquires segmented by `:SINGle`, the QDAC-II
  list re-arms per trigger and restarts past its end, and the L2-4 staircase passes. Pacing became the
  plan's the same day (ADR 0066): the compiler decides from the stand, "auto" by default, and the Sweep
  widget shows the decision and offers the override. Open after it: reading all segments in one
  transfer; the OPX streaming a triggered run per row.
- ~~The sequencer-to-scope trigger line~~ (left open by ADR 0060) — closed by ADR 0063: the OPX runs a
  shot capture now, the scope triggering itself until its stand entry names a marker line
  (`trigger_from`); the executor drains the capture while the shots play.
- **How a sense range is declared** (channel map vs. inferred). The 2450 autoranges its current
  measurement to 10 nA at 0 V and then charges a cable at 10 nA; the QDAC-II's LOW range measures nothing
  on the bench unit (BENCH.md). L2-2 sets both over the drivers' transports. A `ChannelMap` field is the
  obvious home; an unattended node cannot set front panels.
- **A rest level at a sweep's end.** A sweep leaves its last level on the QDAC (ADR 0038 holds levels,
  never zeroes them). A DAG that chains nodes needs to say where a node leaves the device.
- **Flight Deck's time-series view remainder.** Axes and labels on the trace, the method list filtered
  by `applies_to`, an analysis output curve beside the trace (ADR 0046, 0047). A tune-up's DAG state
  display (FINISH_LINE.md) joins it as a rendered schema object.
- **Physics the DAG needs.** Tunnel coupling and transport through the double dot (bias triangles) are
  deferred Step 6 ADRs (ADR 0020, 0030); which nodes need them decides their order.
- **Default operating point per device** (not in ADR 0038); whether the diamond estimator should survive
  warm edges; the dot model's zero-clipping (ADR 0020).
- ~~`flank_offset_v` is a judgment~~ — closed by ADR 0062: the `sensor-wing` node fits the peak's width and
  parks the gate on the fitted wing, with an error; alone it is a retune about the held level, and the
  server holds the gate where it decided.

## Status
DONE (opened 2026-10-15; closed 2026-10-15 on the human's word, session 8). Sessions below. Session 1: the file gained its
Open decisions from Step 5's bench record; nothing built yet. First task: the schema slice's shape
(`SimScenario`, `SimResult`, `CalibrationNode`, ADR 0033 reserved the names) and the first node, against
`SimulatedDevice` only (ADR 0007).
Session 2 (2026-10-15): **the schema slice and the first node** (ADR 0048). `SimScenario`, `DecisionRule`,
`CalibrationNode`, `NodeOutcome`, `SimResult` added beside the frozen three; `qdt-tuning` (pure: nodes as data,
curated decision rules with `RULES`/`apply`); `qdt-sim` realizes a scenario (`device_for`, `lattice_truth`);
`qdt_server.tuning.run_node` runs one node through the user's run path and applies the rule. The
`charge-lattice` node (stability diagram → `detect_transitions` → `virtual_gates`) is accepted on the default
scenario: lattice within 0.6 % (diagonal) and 2.3 % (cross terms) of the model, virtual-gate matrix within
0.007; two `SimResult` fixtures committed and reproduced in CI. Next: the DAG runner over `depends_on`, a second
node that consumes the first's outputs, outcomes persisted, Flight Deck's DAG state display.
Session 3 (2026-10-15): **the DAG edge** (ADR 0049; the human chose the virtual-gate node over the diamonds).
`SweepAxis.couplings` makes a stepped axis a virtual gate (companions move from their held level or 0; compile
resolves them, the executor sets them with the axis); the inner pulse axis uses `Affine.scale`. `InputBinding`
on `CalibrationNode.inputs` and `qdt_tuning.bind` carry an upstream node's outputs into a definition by path.
`virtual_gates` also outputs the compensation coefficients `c_21`, `c_12`; the new rule `straightened` accepts
axis-aligned transitions. The second node, `virtual-lattice`, runs after `charge-lattice` through
`run_tuneup` (nodes in order, inputs bound, stop at the first non-accepted) and is accepted on both scenarios:
residual cross ratios −0.008/−0.004 (noisy) and −0.003/+0.007 (quiet), down from 0.21 in real gates. Next:
a persisted `TuneUp` lifecycle object with a topological sort, `POST /tuneups`, Flight Deck's DAG display.
Session 4 (2026-10-15): **the persisted tune-up** (ADR 0050). `TuneUp` (control slice) is the lifecycle: nodes in
topological order (`qdt_tuning.order`), outcomes so far, queued → running → completed | stopped | failed.
`NodeOutcome` is persisted (`tuning_outcomes`, DDL v3, synced). `TuneUpManager` runs each node's sweep through
the `RunManager` (live on the stream), then the method, the rule and `add_outcome`; `GET /nodes`, `POST /tuneups`,
`GET /tuneups[/{id}]`, `POST /tuneups/{id}/stop`, `GET /outcomes`. Flight Deck's Tune-up section lists the
nodes, starts a tune-up and renders the DAG state (FINISH_LINE). The two-node tune-up completes unattended
through the API and from the UI on the simulator. Left: a `tuneups` table, parallel branches, resume; the
third node; click-to-set.
Session 5 (2026-10-15): **the third node, the root** (ADR 0052): `sensor-operating-point` reads the sensor's
Coulomb diamonds (`detect_diamonds`, ADR 0030) and parks the sensor gate `flank_offset_v` above the peak nearest
`near_v`; `charge-lattice` holds that gate through `levels`, bound from the sensor node's `sg_operating_v`.
`TEMPLATES` take the stand's sensor gate; the simulated stand offers three nodes. On a cold-sensor scenario the
three-node tune-up completes through the API and from the UI: peak −0.0599 V (model −0.06), period 0.248
(0.25), then the lattice at SG = −0.04 V and residuals 0.001/−0.003. Left: a `sensor_peak` method for the
flank (the offset is a parameter today); click-to-set; a bench confirmation.
Session 6 (2026-10-15): **click-to-set** (ADR 0053), the deliverable and FINISH_LINE's one "up" edge. The server holds
the stand's operating point (`GET/POST/DELETE /levels`): set now on the backends, merged into every sweep it compiles
or runs for the channels the sweep does not touch, so records carry it; tune-up nodes inherit it. Flight Deck: a
click on the map yields the point under it (`pointAt`), the panel offers it as levels for the stand's DC channels
(`setpointFor`), shows what is held, releases it. e2e: click, set, held, released. Closes the pending default
operating point decision. Left: axis → channel from the record's definition for axes not named after gates.
Session 7 (2026-10-15): the human struck the DAPS forward model and bias study from this step. With that, every
listed deliverable is done (DAG runner, three nodes verified against the sim, click-to-set) and the first exit
criterion is met; the second (an L3 confirmation) waits for a fridge. Whether the step closes now is the human's.
Session 8 (2026-10-15): **closed.** The human: "let's put off L3 and close step 6." Every listed deliverable is done
and the first exit criterion is met on the simulator. The second, "first L3 contact as confirmation, not discovery",
is deferred, not waived: plan §7.1 says L3 is never a step's exit criterion, and the repo has no fridge yet. It is the
first fridge task, tracked in `STATUS.md` until a fridge session runs the three-node tune-up (ADR 0048–0050, 0052) on
a real device and confirms what the sim showed. Carried out of this step unresolved: the Open decisions above, the
`sensor_peak` method, a bench confirmation of the stability nodes, `PlayedWaveform`, the `tuneups` and `stand_state`
tables, resume and parallel branches. The DAPS study stays struck. Next: Step 6b (spec merged, ADR 0054 proposed) or
Step 7 (gated by manager sign-off), the human's choice.
