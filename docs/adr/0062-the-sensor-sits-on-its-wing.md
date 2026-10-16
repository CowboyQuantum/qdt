# 0062 — The sensor sits on its fitted wing: a `sensor_peak` method, a `sensor-wing` node that is also a retune, the stand held where a node decides

**Status:** Accepted
**Date:** 2026-10-16
**Step:** Step 6 open decision (extends 0030, 0049, 0050, 0052, 0053)

## Context
ADR 0052 parked the sensor gate at "the Coulomb peak plus `flank_offset_v`", a typed 20 mV, because the
diamonds method does not measure a peak's width. The right place is where the sensor current changes
fastest with gate voltage: not the peak but its wing, the inflection of the thermally broadened line,
which sits at a fixed fraction of the width from the peak. On a real device the width is unknown in
advance and drifts; a typed offset is wrong in a way the tune-up cannot see. The human asked for the
analysis to sit the sensor on the wing naturally, and for that to serve a *retune*: after drift, put the
sensor back on its wing without re-measuring the diamonds.

## Decision
- **The lineshape.** At linear-response bias a sensor SET's current against its gate is
  `background + height · sech²((V − V_peak) / width)` (the derivative of a Fermi function; the
  simulator's model of ADR 0030 reduces to it). Its slope is largest at `V_peak ± atanh(1/√3) · width`
  (0.6585 widths), where it is `4/(3√3) · height / width`. These are constants of the lineshape, not
  judgments; the same two numbers give the simulator's truth.
- **A curated method, `qdt_analysis.sensor_peak.fit_sensor_peak`** (applies to a 1-D trace of current
  against the gate): finds the peak nearest the window's centre (or `near_v`), fits the line between the
  neighbouring minima, and reports `peak_v`, `width_v`, `height_a`, `background_a` with standard
  errors, `wing_v` on the `side` asked with its error propagated from the peak's and the width's,
  `sensitivity_a_per_v`, `r2`. Markers at the peak and the wing; the fitted curve as output.
- **A rule, `sensor_wing`** (version 1): accept an `ok` result with a positive width and height and a
  sensitivity above a floor; outputs `sg_peak_v`, `sg_width_v`, `sg_operating_v` (the wing),
  `sensitivity_a_per_v`. Nothing in it is typed.
- **A node, `sensor-wing`**: a short sweep of the sensor gate (±`span_v`, 101 points) at a held
  linear-response bias, read by the method, judged by the rule. After `sensor-operating-point` the
  window is centred on the diamonds' peak; `charge-lattice` now binds its sensor level from this node,
  so the chain is diamonds → wing → lattice → virtual lattice.
- **The same node is the retune.** Two additive changes to the modeling slice make that possible:
  `InputBinding` gains `scale`, `offset` (the target takes `scale · output + offset`: here the peak
  ± half a window) and `held` (a logical channel whose server-held level stands in for the upstream
  output when the upstream node is not in the tune-up); the DAG accepts an absent dependency when every
  binding from it has such a fallback. So `POST /tuneups` with `["sensor-wing"]` alone sweeps around
  the level the server holds for the sensor gate, refits the peak, and re-parks the gate.
- **The stand is held where a node decides.** `CalibrationNode.holds` (channel → output name): when
  the node is accepted, the `TuneUpManager` sets that output as the channel's held operating point
  (ADR 0053's `/levels`). `sensor-wing` holds the sensor gate at its wing. After a tune-up, or a retune,
  the sensor *is* on its wing for every sweep that follows, and the Levels widget shows it.
- `sensor-operating-point` and its rule are unchanged (the diamonds stay the root: they find the peak,
  the period and the lever arm); `flank_offset_v` is no longer what parks the gate.

## Consequences
- Easier: the operating point is an estimate with an error, checkable in the DAG state ("wing at
  −0.0534 ± 0.0004 V"); a drifted sensor is one node away from being re-parked; a sensitivity that comes
  out absurd is a visible rejection, not a silently mis-parked sensor.
- Harder: a retune needs a held level to centre on (the first tune-up, or a manual set, provides it; the
  direct `run_node`/`run_tuneup` paths have no stand state and refuse the fallback with a message); a
  retune that finds the wrong peak (drift of more than half a window) parks on the wrong peak, which the
  period from the diamonds could catch later.
- The `charge-lattice` fixtures on the cold scenario changed: the lattice now runs at the fitted wing
  (−0.0534 V for a 10 mV width) rather than at −0.04 V.

## Alternatives considered
- Keep `flank_offset_v` and let the user type the width — rejected: the width is measurable in one short
  sweep.
- A second node id for the retune — rejected: one node, two ways to centre it; the fallback is data on
  the binding, and the DAG rule is one line.
- Setting the operating point from the UI after a tune-up — rejected: the node decided it; a human
  copying a number is the error the tune-up exists to remove.
