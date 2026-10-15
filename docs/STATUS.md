# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 6 — Closed-loop tuning → `docs/steps/06-closed-loop-tuning.md` (IN PROGRESS, opened 2026-10-15).
**Branch:** `step-6/sensor-node` (PR against `main`; the human merges). PRs #25–#46 merged 2026-10-14/15.
**Last session:** 2026-10-15, Step 6 session 5 (not at the bench). **The third node, the tune-up's root**
(ADR 0052): `sensor-operating-point` runs the sensor's Coulomb diamonds (`detect_diamonds`, ADR 0030) and
parks the sensor gate `flank_offset_v` (20 mV) above the Coulomb peak nearest `near_v`; `charge-lattice`
holds that gate through `levels`, bound from the sensor node's `sg_operating_v` (ADR 0038's operating point
carried by ADR 0049's bindings). `TEMPLATES` take the stand's sensor gate (`SG`) and the server offers the
sensor node only when the stand has one; without it the charge lattice stands alone as before. **The
three-node tune-up completes on a cold-sensor scenario through the API and from the UI**: peak −0.0599 V
(model −0.06), period 0.248 (0.25), charging energy 1.00 meV, lever arm 4.1 meV/V; then the lattice at
SG = −0.04 V and residual cross ratios 0.001/−0.003; 0.9 s on the sim. Six `SimResult` fixtures reproduced
in CI. The flank offset is a parameter, not a measurement (the method does not estimate the peak width).

## Step 6 exit criteria (from the step file)
| Criterion | State |
|---|---|
| a multi-node tune-up runs unattended against the sim | ✔ three nodes (sensor → lattice → virtual gates), two kinds of binding, from `POST /tuneups` and from Flight Deck; outcomes in the registry |
| first L3 contact as confirmation, not discovery | not started (needs a fridge; the bench can confirm the two stability nodes once a second OPX pulse line is cabled; the sensor node needs `SG`, `bias` and `sensor` channels the bench stand lacks) |

## Done
- **Steps 0–5 DONE.** ADR 0001–0052 (0051 is a Step 7 decision taken ahead of its step). Frozen: `Dataset`
  (0015; v2 by 0031), protocols (0021), stand/activity/pulse (0022; amended additively by 0037, 0038, 0047,
  0049), identity/envelope/`qdt-hdf5-v1` (0028), modeling (0033; Step 6 objects beside it by 0048–0050),
  control (0036; amended additively by 0046; `TuneUp` beside it by 0050). Registry DDL v3 (0026, 0029, 0050).
- **Step 6 so far:** the modeling objects; `qdt-tuning` (pure: `nodes` + `TEMPLATES`, `decisions` with three
  rules, `bind`, `dag.order`); `run_node`, `run_tuneup`, `TuneUpManager`; the `sensor-operating-point`,
  `charge-lattice` and `virtual-lattice` nodes; virtual gates in the sweep; scenario realization and truth in
  `qdt-sim`; the tune-up API; Flight Deck's Tune-up section; `scripts/make_tuning_fixtures.py`.
- **Packages:** `qdt-schemas`, `qdt-lab`, `qdt-sim`, `qdt-registry`, `qdt-analysis`, `qdt-tuning`,
  `qdt-server`, `apps/flightdeck`.
- 393 Python tests (+5 Postgres-parametrized), 4 skipped, 34 hardware-only in `packages/`, 16
  hardware-only in `bench/`; Flight Deck 72 unit tests and 6 e2e.

## In flight
- Nothing uncommitted. PR for `step-6/sensor-node` awaits the human.

## Known broken / not yet real
- **`flank_offset_v` is a judgment, not an estimate** (ADR 0052): a `sensor_peak` curated method (width
  and slope of the Coulomb peak from a zero-bias cut or a sensor-gate sweep) is the successor and a rule
  `VERSION` bump. **The diamonds method needs a cold sensor** (ADR 0030): on the default warm scenario the
  root fails and the tune-up stops there, visibly.
- **`TuneUp` is not persisted; one tune-up at a time; stop between nodes; no parallel branches, retries or
  resume** (ADR 0050).
- **Flight Deck: no click-to-set yet; the sweep form does not expose couplings; the Tune-up section runs
  templates only.**
- **The bench has one OPX pulse line cabled and no `SG`/`bias`/`sensor` channels**, so neither the virtual
  pulse axis nor the sensor node can run there yet; the nodes are stand-agnostic.
- **`detect_transitions` reports `ok` on a noiseless, nearly constant map** (a degenerate lattice); a method
  fix is a `VERSION` bump (ADR 0029).
