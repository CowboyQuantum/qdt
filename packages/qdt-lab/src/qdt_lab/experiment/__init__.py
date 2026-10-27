"""Experiment compiler and executor (Step 2, ADR 0019).

`compile_sweep` turns a `SweepDefinition` plus a `StandConfig` into an `ExecutionPlan`: channels
resolved, the `Dataset` declared, the stage's program emitted by the backend's `Emitter` (ADR 0018).
`Executor` walks the plan against backend objects (anything satisfying the capability protocols) and
returns a stream `Source`.
"""

from .compile import LimitError, check_limits, compile_sweep, driven_extents, resolve_pacing
from .emit import (
    DEFAULT_SCALES,
    ONCE,
    Emitter,
    QuaEmitter,
    SimulatedEmitter,
    TriggeredStep,
    once_results,
    scale_for,
)
from .execute import Executor, build_backends
from .record import RunRecorder

__all__ = [
    "DEFAULT_SCALES",
    "ONCE",
    "Emitter",
    "Executor",
    "LimitError",
    "QuaEmitter",
    "RunRecorder",
    "SimulatedEmitter",
    "TriggeredStep",
    "build_backends",
    "check_limits",
    "compile_sweep",
    "driven_extents",
    "once_results",
    "resolve_pacing",
    "scale_for",
]
