"""Run calibration nodes (ADR 0048, 0049, 0050): experiment → record → curated method → result → rule →
outcome; a tune-up chains nodes in topological order, binding each one's inputs from the accepted
outcomes before it.

The server is the one process that holds backends and a `Registry`, so the runners live here. Two paths
share `analyse_and_decide`: `run_node`/`run_tuneup` execute a node's sweep directly (tests, fixtures,
scripts); `TuneUpManager` executes it through the `RunManager`, so Flight Deck sees every node's map on
the stream as it runs, and keeps a `TuneUp` lifecycle object per tune-up (in memory, like `Run`). The
outcomes are durable: `Registry.add_outcome` (ADR 0050).
"""

import asyncio
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qdt_lab.experiment import Executor, QuaEmitter, RunRecorder, SimulatedEmitter, compile_sweep
from qdt_registry import Registry
from qdt_schemas.activity import FixedLevel
from qdt_schemas.control import TuneUp
from qdt_schemas.data import AttrValue
from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.modeling import AnalysisResult, CalibrationNode, NodeOutcome, SimScenario
from qdt_schemas.stand import StandConfig
from qdt_tuning import TEMPLATES, apply, bind, order

from . import catalogue
from .runs import TERMINAL, RunManager, with_operating_point

EMITTERS = {"simulated": SimulatedEmitter(), "qua": QuaEmitter()}


def _failed(
    node_id: str,
    outcome_id: str,
    message: str,
    *,
    scenario_id: str | None = None,
    tuneup_id: str | None = None,
    record_id: str | None = None,
) -> NodeOutcome:
    return NodeOutcome(
        outcome_id=outcome_id,
        node_id=node_id,
        tuneup_id=tuneup_id,
        scenario_id=scenario_id,
        record_id=record_id,
        status="failed",
        message=message,
        created_at=datetime.now(UTC),
    )


def analyse_and_decide(
    node: CalibrationNode,
    record: MeasurementRecord,
    registry: Registry,
    *,
    outcome_id: str | None = None,
    scenario_id: str | None = None,
    tuneup_id: str | None = None,
) -> tuple[NodeOutcome, AnalysisResult | None]:
    """The analysis and decision half of a node, on a record already in `registry`: the catalogue
    method runs and its result is stored, the rule judges it, and the outcome is stored. Raises KeyError
    for a method that is not in the catalogue (a definition error, not an outcome)."""
    if node.method.name not in catalogue.METHODS:
        raise KeyError(f"node {node.node_id!r}: no method {node.method.name!r} in the catalogue")
    outcome_id = outcome_id or uuid.uuid4().hex
    try:
        analysis = catalogue.run_method(
            node.method.name, record, registry.payload(record.record_id), node.method.parameters
        )
        result = registry.add_result(*analysis)
    except (KeyError, ValueError, RuntimeError, TypeError) as e:
        outcome = _failed(
            node.node_id,
            outcome_id,
            f"{type(e).__name__}: {e}",
            scenario_id=scenario_id,
            tuneup_id=tuneup_id,
            record_id=record.record_id,
        )
        return registry.add_outcome(outcome), None
    decision = apply(node.decision, result)
    outcome = NodeOutcome(
        outcome_id=outcome_id,
        node_id=node.node_id,
        tuneup_id=tuneup_id,
        scenario_id=scenario_id,
        record_id=record.record_id,
        result_id=result.result_id,
        status=decision.status,
        message=decision.message,
        outputs=decision.outputs if decision.status == "accepted" else {},
        created_at=datetime.now(UTC),
        attrs={"method": node.method.name, "rule": node.decision.name},
    )
    return registry.add_outcome(outcome), result


