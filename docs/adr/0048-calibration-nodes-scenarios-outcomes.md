# 0048 — Step 6's modeling objects: `SimScenario`, `CalibrationNode` with a `DecisionRule`, `NodeOutcome`, `SimResult`; nodes and rules in `qdt-tuning`, the runner in `qdt-server`

**Status:** Accepted
**Date:** 2026-10-15
**Step:** 6 (adds to the modeling slice frozen by ADR 0033, as that ADR reserved)

## Context
Step 6's goal is a tune-up that runs unattended against `SimulatedDevice` and is confirmed, not
discovered, on hardware. Its schema slice has been named since the plan's v0.3 (`SimScenario`,
`SimResult`, `CalibrationNode`; ADR 0033 reserved them as additions beside the frozen `FitModel`,
`Estimate`, `AnalysisResult`). Nothing defined them. What exists: sweeps as data (`SweepDefinition`),
curated methods as data (`FitModel`, `MethodSpec`), results with dual provenance (record + method, ADR
0029), a registry that keeps records and results, a server that is the one process holding backends and
a `Registry`, and a simulator whose model knows the truth (`charge_lattice`) with one committed
fixture that CI reproduces bit-for-bit (`stability_24x32.npy`).

A calibration node has a third part the stack has no word for: the **decision**. After the experiment
and the method, something reads the estimates and says "this is a double-dot lattice; the virtual-gate
matrix is M; proceed" or "no; reason". That judgment must be as reproducible as a fit: named, versioned,
every parameter recorded. And where it runs matters under the rules: `qdt-analysis` is schema objects in,
`AnalysisResult` out (rule 5); `qdt-server` compiles, executes, stores and serves but never computes an
analysis itself; `qdt-sim` holds the physics.

## Decision
Four additive objects in `modeling.py`, none persisted yet:
- `SimScenario(scenario_id, description, model, seed, noise, attrs)`: a reproducible simulated situation.
  `model` holds scalar overrides of the simulator's default model by field name; the truth is never
  stored (rule 1), `qdt-sim` derives it (`model_for`, `device_for`, `lattice_truth`).
- `DecisionRule(name, version, parameters)`: a curated decision as data, the `FitModel` of decisions.
- `CalibrationNode(node_id, description, definition, method, decision, depends_on, attrs)`: one step of a
  tune-up as data: the `SweepDefinition` in logical channel names, the method's `FitModel` with every
  parameter, the rule. Stand-agnostic: the sequencer's instrument id is the constructor's argument.
- `NodeOutcome(outcome_id, node_id, scenario_id, record_id, result_id, status, message, outputs, …)`:
  what running a node produced; `accepted` carries `outputs` and names its record and result (which are
  durable), `rejected` carries a reason, `failed` means the experiment or the method did not complete.
- `SimResult(scenario, node_id, outcome, estimates, truth, created_at)`: a committed outcome with the
  model's truth, the fixture CI reproduces.

A new pure package, **`qdt-tuning`** (imports `qdt-schemas` and numpy only; `check_imports.py` enforces
it): `nodes.py` builds nodes, `decisions.py` holds `RULES` (name → version, callable), `decision_rule`
(a rule with its defaults filled) and `apply` (checks version and parameters against the callable, as
the method catalogue does, then runs it). The first rule, `virtual_gates`, accepts a transitions result
whose lattice is a plausible double-dot lattice (positive lever arms, cross ratios in [0, `max_cross_ratio`],
condition below `max_condition`) and outputs the lattice and the virtual-gate matrix
`M = L⁻¹ · diag(diag L)`. The first node, `charge-lattice`, is the stability diagram in the occupied
window read by `detect_transitions` (ADR 0029) and judged by `virtual_gates`.

The runner, **`qdt_server.tuning.run_node`**, takes the user's run path (compile, execute, record,
ingest, `catalogue.run_method`, `Registry.add_result`) and applies the rule: one node, one record, one
result, one outcome. A DAG over nodes is the next layer, in the same module.

## Consequences
- Easier: a node is a document. The same `charge-lattice` node compiles on the simulator's stand and on a
  bench-shaped one (the test pins it), so the bench confirmation is the same object with another
  instrument id. An outcome's provenance is complete: node (experiment + method + rule, all as data),
  record, result, scenario.
- Easier: the simulator is the oracle. `SimResult` fixtures commit what a node decided on a scenario and
  what the model says; CI reproduces them within tolerance, and a change to the node, the method or the
  simulator that moves a decided quantity is seen.
- Harder: outcomes are not persisted. A tune-up's history (which outcome led to which node) lives in
  memory until a `tuning_outcomes` table and a DDL bump arrive with the DAG runner; records and results
  are already durable, so nothing measured is lost.
- Harder: `SimScenario.model` overrides scalars only. A scenario that varies a capacitance matrix (the
  lattice itself) needs a nested value `AttrValue` does not allow; the first node's truth therefore comes
  from the default matrices, and a matrix-varying scenario is a follow-up decision.
- Harder: `qdt-tuning` duplicates the shape of `qdt_sim.scenarios.stability` as `stability_diagram`,
  because a node cannot depend on the simulator. The two agree by test.
- Must now: a new rule or node registers in `RULES` or `nodes.py`, carries every parameter, and lands with
  a `SimResult` fixture; a rule that changes a verdict bumps its `VERSION`.

## Alternatives considered
- Decisions as `qdt-analysis` methods returning an `AnalysisResult` — rejected: a decision's output is a
  verdict and the next node's inputs, not estimates and overlays on a Dataset; forcing it through
  `AnalysisResult` would put the verdict in `attrs` and lose rule 5's clarity.
- Decisions inside `qdt-server` — rejected: the server never computes anything itself (its package
  rules); keeping rules pure and separate lets them be tested with a hand-made `AnalysisResult` and
  reused by a future offline DAG replay.
- Storing the truth in `SimScenario` — rejected: rule 1 (schemas know no physics) and the truth is a
  function of the model, so storing it would duplicate what `qdt-sim` derives.
- Persisting outcomes now — rejected: no reader exists yet (Flight Deck's DAG display is a later
  deliverable), and ADR 0025's rule is to add what a step consumes.
- One `TuneUp` object holding nodes and outcomes — deferred to the DAG runner: a node and its outcome are
  the units; the DAG is a list of nodes and the edges `depends_on` already carries.
