# qdt-tuning — package rules

Calibration nodes as data and the curated decision rules that judge their results (Step 6, ADR 0048).
Pure: schema objects in, schema objects out. It imports `qdt-schemas` and numpy only; it never runs an
experiment, opens a registry or touches a backend. The runner lives in `qdt-server` (the one process
that holds backends and a `Registry`); the simulator's realization of a scenario lives in `qdt-sim`.

## Layout
```
qdt_tuning/
  nodes.py      # CalibrationNode constructors: the experiment in logical channel names, the method, the rule, the inputs
  decisions.py  # RULES: curated decision rules, name → (version, callable); apply(rule, result) → Decision
  bind.py       # bind(node, outcomes): fill the node's `inputs` paths from upstream accepted outputs (ADR 0049)
```

## Rules
- A node is stand-agnostic: it names logical channels (`P1`, `P2_pulse`, `sensor`) and takes the
  sequencer's instrument id as an argument; the same node runs on the simulator and on the bench.
- A rule has a dotted name and a `VERSION`, puts every parameter in its `DecisionRule`, and returns a
  `Decision(status, message, outputs)`. A `failed` result is `failed`; a rule that declines a readable
  result is `rejected` with a reason; `outputs` are filled only when `accepted`. Bump `VERSION` whenever
  the same result could be judged differently.
- `apply(rule, result)` checks the rule's parameters against the callable's keyword arguments, as the
  server's method catalogue does; a test pins it.
- Truth for a node comes from `qdt-sim` through the same formula the rule uses (`virtual_gate_matrix`
  is here so both sides agree); the committed `SimResult` fixture lives beside the runner's test.
- A node that needs an upstream number declares an `InputBinding` (node, output, dotted path into its
  definition); a node constructor keeps the template value (0) and the binding together, and
  `test_bind.py` pins each node's bindings. A rule whose outputs another node binds keeps those names.
