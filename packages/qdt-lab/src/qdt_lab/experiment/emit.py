"""Emitters: PulseSequence + stage shape → a backend's `SequencerProgram` (ADR 0018).

An emitter owns everything the sequencer language needs around the per-shot sequence: the loops over
the stage axes and shots, the integer input streams for swept and per-run symbols, the stream
processing that keeps or reduces shots, and the result declarations. The simulated emitter is the first
ISA: its body is the sequence itself as JSON plus the symbol → parameter map, which `qdt-sim`'s
`SimulatedDevice` interprets against the dot model. The QUA emitter is Step 5 (`[opx]`).
"""

import json
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from qdt_schemas.activity import (
    ParameterBinding,
    SequencerParameter,
    SequencerProgram,
    SequencerResult,
    SequencerStage,
    SweepAxis,
)
from qdt_schemas.stand import QUANTITY_UNIT, ChannelMap

DEFAULT_SCALES: dict[str, float] = {
    "V": 1e-6,
    "A": 1e-12,
    "Hz": 1.0,
    "ns": 1.0,
    "rad": 1e-6,
    "": 1e-6,
}
"""Integer scale per unit (ADR 0015): a value in `unit` travels as round(value / scale)."""


def scale_for(unit: str) -> float:
    try:
        return DEFAULT_SCALES[unit]
    except KeyError:
        raise ValueError(f"no integer scale defined for unit {unit!r}") from None


@runtime_checkable
class Emitter(Protocol):
    """Translates a stage into one backend's program and the bindings that compute its parameters."""

    backend: str

    def emit(
        self,
        stage: SequencerStage,
        axes: Mapping[str, SweepAxis],
        channels: Mapping[str, ChannelMap],
    ) -> tuple[SequencerProgram, tuple[ParameterBinding, ...]]:
        """`axes` holds every axis of the definition by name; `channels` every logical channel the
        sequence touches. Raises ValueError for what this backend cannot express."""
        ...


class SimulatedEmitter:
    """Backend 'simulated': the body is the sequence as JSON; parameters follow a fixed naming scheme.

    Parameters: `n_<axis>` per stage axis (axis_num); per symbol bound to a stage axis `<sym>_start`
    and `<sym>_step` (axis_start / axis_step); per symbol bound to a stepped axis `<sym>` (axis_value);
    per constant symbol `<sym>` (const); `shots` (const). Results: one per `measure` and per
    `difference` (ADR 0037), float64, in the sense channel's quantity unit, dims = stage axes (+ `shots`
    when kept and shots > 1). Affine values travel inside the sequence; the device applies them.
    """

    backend = "simulated"

    def emit(
        self,
        stage: SequencerStage,
        axes: Mapping[str, SweepAxis],
        channels: Mapping[str, ChannelMap],
    ) -> tuple[SequencerProgram, tuple[ParameterBinding, ...]]:
        if stage.sequence is None:
            raise ValueError("SimulatedEmitter emits a PulseSequence; the stage carries a program")
        seq = stage.sequence
        units = seq.symbols()
        params: list[SequencerParameter] = []
        bindings: list[ParameterBinding] = []
        symbol_params: dict[str, dict[str, str]] = {}
        for name in stage.axes:
            params.append(SequencerParameter(name=f"n_{name}", unit="", scale=1.0))
            bindings.append(ParameterBinding(parameter=f"n_{name}", source="axis_num", axis=name))
        for b in stage.bindings:
            unit = units[b.symbol]
            scale = scale_for(unit)
            if b.axis is not None and b.axis in stage.axes:
                for suffix, source in (("start", "axis_start"), ("step", "axis_step")):
                    p = f"{b.symbol}_{suffix}"
                    params.append(SequencerParameter(name=p, unit=unit, scale=scale))
                    bindings.append(ParameterBinding(parameter=p, source=source, axis=b.axis))
                symbol_params[b.symbol] = {
                    "start": f"{b.symbol}_start",
                    "step": f"{b.symbol}_step",
                    "axis": f"n_{b.axis}",
                }
            elif b.axis is not None:
                params.append(SequencerParameter(name=b.symbol, unit=unit, scale=scale))
                bindings.append(
                    ParameterBinding(parameter=b.symbol, source="axis_value", axis=b.axis)
                )
                symbol_params[b.symbol] = {"value": b.symbol}
            else:
                params.append(SequencerParameter(name=b.symbol, unit=unit, scale=scale))
                bindings.append(
                    ParameterBinding(
                        parameter=b.symbol, source="const", value=round(b.value / scale)
                    )
                )
                symbol_params[b.symbol] = {"value": b.symbol}
        params.append(SequencerParameter(name="shots", unit="", scale=1.0))
        bindings.append(ParameterBinding(parameter="shots", source="const", value=stage.shots))

        results = []
        for op in seq.expand():
            if op.op == "difference":
                qa, qb = (channels[seq.result_channel(x)].quantity for x in (op.a, op.b))
                if qa != qb:
                    raise ValueError(f"difference {op.result!r} subtracts a {qb} from a {qa}")
            elif op.op != "measure":
                continue
            elif op.channel not in channels:
                raise ValueError(f"measure on unknown channel {op.channel!r}")
            dims = tuple(f"n_{a}" for a in stage.axes)
            if stage.reduction(op.result) == "keep" and stage.shots > 1:
                dims = (*dims, "shots")
            if not dims:
                raise ValueError(
                    f"result {op.result!r} has no axis: a stage with no axes needs shots > 1 kept"
                )
            results.append(
                SequencerResult(
                    name=op.result,
                    dims=dims,
                    dtype="float64",
                    unit=QUANTITY_UNIT[channels[seq.result_channel(op.result)].quantity],
                )
            )
        body = json.dumps(
            {
                "sequence": seq.model_dump(mode="json"),
                "symbols": symbol_params,
                "reduce": {r.name: stage.reduction(r.name) for r in results},
            },
            sort_keys=True,
        )
        program = SequencerProgram(
            backend=self.backend,
            body=body,
            parameters=tuple(params),
            results=tuple(results),
            attrs={"emitter": type(self).__name__, "sequence": seq.name},
        )
        return program, tuple(bindings)


class QuaEmitter(SimulatedEmitter):
    """Backend 'qua' (the OPX, Step 5): the same body and parameter scheme as the simulated emitter. The
    OPX driver (`qdt_lab.drivers.qm.opx1000`) turns the sequence into a QUA program at compile time,
    reading every parameter from one int input stream (compile once, run with ints; Probe 01)."""

    backend = "qua"