def run_node(
    node: CalibrationNode,
    stand: StandConfig,
    backends: Mapping[str, Any],
    registry: Registry,
    outbox: str | Path,
    *,
    device_id: str,
    scenario_id: str | None = None,
    tuneup_id: str | None = None,
    campaign: str | None = None,
    held: Mapping[str, float] | None = None,
) -> tuple[NodeOutcome, AnalysisResult | None]:
    """Run `node` on `backends` wired by `stand`, recording into `registry`, with `held` (logical
    channel → level) merged in as the operating point the sweep inherits, as the stand server merges
    its own (ADR 0053; a virtual gate's companion moves from it). Returns the outcome and the
    method's result (None when the experiment or the method did not complete). Raises for a node whose
    method is not in the catalogue or whose rule is unknown: those are definition errors, not outcomes."""
    if node.method.name not in catalogue.METHODS:
        raise KeyError(f"node {node.node_id!r}: no method {node.method.name!r} in the catalogue")
    outcome_id = uuid.uuid4().hex
    try:
        plan = compile_sweep(with_operating_point(node.definition, held or {}), stand, EMITTERS)
        recorder = RunRecorder(plan, stand, device_id, campaign=campaign)
        for _ in recorder.wrap(Executor(plan, backends).run()).frames():
            pass
        record, path = recorder.finish(outbox)
        registry.ingest(record, path)
    except (
        KeyError,
        ValueError,
        RuntimeError,
        TypeError,
    ) as e:  # a stand or backend it cannot run on
        outcome = _failed(
            node.node_id,
            outcome_id,
            f"{type(e).__name__}: {e}",
            scenario_id=scenario_id,
            tuneup_id=tuneup_id,
        )
        return registry.add_outcome(outcome), None
    return analyse_and_decide(
        node, record, registry, outcome_id=outcome_id, scenario_id=scenario_id, tuneup_id=tuneup_id
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
    held: Mapping[str, float] | None = None,
) -> list[NodeOutcome]:
    """Run `nodes` in topological order (ADR 0049, 0050): each node's `inputs` are bound from the
    accepted outcomes before it (or from `held`, the operating point every node inherits, for a
    binding with a held fallback), then it runs; the tune-up stops at the first outcome that is not
    `accepted` and returns the outcomes so far, that one last. Raises ValueError for a missing
    dependency or a cycle."""
    tuneup_id = uuid.uuid4().hex
    outcomes: dict[str, NodeOutcome] = {}
    out: list[NodeOutcome] = []
    for node in order(nodes):
        try:
            bound = bind(node, outcomes, held)
        except (KeyError, ValueError) as e:
            failed = _failed(
                node.node_id,
                uuid.uuid4().hex,
                f"binding inputs: {e}",
                scenario_id=scenario_id,
                tuneup_id=tuneup_id,
            )
            out.append(registry.add_outcome(failed))
            return out
        outcome, _ = run_node(
            bound,
            stand,
            backends,
            registry,
            outbox,
            device_id=device_id,
            scenario_id=scenario_id,
            tuneup_id=tuneup_id,
            campaign=campaign,
            held=held,
        )
        out.append(outcome)
        if outcome.status != "accepted":
            return out
        outcomes[node.node_id] = outcome
    return out


def scenario_options(
    scenario: SimScenario | None, options: Mapping[str, AttrValue]
) -> dict[str, AttrValue]:
    """The run options a scenario means for the simulated backends (its device and that file's hash,
    noise seed and noise), under any options given explicitly."""
    base: dict[str, AttrValue] = {}
    if scenario is not None:
        base = {
            "device": scenario.device,
            "device_sha256": scenario.device_sha256,
            "seed": scenario.seed,
            "noise": scenario.noise,
        }
    return {**base, **options}


