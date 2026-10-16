"""Step 2 schema slice: the per-shot pulse sequence (ADR 0018). Frozen by ADR 0022.

A `PulseSequence` says what happens on logical channels during one shot, in backend-neutral terms:
hold a level, ramp, wait, drive at a frequency, measure. Timing is integer nanoseconds; any level,
duration, frequency or amplitude may be a `Symbol` that a sweep binds to an axis or a constant, and
any level, frequency, phase or amplitude may be an `Affine` of one (`scale·symbol + offset`, ADR 0037).
A `difference` subtracts two of the shot's measures into a result of its own, per shot (ADR 0037).
A `capture` opens a time window on a `WaveformSense` channel at that point of the shot, one record per
shot (ADR 0060): the shot is the one timeline, and a time-resolved readout hangs off it like an
integrated one. Named `Segment`s are reused by `call`. There is no control flow: loops over axes and
shots belong to the sweep stage, and a per-backend emitter turns sequence + stage into that backend's
`SequencerProgram`. The vocabulary grows only by ADR; it is deliberately not a general pulse language.
"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ._base import QdtModel
from .data import AttrValue


class Symbol(QdtModel):
    """A named placeholder for a value the sweep supplies (bound to an axis or a constant)."""

    name: str = Field(
        min_length=1, description="Symbol name; the same name means the same value everywhere."
    )
    unit: str = Field(
        description="Physical unit of the value, e.g. 'V', 'ns', 'Hz'; empty for dimensionless."
    )


class Affine(QdtModel):
    """`scale · symbol + offset`: a value that follows a bound symbol, e.g. a chop point `v_P2 + 2 mV`.

    `offset` is in the symbol's unit; `scale` is dimensionless. A bare symbol stays a `Symbol`.
    """

    symbol: Symbol = Field(description="The symbol the value follows; bound like any other.")
    scale: float = Field(default=1.0, description="Dimensionless factor on the symbol's value.")
    offset: float = Field(default=0.0, description="Added after scaling, in the symbol's unit.")

    def of(self, value: float) -> float:
        """The value when the symbol takes `value`."""
        return self.scale * value + self.offset


Value = float | Symbol | Affine
"""A number, a Symbol the sweep binds, or an Affine of one. (Not `stand.Quantity`, which names a
physical quantity.)"""
Duration = int | Symbol


def symbol_of(v: object) -> Symbol | None:
    """The Symbol a value depends on, if any (bare or inside an Affine)."""
    if isinstance(v, Symbol):
        return v
    if isinstance(v, Affine):
        return v.symbol
    return None


class Step(QdtModel):
    """Hold `channel` at `level` for `duration`."""

    op: Literal["step"] = Field(default="step", description="Discriminator.")
    channel: str = Field(min_length=1, description="Logical channel (ChannelMap.logical).")
    level: Value = Field(description="Level in the channel's quantity unit, or a Symbol.")
    duration: Duration = Field(description="Duration in integer nanoseconds, or a Symbol in 'ns'.")


class Ramp(QdtModel):
    """Ramp `channel` linearly from `start` to `stop` over `duration`."""

    op: Literal["ramp"] = Field(default="ramp", description="Discriminator.")
    channel: str = Field(min_length=1, description="Logical channel (ChannelMap.logical).")
    start: Value = Field(
        description="Level at the start, in the channel's quantity unit, or a Symbol."
    )
    stop: Value = Field(
        description="Level at the end, in the channel's quantity unit, or a Symbol."
    )
    duration: Duration = Field(description="Duration in integer nanoseconds, or a Symbol in 'ns'.")


class Wait(QdtModel):
    """All channels hold their current level for `duration`."""

    op: Literal["wait"] = Field(default="wait", description="Discriminator.")
    duration: Duration = Field(description="Duration in integer nanoseconds, or a Symbol in 'ns'.")


class Drive(QdtModel):
    """Drive `channel` with a tone (ESR / EDSR) for `duration`."""

    op: Literal["drive"] = Field(default="drive", description="Discriminator.")
    channel: str = Field(min_length=1, description="Logical channel (ChannelMap.logical).")
    frequency: Value = Field(description="Tone frequency in Hz, or a Symbol.")
    phase: Value = Field(default=0.0, description="Phase in radians, or a Symbol.")
    amplitude: Value = Field(description="Amplitude in the channel's quantity unit, or a Symbol.")
    duration: Duration = Field(description="Duration in integer nanoseconds, or a Symbol in 'ns'.")


class Measure(QdtModel):
    """Integrate `channel` for `duration` into the result stream `result`, once per shot."""

    op: Literal["measure"] = Field(default="measure", description="Discriminator.")
    channel: str = Field(min_length=1, description="Logical sense channel (ChannelMap.logical).")
    duration: Duration = Field(
        description="Integration time in integer nanoseconds, or a Symbol in 'ns'."
    )
    result: str = Field(
        min_length=1,
        description="Result stream name; unique within the sequence; becomes a data variable.",
    )


class Capture(QdtModel):
    """Open a time window on a `WaveformSense` `channel` here in the shot, into the result stream
    `result`: one record per shot, `num` samples over `duration`, time counted from this point
    (ADR 0060). The shot waits for the window. The sequencer triggers the capture; the samples land on
    the declared grid (ADR 0015). The window is fixed per sweep, so it is never a Symbol.
    """

    op: Literal["capture"] = Field(default="capture", description="Discriminator.")
    channel: str = Field(
        min_length=1, description="Logical WaveformSense channel (ChannelMap.logical)."
    )
    duration: int = Field(
        ge=1, description="Window length in integer nanoseconds, from this point of the shot."
    )
    num: int = Field(
        ge=2, description="Samples in the window: the declared time grid, filled exactly."
    )
    result: str = Field(
        min_length=1,
        description=(
            "Result stream name; unique within the sequence; becomes a data variable over the sweep's "
            "axes, 'shot' when shots are kept, and its time axis."
        ),
    )

    @property
    def duration_s(self) -> float:
        return self.duration * 1e-9


class Difference(QdtModel):
    """`result = a − b`, per shot, from two measures earlier in the shot (e.g. a chopped readout).

    Computed by the sequencer before any reduction, so a mean of differences is what is recorded; the
    measured results are kept as well. Takes no time.
    """

    op: Literal["difference"] = Field(default="difference", description="Discriminator.")
    result: str = Field(
        min_length=1,
        description="Result stream name; unique within the sequence; becomes a data variable.",
    )
    a: str = Field(min_length=1, description="Measure result the difference starts from.")
    b: str = Field(
        min_length=1, description="Measure result subtracted from `a`; same channel unit."
    )


class Call(QdtModel):
    """Insert the named `Segment` here."""

    op: Literal["call"] = Field(default="call", description="Discriminator.")
    segment: str = Field(min_length=1, description="Name of a Segment of this sequence.")


Primitive = Annotated[
    Step | Ramp | Wait | Drive | Measure | Capture | Difference | Call, Field(discriminator="op")
]
Expanded = Step | Ramp | Wait | Drive | Measure | Capture | Difference


class Segment(QdtModel):
    """A named, reusable sub-sequence (e.g. 'initialise', 'read_out')."""

    name: str = Field(min_length=1, description="Segment name, unique within the sequence.")
    ops: tuple[Primitive, ...] = Field(min_length=1, description="Primitives in time order.")


class PulseSequence(QdtModel):
    """What one shot does: `body` in time order, with `segments` available to `call`."""

    name: str = Field(min_length=1, description="Human-readable name.")
    segments: tuple[Segment, ...] = Field(default=(), description="Reusable sub-sequences.")
    body: tuple[Primitive, ...] = Field(min_length=1, description="The shot, in time order.")
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict, description="Free-form scalar metadata, e.g. author, version."
    )

    @model_validator(mode="after")
    def _consistent(self) -> "PulseSequence":
        names = [s.name for s in self.segments]
        if len(set(names)) != len(names):
            raise ValueError("segment names must be unique")
        segments = {s.name: s for s in self.segments}
        for owner, ops in [("body", self.body), *((s.name, s.ops) for s in self.segments)]:
            for op in ops:
                if isinstance(op, Call) and op.segment not in segments:
                    raise ValueError(f"{owner!r} calls unknown segment {op.segment!r}")
        # no recursion: every segment must expand
        for s in self.segments:
            self._expand(s.ops, segments, (s.name,))
        expanded = self._expand(self.body, segments, ())
        results = [op.result for op in expanded if isinstance(op, Measure | Capture | Difference)]
        if len(set(results)) != len(results):
            raise ValueError("result names must be unique within a shot")
        measured: dict[str, str] = {}  # result -> channel, in time order
        for op in expanded:
            if isinstance(op, Measure):
                measured[op.result] = op.channel
            elif isinstance(op, Difference):
                for x in (op.a, op.b):
                    if x not in measured:
                        raise ValueError(
                            f"difference {op.result!r} needs {x!r} measured earlier in the shot"
                        )
                if op.a == op.b:
                    raise ValueError(f"difference {op.result!r} subtracts {op.a!r} from itself")
        captured = [op.channel for op in expanded if isinstance(op, Capture)]
        if len(set(captured)) != len(captured):
            raise ValueError("a channel is captured once per shot (ADR 0060)")
        units: dict[str, str] = {}
        for op in expanded:
            for field in ("level", "start", "stop", "frequency", "phase", "amplitude", "duration"):
                v = symbol_of(getattr(op, field, None))
                if v is not None:
                    if units.setdefault(v.name, v.unit) != v.unit:
                        raise ValueError(
                            f"symbol {v.name!r} used with units {units[v.name]!r} and {v.unit!r}"
                        )
                    if field == "duration" and v.unit != "ns":
                        raise ValueError(
                            f"duration symbol {v.name!r} must be in 'ns', not {v.unit!r}"
                        )
        return self

    @staticmethod
    def _expand(ops, segments, stack):
        out = []
        for op in ops:
            if isinstance(op, Call):
                if op.segment in stack:
                    raise ValueError(f"segment {op.segment!r} calls itself (via {stack})")
                out.extend(
                    PulseSequence._expand(segments[op.segment].ops, segments, (*stack, op.segment))
                )
            else:
                out.append(op)
        return out

    def expand(self) -> tuple[Expanded, ...]:
        """The shot with every `call` inlined, in time order."""
        return tuple(self._expand(self.body, {s.name: s for s in self.segments}, ()))

    def symbols(self) -> dict[str, str]:
        """Every Symbol used, name → unit."""
        out: dict[str, str] = {}
        for op in self.expand():
            for field in ("level", "start", "stop", "frequency", "phase", "amplitude", "duration"):
                v = symbol_of(getattr(op, field, None))
                if v is not None:
                    out[v.name] = v.unit
        return out

    def results(self) -> tuple[str, ...]:
        """Result stream names (measures, captures and differences), in time order."""
        return tuple(
            op.result for op in self.expand() if isinstance(op, Measure | Capture | Difference)
        )

    def captures(self) -> tuple[Capture, ...]:
        """The shot's time-resolved readouts (ADR 0060), in time order."""
        return tuple(op for op in self.expand() if isinstance(op, Capture))

    def result_channel(self, result: str) -> str:
        """The channel a result comes from (a difference: that of its `a`)."""
        ops = {
            op.result: op for op in self.expand() if isinstance(op, Measure | Capture | Difference)
        }
        op = ops[result]
        while isinstance(op, Difference):
            op = ops[op.a]
        return op.channel

    def channels(self) -> tuple[str, ...]:
        """Logical channels touched, in first-use order (a capture's scope channel included)."""
        seen: dict[str, None] = {}
        for op in self.expand():
            ch = getattr(op, "channel", None)
            if ch is not None:
                seen.setdefault(ch, None)
        return tuple(seen)
