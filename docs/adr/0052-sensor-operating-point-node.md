# 0052 — The sensor operating point as the first node: Coulomb diamonds → a gate parked on a peak's flank, held by the stability nodes through `levels`

**Status:** Accepted
**Date:** 2026-10-15
**Step:** 6 (extends ADR 0048–0050; uses ADR 0030's diamonds method and ADR 0038's operating point)

## Context
After ADR 0050 the tune-up had two nodes, both about the dots' gates. Nothing decided where the charge
sensor itself should sit, and the stability nodes read the sensor wherever the sweep left its gate. The
human chose a third node over click-to-set and a bench confirmation. The candidates were the sensor's
Coulomb diamonds (a different physics, ADR 0030's method, the sensor's operating point as output) or
another stability-based node; the diamonds give the tune-up its natural root.

What the diamonds method reports: the degeneracy points (Coulomb peaks, as `marker` annotations at zero
bias), the period, the charging energy and the lever arm. What it does not report: the peaks' width. On
the simulator the sensor's current changes fastest about one thermal width from a peak (0.65 width for
the default model: −0.0865 V against a peak at −0.06 V with a 40 mV width; −0.068 V with a 10 mV
width), so "a quarter period up the flank" would park the gate far out on the tail.

The operating point must reach the stability nodes. ADR 0038 made the operating point part of the sweep
(`SweepDefinition.levels`, set once and held), and ADR 0049 made node inputs bind into a definition by
path. The sensor gate's level is therefore a `FixedLevel` in the stability node's sweep, bound from the
sensor node's output.

## Decision
- A rule `sensor_operating_point(result, *, flank_offset_v=0.02, near_v=0.0)`: on an `ok` diamonds result
  with at least one degeneracy point and a positive period and charging energy, choose the peak nearest
  `near_v` and park the gate `flank_offset_v` above it. Outputs `sg_peak_v`, `sg_operating_v`, `period`,
  `charging_energy`, `lever_arm`. The offset is a parameter, not an estimate, because the method does not
  measure the width; it is set from the sensor's known thermal broadening (20 mV is half a width for the
  default model, two widths for a cold one).
- A node `sensor-operating-point`: the Coulomb diamonds sweep (`SG` × `bias`, `I_sensor` sensed; the
  sweep `qdt_sim.scenarios.diamonds` has, now stand-agnostic in `qdt_tuning.nodes.coulomb_diamonds`),
  read by `detect_diamonds` with its catalogue defaults, judged by the rule. No dependencies: the root.
- `charge_lattice(..., sensor_gate=...)`: with a sensor gate, the node holds it (`levels` with a
  `FixedLevel` at 0), depends on `sensor-operating-point`, and binds `sg_operating_v` into
  `levels.0.value`. Without one it is the standalone node of ADR 0048.
- `TEMPLATES` constructors take `(instrument, sensor_gate)`; the server passes the stand's `SG` channel
  when it has one and leaves the sensor node out when it does not. `GET /nodes` on the simulated stand
  offers three nodes; `POST /tuneups` with the three completes on a cold-sensor scenario.
- The simulator provides the truth (`qdt_sim.scenarios.sensor_truth`): the peak nearest a gate value, the
  period, the charging energy and the lever arm from the model's fields. Two new fixtures:
  `sensor_operating_point_cold` and `virtual_lattice_cold` (the three-node tune-up's last node).

## Consequences
- Easier: the tune-up has a root that sets the sensor up before anything reads it, and the dependency
  chain is three deep with two kinds of binding (a coupling coefficient, a held level). On the cold
  scenario: peak −0.0599 V (model −0.06), period 0.248 (0.25), charging energy 1.00 meV (1.00), lever arm
  4.1 meV/V (4.0); the stability nodes then run at SG = −0.04 V and straighten to residuals of 0.001 and
  −0.003.
- Harder: `flank_offset_v` is a judgment, not a measurement. A `sensor_peak` curated method (a 1-D cut of
  the diamonds record at zero bias, or a dedicated sensor-gate sweep, fitted for width and slope) would
  make the operating point an estimate with an error; it is the right successor and a `VERSION` bump of
  this rule when it comes.
- Harder: the diamonds method needs a cold sensor (ADR 0030); on the default warm scenario the root
  fails and the tune-up stops there, which is honest and visible in the DAG state.
- Harder: `charge-lattice` is two nodes in one constructor (standalone or dependent) under one id; a
  tune-up on a stand with `SG` always runs the sensor node first. The existing two-node fixtures stay
  valid because they build the standalone variant directly.
- Must now: a stand file that wants the sensor node names its sensor gate `SG` and has `bias` and
  `sensor` channels; the bench stand has none of the three today.

## Alternatives considered
- A quarter-period flank (`peak + period/4`) — rejected: on a thermally broadened peak that is the tail,
  not the flank; the simulator's numbers above show it.
- Estimating the width inside the rule from the result's edge slopes — rejected: the diamond edges'
  slopes are the lever arm, not the thermal width; the rule would be inventing an estimate.
- Carrying the operating point as a `SweepAxis` coupling or an `Affine` offset — rejected: it is a held
  level, which is exactly what ADR 0038's `levels` is for.
- Separate node ids for the standalone and the dependent charge lattice — rejected: `virtual-lattice`
  binds to `charge-lattice` by id, and the two variants decide the same quantities.
