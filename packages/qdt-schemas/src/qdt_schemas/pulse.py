"""Step 2 schema slice: the per-shot pulse sequence (ADR 0018). Frozen by ADR 0022.

A `PulseSequence` says what happens on logical channels during one shot, in backend-neutral terms:
hold a level, ramp, wait, drive at a frequency, measure. Timing is integer nanoseconds; any level,
duration, frequency or amplitude may be a `Symbol` that a sweep binds to an axis or a constant. Named
`Segment`s are reused by `call`. There is no control flow: loops over axes and shots belong to the
sweep stage, and a per-backend emitter turns sequence + stage into that backend's `SequencerProgram`.
The vocabulary grows only by ADR; it is deliberately not a general pulse language.
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


Value = float | Symbol
"""A number or a Symbol the sweep binds. (Not `stand.Quantity`, which names a physical quantity.)"""
Duration = int | Symbol


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


class Call(QdtModel):
    """Insert the named `Segment` here."""

    op: Literal["call"] = Field(default="call", description="Discriminator.")
    segment: str = Field(min_length=1, description="Name of a Segment of this sequence.")


Primitive = Annotated[Step | Ramp | Wait | Drive | Measure | Call, Field(discriminator="op")]


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
        results = [op.result for op in expanded if isinstance(op, Measure)]
        if len(set(results)) != len(results):
            raise ValueError("measure result names must be unique within a shot")
        units: dict[str, str] = {}
        for op in expanded:
            for field in ("level", "start", "stop", "frequency", "phase", "amplitude", "duration"):
                v = getattr(op, field, None)
                if isinstance(v, Symbol):
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

    def expand(self) -> tuple[Step | Ramp | Wait | Drive | Measure, ...]:
        """The shot with every `call` inlined, in time order."""
        return tuple(self._expand(self.body, {s.name: s for s in self.segments}, ()))

    def symbols(self) -> dict[str, str]:
        """Every Symbol used, name → unit."""
        out: dict[str, str] = {}
        for op in self.expand():
            for field in ("level", "start", "stop", "frequency", "phase", "amplitude", "duration"):
                v = getattr(op, field, None)
                if isinstance(v, Symbol):
                    out[v.name] = v.unit
        return out

    def results(self) -> tuple[str, ...]:
        """Result stream names, in time order."""
        return tuple(op.result for op in self.expand() if isinstance(op, Measure))

    def channels(self) -> tuple[str, ...]:
        """Logical channels touched, in first-use order."""
        seen: dict[str, None] = {}
        for op in self.expand():
            ch = getattr(op, "channel", None)
            if ch is not None:
                seen.setdefault(ch, None)
        return tuple(seen)
