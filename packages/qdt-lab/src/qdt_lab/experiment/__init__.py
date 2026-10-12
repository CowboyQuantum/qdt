"""Experiment compiler and executor (Step 2, ADR 0019).

`compile_sweep` turns a `SweepDefinition` plus a `StandConfig` into an `ExecutionPlan`: channels
resolved, the `Dataset` declared, the stage's program emitted by the backend's `Emitter` (ADR 0018).
`Executor` walks the plan against backend objects (anything satisfying the capability protocols) and
returns a stream `Source`.
"""

from .compile import compile_sweep
from .emit import DEFAULT_SCALES, Emitter, SimulatedEmitter, scale_for
from .execute import Executor

__all__ = [
    "DEFAULT_SCALES",
    "Emitter",
    "Executor",
    "SimulatedEmitter",
    "compile_sweep",
    "scale_for",
]
