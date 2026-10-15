# 0049 — Virtual gates as coupled axes (`SweepAxis.couplings`), node inputs bound from upstream outcomes (`InputBinding`), and the first tune-up runner

**Status:** Accepted
**Date:** 2026-10-15
**Step:** 6 (amends the activity slice frozen by ADR 0022, additively; extends ADR 0048's `CalibrationNode`)

## Context
The human chose the second node to be a stability diagram **in virtual gates** that consumes the first
node's matrix (over the sensor's Coulomb diamonds), because it shows the DAG edge and is the capability
the finish line calls gate-voltage navigation. Two things were missing.

**Nothing could sweep a virtual gate.** A `SweepAxis` steps one logical channel. A virtual gate moves
`P1` and `P2` together along a column of the virtual-gate matrix `M` (ADR 0048). The inner, pulsed axis
can already do that: the pulse slice's `Affine` value (ADR 0037) has a `scale`, so a second `Step` on
`P1_pulse` at `c_12 · v_p2` beside the `P2_pulse` step is a virtual pulse axis, and the simulated device
applies it. The outer, stepped axis could not: the executor sets one channel per axis.

**Nothing carried one node's outputs into the next node's definition.** `CalibrationNode.definition` is
a fixed `SweepDefinition`; `charge-lattice`'s `M` has to land in the next node's axis and pulse sequence
before it runs.

## Decision
- `SweepAxis.couplings: dict[str, float]` (channel → volts per volt of the axis value), excluded from
  serialization when empty so existing definitions keep their content hash. Only a stepped axis couples
  (a stage axis's couplings are `Affine` levels in its sequence; the schema rejects couplings on a stage
  axis); a coupled channel is swept by no axis and is neither sensed nor captured; it may hold a level in
  `levels`, which is then the coupling's origin. Compile resolves coupled channels as `level_source`;
  the executor sets each companion to `origin + c · value` with its axis, the origin its held level or 0,
  and settles for the longest of the channels it moved. The Dataset's coordinate stays the primary
  channel's value: in a virtual sweep the honeycomb is read in virtual coordinates.
- `virtual_gates` (ADR 0048) also outputs the compensation coefficients `c_21 = m_21 / m_11` and
  `c_12 = m_12 / m_22`, which a coupling and an `Affine.scale` take directly. Moving virtual gate 1 by
  ΔV moves `P1` by ΔV and `P2` by `c_21 · ΔV`; the lattice in those coordinates is `L · C` with
  `C = [[1, c_12], [c_21, 1]]`, which is diagonal when `M` is right.
- `InputBinding(node_id, output, target)` on `CalibrationNode.inputs`: `target` is a dotted path into
  `definition` as it serializes (`axes.0.couplings.P2`, `stage.sequence.body.0.level.scale`); the
  upstream node must be in `depends_on`; targets are unique. `qdt_tuning.bind(node, outcomes)` dumps the
  definition, sets every bound path from the accepted outcomes, validates it again, and returns the node
  to run. A missing or non-accepted upstream outcome, an unknown output or an unreachable path is an
  error before anything runs.
- The second node, `virtual-lattice`: the same window swept with `P1` coupled to `P2` by `c_21` and the
  pulse sequence stepping `P1_pulse` by `c_12 · v_p2`, read by `detect_transitions`, judged by a new rule
  `straightened` (accept when both residual cross ratios are within `max_residual_ratio` of zero;
  outputs the residuals and the lever arms in virtual coordinates).
- `qdt_server.tuning.run_tuneup(nodes, …)`: the first DAG runner. Nodes in the caller's order (a node's
  dependencies must come earlier; checked up front); each node is bound from the accepted outcomes before
  it and run with `run_node`; the tune-up stops at the first outcome that is not `accepted`. It returns
  the outcomes; nothing new is persisted (records and results are).

## Consequences
- Easier: the DAG edge exists and is tested end to end on the simulator: `charge-lattice` then
  `virtual-lattice`, the second accepted with residual cross ratios near zero where the first found 0.21.
  A node that needs an upstream number says so in data (`inputs`), not in code.
- Easier: virtual gates are a property of the sweep, so Flight Deck's click-to-set and gate-voltage
  navigation (FINISH_LINE) have an object to emit: an axis with couplings. The bench runs the same node
  once its stand wires a second pulse line (today only `ao1` is cabled).
- Harder: the companion follows the axis *value*, not its index, so a coupled channel's origin is the
  held level or 0, never "where it was". A sweep that wants a companion to follow from its current level
  must hold that level in `levels` first. ADR 0038's rule that a held channel is untouched by the sweep
  gains one exception, the coupled companion.
- Harder: `InputBinding.target` is a string path, checked only at bind time. A node whose template changes
  shape breaks its bindings at run time, not at import; the node constructors keep template and bindings
  together, and `test_bind.py` pins the two nodes.
- Harder: `run_tuneup` is a list, not a graph: the caller orders the nodes. A topological sort over
  `depends_on`, parallel branches, retries and a persisted `TuneUp` lifecycle object are the next layer;
  Flight Deck's DAG display needs that object.
- Must now: a rule whose outputs another node binds keeps those names stable or bumps its version
  (`virtual_gates` gained outputs without changing any verdict and stays at version 1); the executor's
  companion setting is honoured by every `LevelSource` the same way (`set` per channel), so no driver
  changes.

## Alternatives considered
- A virtual axis as a new object (`VirtualAxis` with several channels and coefficients) replacing
  `channel` — rejected: `channel` is a required field of a frozen object, every consumer reads it, and
  the Dataset needs one coordinate per axis; a primary channel plus companions keeps all of that.
- Companions following the axis *from where they were* — rejected: not reproducible (a definition would
  depend on the device's state); the held level in `levels` is the explicit origin.
- Virtual gates in the drivers (a `LevelSource` that is itself a linear combination) — rejected: the
  stand describes wires, the sweep describes motion; a combination is motion.
- Node inputs as a function (a node builder called with upstream outcomes) — rejected: nodes stop being
  data; a run could not record what was bound.
- Topological sort now — deferred: two nodes in a list is honest for the first edge; the sort comes with
  the persisted `TuneUp`.