class TuneUpManager:
    """Runs tune-ups through the `RunManager` (ADR 0050): each node's sweep is a `Run` on the stream, so
    Flight Deck sees it live; the method, the rule and the outcome follow; a `TuneUp` records where the
    tune-up stands. One tune-up at a time per manager (the run manager runs one sweep at a time)."""

    POLL_S = 0.2

    def __init__(
        self, runs: RunManager, windows: Mapping[str, Mapping[str, Any]] | None = None
    ) -> None:
        self.runs = runs
        self.windows = dict(windows or {})
        """Per node id, the stand's windows for that node's template (ADR 0088)."""
        self.tuneups: dict[str, TuneUp] = {}
        self._stops: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def sequencer(self) -> str | None:
        """The stand's sequencer instrument id, which the node templates take; None without one."""
        for i in self.runs.stand.instruments:
            if "sequencer" in i.capabilities:
                return i.id
        return None

    @property
    def sensor_gate(self) -> str | None:
        """The stand's sensor-gate channel by convention (`SG`), if it has one; None otherwise."""
        return next((c.logical for c in self.runs.stand.channels if c.logical == "SG"), None)

    def templates(self) -> list[CalibrationNode]:
        """The nodes this server can offer: every template built for the stand's sequencer and sensor
        gate. Without a sensor gate the sensor node is left out (its sweep needs `SG`, `bias`, `sensor`)."""
        seq = self.sequencer
        if seq is None:
            return []
        gate = self.sensor_gate
        return [
            make(seq, gate, **self.windows.get(node_id, {}))
            for node_id, make in TEMPLATES.items()
            if gate is not None or node_id not in ("sensor-operating-point", "sensor-wing")
        ]

    def nodes_for(self, node_ids: Sequence[str]) -> tuple[CalibrationNode, ...]:
        """The templates named by `node_ids`, in topological order. Raises KeyError for an unknown id,
        ValueError for a missing dependency or no sequencer on the stand."""
        seq = self.sequencer
        if seq is None:
            raise ValueError("the stand has no sequencer; no node can run on it")
        offered = {n.node_id for n in self.templates()}
        unknown = [n for n in node_ids if n not in offered]
        if unknown:
            raise KeyError(f"no node templates {unknown} on this stand; have {sorted(offered)}")
        gate = self.sensor_gate
        return order(TEMPLATES[n](seq, gate, **self.windows.get(n, {})) for n in node_ids)

    async def start(
        self,
        nodes: Sequence[CalibrationNode],
        options: Mapping[str, AttrValue] | None = None,
        *,
        scenario: SimScenario | None = None,
        name: str | None = None,
    ) -> TuneUp:
        """Order `nodes`, queue the tune-up and run it in the background; returns the queued `TuneUp`.
        Raises ValueError for a missing dependency or a cycle."""
        ordered = order(nodes)
        resolved = scenario_options(scenario, options or {})
        tuneup = TuneUp(
            tuneup_id=uuid.uuid4().hex,
            name=name or " → ".join(n.node_id for n in ordered),
            nodes=ordered,
            stand_id=self.runs.stand.stand_id,
            device_id=self.runs.device_id,
            scenario_id=scenario.scenario_id if scenario else None,
            state="queued",
            created_at=datetime.now(UTC),
            attrs=resolved,
        )
        self.tuneups[tuneup.tuneup_id] = tuneup
        asyncio.create_task(self._execute(tuneup.tuneup_id, resolved))
        return tuneup

    def stop(self, tuneup_id: str) -> TuneUp:
        """Ask a tune-up to stop between nodes (the node running now finishes and is judged). Raises
        KeyError for an unknown tune-up, ValueError for one already finished."""
        tuneup = self.tuneups[tuneup_id]
        if tuneup.state in ("completed", "stopped", "failed"):
            raise ValueError(f"tune-up {tuneup_id!r} already {tuneup.state}")
        self._stops.add(tuneup_id)
        if tuneup.state == "queued":
            return self._set(
                tuneup_id,
                state="stopped",
                message="stopped by request",
                finished_at=datetime.now(UTC),
            )
        return tuneup

    def _set(self, tuneup_id: str, **update: Any) -> TuneUp:
        tuneup = self.tuneups[tuneup_id].model_copy(update=update)
        self.tuneups[tuneup_id] = tuneup
        return tuneup

    async def _wait(self, run_id: str):
        while self.runs.runs[run_id].state not in TERMINAL:
            await asyncio.sleep(self.POLL_S)
        return self.runs.runs[run_id]

    async def _execute(self, tuneup_id: str, options: dict[str, AttrValue]) -> None:
        async with self._lock:
            tuneup = self.tuneups[tuneup_id]
            if tuneup.state != "queued":  # stopped while queued
                return
            registry = self.runs.registry
            accepted: dict[str, NodeOutcome] = {}
            outcomes: list[NodeOutcome] = []
            self._set(tuneup_id, state="running", started_at=datetime.now(UTC))

            def finish(state: str, message: str = "") -> None:
                self._set(
                    tuneup_id,
                    state=state,
                    message=message,
                    outcomes=tuple(outcomes),
                    current_node=None,
                    finished_at=datetime.now(UTC),
                )

            async def record_failure(node: CalibrationNode, message: str, record_id=None) -> None:
                failed = _failed(
                    node.node_id,
                    uuid.uuid4().hex,
                    message,
                    scenario_id=tuneup.scenario_id,
                    tuneup_id=tuneup_id,
                    record_id=record_id,
                )
                outcomes.append(await asyncio.to_thread(registry.add_outcome, failed))

            try:
                for node in tuneup.nodes:
                    if tuneup_id in self._stops:
                        finish("stopped", "stopped by request")
                        return
                    self._set(tuneup_id, current_node=node.node_id, outcomes=tuple(outcomes))
                    try:
                        # a retune (ADR 0062): an upstream not in the tune-up falls back to the held level
                        held = {lv.channel: lv.value for lv in self.runs.levels()}
                        bound = bind(node, accepted, held)
                    except (KeyError, ValueError) as e:
                        await record_failure(node, f"binding inputs: {e}")
                        finish("stopped", f"node {node.node_id!r} could not be bound")
                        return
                    # the lifecycle object keeps the node as it ran: inputs bound (a retune's window
                    # about the held level, a lattice at the fitted wing), not the template
                    self._set(
                        tuneup_id,
                        nodes=tuple(
                            bound if n.node_id == node.node_id else n for n in tuneup.nodes
                        ),
                    )
                    tuneup = self.tuneups[tuneup_id]
                    run = await self.runs.start(bound.definition, options)
                    run = await self._wait(run.run_id)
                    if run.state != "completed" or not run.record_id:
                        why = f"the run {run.state}" + (f": {run.error}" if run.error else "")
                        await record_failure(node, why, run.record_id)
                        finish("stopped", f"node {node.node_id!r}: {why}")
                        return
                    record = await asyncio.to_thread(registry.get, run.record_id)
                    outcome, _ = await asyncio.to_thread(
                        analyse_and_decide,
                        bound,
                        record,
                        registry,
                        scenario_id=tuneup.scenario_id,
                        tuneup_id=tuneup_id,
                    )
                    outcomes.append(outcome)
                    if outcome.status != "accepted":
                        finish(
                            "stopped", f"node {node.node_id!r} {outcome.status}: {outcome.message}"
                        )
                        return
                    accepted[node.node_id] = outcome
                    if node.holds:
                        # the node decided where the stand sits (ADR 0053, 0062): hold it now
                        levels = [
                            FixedLevel(channel=ch, value=outcome.outputs[name])
                            for ch, name in node.holds.items()
                            if name in outcome.outputs
                        ]
                        if levels:  # a level beyond a limit fails the tune-up (ADR 0085)
                            self.runs.set_levels(
                                levels,
                                by=f"tune-up {tuneup_id}",
                                reason=f"node {node.node_id!r} accepted: holds "
                                + ", ".join(f"{lv.channel} = {lv.value:g}" for lv in levels),
                            )
                finish("completed")
            except Exception as e:  # noqa: BLE001 — the tune-up reports its failure
                finish("failed", f"{type(e).__name__}: {e}")
