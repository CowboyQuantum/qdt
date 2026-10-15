"""Run calibration nodes (ADR 0048, 0049): experiment → record → curated method → result → rule → outcome;
`run_tuneup` chains nodes, binding each one's inputs from the accepted outcomes before it.

The server is the one process that holds backends and a `Registry`, so the runner lives here. It uses
the same path a user's run takes (compile, execute, record, ingest; `catalogue.run_method`;
`Registry.add_result`), then applies the node's `DecisionRule` through `qdt_tuning.apply`. The record
and the result are durable; the `NodeOutcome` points at them. A DAG over nodes is the next layer.
"""

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qdt_lab.experiment import Executor, QuaEmitter, RunRecorder, SimulatedEmitter, compile_sweep
from qdt_registry import Registry
from qdt_schemas.modeling import AnalysisResult, CalibrationNode, NodeOutcome
from qdt_schemas.stand import StandConfig
from qdt_tuning import apply, bind

from . import catalogue

EMITTERS = {"simulated": SimulatedEmitter(), "qua": QuaEmitter()}


def run_node(
    node: CalibrationNode,
    stand: StandConfig,
    backends: Mapping[str, Any],
    registry: Registry,
    outbox: str | Path,
    *,
    device_id: str,
    scenario_id: str | None = None,
    campaign: str | None = None,
) -> tuple[NodeOutcome, AnalysisResult | None]:
    """Run `node` on `backends` wired by `stand`, recording into `registry`. Returns the outcome and the
    method's result (None when the experiment or the method did not complete). Raises for a node whose
    method is not in the catalogue or whose rule is unknown: those are definition errors, not outcomes."""
    if node.method.name not in catalogue.METHODS:
        raise KeyError(f"node {node.node_id!r}: no method {node.method.name!r} in the catalogue")
    outcome_id = uuid.uuid4().hex
    record_id = result_id = None
    try:
        plan = compile_sweep(node.definition, stand, EMITTERS)
        recorder = RunRecorder(plan, stand, device_id, campaign=campaign)
        for _ in recorder.wrap(Executor(plan, backends).run()).frames():
            pass
        record, path = recorder.finish(outbox)
        registry.ingest(record, path)
        record_id = record.record_id
        analysis = catalogue.run_method(
            node.method.name, record, registry.payload(record_id), node.method.parameters
        )
        result = registry.add_result(*analysis)
        result_id = result.result_id
    except (
        KeyError,
        ValueError,
        RuntimeError,
        TypeError,
    ) as e:  # a stand or a backend this node cannot run on
        return (
            NodeOutcome(
                outcome_id=outcome_id,
                node_id=node.node_id,
                scenario_id=scenario_id,
                record_id=record_id,
                status="failed",
                message=f"{type(e).__name__}: {e}",
                created_at=datetime.now(UTC),
            ),
            None,
        )
    decision = apply(node.decision, result)
    return (
        NodeOutcome(
            outcome_id=outcome_id,
            node_id=node.node_id,
            scenario_id=scenario_id,
            record_id=record_id,
            result_id=result_id,
            status=decision.status,
            message=decision.message,
            outputs=decision.outputs if decision.status == "accepted" else {},
            created_at=datetime.now(UTC),
            attrs={"method": node.method.name, "rule": node.decision.name},
        ),
        result,
    )


def run_tuneup(
    nodes: Sequence[CalibrationNode],
    stand: StandConfig,
    backends: Mapping[str, Any],
    registry: Registry,
    outbox: str | Path,
    *,
    device_id: str,
    scenario_id: str | None = None,
    campaign: str | None = None,
) -> list[NodeOutcome]:
    """Run `nodes` in order (ADR 0049): each node's `inputs` are bound from the accepted outcomes before
    it, then it runs; the tune-up stops at the first outcome that is not `accepted` and returns the
    outcomes so far, that one last. Raises ValueError for a node whose dependencies are not earlier in
    the list (the order is the caller's statement of the DAG)."""
    seen: set[str] = set()
    for node in nodes:
        missing = set(node.depends_on) - seen
        if missing:
            raise ValueError(
                f"node {node.node_id!r} depends on {sorted(missing)}, not run before it"
            )
        seen.add(node.node_id)
    outcomes: dict[str, NodeOutcome] = {}
    out: list[NodeOutcome] = []
    for node in nodes:
        try:
            bound = bind(node, outcomes)
        except (KeyError, ValueError) as e:
            outcome = NodeOutcome(
                outcome_id=uuid.uuid4().hex,
                node_id=node.node_id,
                scenario_id=scenario_id,
                status="failed",
                message=f"binding inputs: {e}",
                created_at=datetime.now(UTC),
            )
            out.append(outcome)
            return out
        outcome, _ = run_node(
            bound,
            stand,
            backends,
            registry,
            outbox,
            device_id=device_id,
            scenario_id=scenario_id,
            campaign=campaign,
        )
        out.append(outcome)
        if outcome.status != "accepted":
            return out
        outcomes[node.node_id] = outcome
    return out