- **`SimScenario.model` overrides scalars only** (ADR 0048). **`InputBinding.target` is a string path**
  checked at bind time (ADR 0049).
- **QDAC-II (firmware 14-1.70), for QDevil:** filter setting changes nothing; LOW sense range reads ≈ 2 nA
  for any current; ch02 dead (`*RST` no cure); output impedance 50 Ω. **The 2450 autoranges to 10 nA at
  0 V.** Bench quirks in BENCH.md.
- Step 5 carry-overs, Step 6 open decisions: nothing in a sweep plays a waveform; a sweep leaves its last
  level; captures sequential, one channel each; no 3-D capture view; Flight Deck offers every method on
  every record; the trace view has no axes, labels or output curve.
- **The exponential's edge detector is a heuristic** (0046); **the plane fit is OLS** (0045). OPX input
  offset −1.7 mV not applied; OPX `drive` unsupported on the LF-FEM stage.
- **Serial numbers:** `bench_report.py` does not redact `*IDN?` serials (decision pending).
- **qm-qua deprecations:** the QUA config's `version` key; `job.halt` for `job.cancel`.
- Carried over: diamond estimator needs a cold sensor (ADR 0030); zero-clipping in the dot model (ADR
  0020); overlays in one colour; Postgres suite only in CI; `FINISH_LINE.md` TODO (human); Windows pnpm
  via `corepack pnpm`.
- `chat-2026-10-15-series.patch` sits untracked at the repo root (the human's upload; fully applied).

## Next action
**Human:**
1. Merge the PR.
2. Choose the next session: **click-to-set** (Flight Deck emits a set-level request, the one "up" edge of
   FINISH_LINE; a `POST /levels` that holds an operating point on the stand, or a one-point sweep), a
   **`sensor_peak` method** (makes the sensor operating point an estimate with an error and retires
   `flank_offset_v`), or a **bench confirmation** of the stability nodes (cable a second OPX pulse line;
   `qdt-server --stand`; `POST /tuneups` with `charge-lattice` and `virtual-lattice`).
3. The QDevil report; the Step 6 Open decisions still waiting (`PlayedWaveform`, sub-ms stepping, sense
   range declaration, rest level).

**Then (sessions):** the chosen item; a `tuneups` table when something reads tune-up history; resume and
parallel branches when a DAG needs them; Step 6's L3 confirmation when a fridge is available.

## Direction recorded (human)
- **2026-10-13:** web app end state. Curated analyses only. The control path came before the drivers
  (ADR 0031, 0032).
- **2026-10-14:** a chop's difference is recorded (0037); additive changes without a version bump are
  accepted (0037); the operating point comes before Step 5 (0038); wall-clock CI gates are advisory
  (0039); no surrogate DUT (0040); drivers first, simple; fits later (0041); bench reports write
  themselves (0042); USB serial counts for the QDAC-II (0043); drivers are recreated here rather than
  adapted from QCoDeS (discussion, no ADR); the OPX input constants are measured, not assumed (0044);
  the combiner board stands in for the bias tee and is characterised by a probe before it is used
  (Probe 03); the plane fit is written ahead of the sink decision.
- **2026-10-14, tabled:** Flight Deck should visualise time-series data (scope records first). A renderer,
  not a schema change. Partly done 2026-10-15 (record traces draw as traces with markers).
- **2026-10-15:** the scope is L2-1's sink; waveform capture is a server feature (ADR 0047); how fast the
  QDAC can be stepped matters for untriggered sweeps (Probe 04); finish the OPX conformance rows and L2-2
  before closing Step 5; Step 5 closes and Step 6 opens; the schema slice and the first node first (ADR
  0048); the second node is the virtual-gate stability diagram (ADR 0049); the persisted tune-up before a
  third node (ADR 0050); `qdt-telemetry` ingests, does not collect (ADR 0051, from a separate chat's
  patch); **"start the next session"**: the third node is the sensor operating point (ADR 0052).

## Decisions pending
- Next: click-to-set, a `sensor_peak` method, or a bench confirmation of the stability nodes.
- Step 6's Open decisions (step file): `PlayedWaveform`; sub-ms stepping; how a sense range is declared;
  a rest level at a sweep's end; the time-series view's remainder; the deferred physics.
- A `tuneups` table (when something reads tune-up history); resume and parallel branches.
- `detect_transitions` on a noiseless constant map (a method `VERSION` bump).
- `bench_report.py` and `*IDN?` serials; a default operating point per device; the dot model's
  zero-clipping; the diamond estimator on warm edges.
