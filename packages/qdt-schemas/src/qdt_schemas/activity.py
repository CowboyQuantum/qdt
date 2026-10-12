"""Step 2 schema slice: activity — what an experiment asks a stand to do. Frozen only after Step 2's
test ladder passes.

`SequencerProgram` (ADR 0017) is the envelope the executor hands to a `Sequencer`: a typed contract
(runtime parameters, result streams) around an opaque, backend-specific body. `SweepDefinition`
(ADR 0019) is the experiment as data: stepped axes, sensed levels, an optional sequencer `stage` whose
per-shot `PulseSequence` (ADR 0018) is bound to the innermost axes, shots innermost, repeats outermost.
`ExecutionPlan` is its compiled, resolved form: the `Dataset` to fill, the channel bindings, and the
emitted program with how each integer parameter is computed. Probe 01 (ADR 0015) fixed the constraints
the envelope encodes: one compiled program, integer runtime parameters (fractional values as scaled
integers), positional results with no in-band coordinates.
"""

from collections.abc import Mapping
from typing import Literal

from pydantic import Field, model_validator

from ._base import QdtModel
from .data import AttrValue, Dataset, DType
from .pulse import PulseSequence
from .stand import Capability, Quantity


class SequencerParameter(QdtModel):
    """A runtime input of a compiled program: sent as an integer, meaning `integer × scale` in `unit`."""

    name: str = Field(
        min_length=1,
        description="Parameter name, unique within the program; the key the executor supplies at run time.",
    )
    unit: str = Field(
        description="Physical unit of the parameter's value, e.g. 'V'; empty for counts and dimensionless."
    )
    scale: float = Field(
        default=1.0,
        gt=0,
        description=(
            "Value in `unit` = integer × scale. Fractional quantities travel as scaled integers because "
            "fixed-typed input streams do not compile (ADR 0015); counts use 1."
        ),
    )


class SequencerResult(QdtModel):
    """A result stream of a compiled program; fills one data variable of the Dataset a run is given."""

    name: str = Field(
        min_length=1,
        description="Result name, unique within the program; must match a DataVariable name in the run's Dataset.",
    )
    dims: tuple[str, ...] = Field(
        min_length=1,
        description=(
            "Parameter names, in array (row-major) order, whose integer values at run time are the "
            "lengths of this result's axes."
        ),
    )
    dtype: DType = Field(
        description="Element type the sequencer delivers (int saves fetch as int64 on the OPX, ADR 0015)."
    )
    unit: str = Field(description="Physical unit of the result values; empty for raw counts.")


class SequencerProgram(QdtModel):
    """A compiled-once program for a `Sequencer`: typed parameter and result contract around an opaque body."""

    backend: str = Field(
        min_length=1,
        description=(
            "Language or target the body is written for, e.g. 'qua'. A Sequencer accepts the backends "
            "it names; the simulated one accepts any and ignores the body."
        ),
    )
    body: str = Field(
        description="The program itself, opaque to the schema (QUA source, a serialized program, ...)."
    )
    parameters: tuple[SequencerParameter, ...] = Field(
        default=(),
        description="Runtime inputs that change between runs without recompiling.",
    )
    results: tuple[SequencerResult, ...] = Field(
        min_length=1,
        description="Result streams the program produces; positional, no in-band coordinates.",
    )
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict,
        description="Free-form scalar metadata, e.g. the generating experiment and its version.",
    )

    @model_validator(mode="after")
    def _consistent(self) -> "SequencerProgram":
        params = [p.name for p in self.parameters]
        if len(set(params)) != len(params):
            raise ValueError("parameter names must be unique")
        results = [r.name for r in self.results]
        if len(set(results)) != len(results):
            raise ValueError("result names must be unique")
        for r in self.results:
            unknown = set(r.dims) - set(params)
            if unknown:
                raise ValueError(
                    f"result {r.name!r} sizes its axes by unknown parameters {sorted(unknown)}"
                )
            if len(set(r.dims)) != len(r.dims):
                raise ValueError(f"result {r.name!r} repeats a parameter as an axis")
        return self

    def parameter(self, name: str) -> SequencerParameter:
        for p in self.parameters:
            if p.name == name:
                return p
        raise KeyError(f"unknown parameter {name!r}")

    def check_parameters(self, values: Mapping[str, int]) -> None:
        """Raise ValueError unless `values` supplies every parameter as an int (bool excluded)."""
        missing = {p.name for p in self.parameters} - set(values)
        if missing:
            raise ValueError(f"missing parameters {sorted(missing)}")
        unknown = set(values) - {p.name for p in self.parameters}
        if unknown:
            raise ValueError(f"unknown parameters {sorted(unknown)}")
        for name, v in values.items():
            if type(v) is not int:  # bool excluded on purpose
                raise ValueError(f"parameter {name!r} must be an int, got {type(v).__name__}")

    def result_shape(self, result: str, values: Mapping[str, int]) -> tuple[int, ...]:
        """Shape of `result` for the given parameter values."""
        r = next((r for r in self.results if r.name == result), None)
        if r is None:
            raise ValueError(f"unknown result {result!r}")
        shape = tuple(values[d] for d in r.dims)
        if any(n < 1 for n in shape):
            raise ValueError(f"result {result!r} would have an empty axis: {shape}")
        return shape

    def check_run(self, values: Mapping[str, int], dataset: Dataset) -> None:
        """Raise ValueError unless a run with `values` can fill `dataset`: every result is a data
        variable of the same rank, dtype and (parameter-valued) sizes."""
        self.check_parameters(values)
        sizes = {d.name: d.size for d in dataset.dims}
        variables = {v.name: v for v in dataset.data_vars}
        for r in self.results:
            v = variables.get(r.name)
            if v is None:
                raise ValueError(f"dataset has no data variable for result {r.name!r}")
            shape = self.result_shape(r.name, values)
            if len(v.dims) != len(shape):
                raise ValueError(
                    f"result {r.name!r} has {len(shape)} axes; variable has {len(v.dims)}"
                )
            declared = tuple(sizes[d] for d in v.dims)
            if declared != shape:
                raise ValueError(f"result {r.name!r} runs as {shape}; dataset declares {declared}")
            if v.dtype != r.dtype:
                raise ValueError(
                    f"result {r.name!r} is {r.dtype}; variable {v.name!r} is {v.dtype}"
                )


# --- SweepDefinition (ADR 0019) -----------------------------------------------------------------

Reduction = Literal["keep", "mean", "sum"]
ParameterSource = Literal["const", "axis_num", "axis_start", "axis_step", "axis_value"]


class SweepAxis(QdtModel):
    """One swept coordinate: `num` evenly spaced values of a logical channel from `start` to `stop`."""

    name: str = Field(
        min_length=1,
        description="Axis name; the Dataset dimension and coordinate are named after it.",
    )
    channel: str = Field(
        min_length=1, description="Logical channel (ChannelMap.logical) that is swept."
    )
    start: float = Field(description="Value at index 0, in the channel's quantity unit.")
    stop: float = Field(description="Value at the last index (inclusive).")
    num: int = Field(ge=1, description="Number of points.")

    @property
    def step(self) -> float:
        return (self.stop - self.start) / (self.num - 1) if self.num > 1 else 0.0

    def value(self, index: int) -> float:
        return self.start + index * self.step


class SensedLevel(QdtModel):
    """A level read at every stepped point; becomes a data variable over the stepped axes."""

    name: str = Field(min_length=1, description="Data variable name.")
    channel: str = Field(
        min_length=1, description="Logical LevelSense channel (ChannelMap.logical)."
    )


class SymbolBinding(QdtModel):
    """What a `PulseSequence` Symbol takes: an axis's current value, or a constant. Exactly one."""

    symbol: str = Field(min_length=1, description="Symbol name in the stage's PulseSequence.")
    axis: str | None = Field(
        default=None,
        description=(
            "Axis whose value the symbol takes. A stage axis is swept inside the program; a stepped "
            "axis is passed as a per-run constant."
        ),
    )
    value: float | None = Field(default=None, description="Constant value in the symbol's unit.")

    @model_validator(mode="after")
    def _one(self) -> "SymbolBinding":
        if (self.axis is None) == (self.value is None):
            raise ValueError(f"binding of {self.symbol!r} needs exactly one of axis or value")
        return self


class ParameterBinding(QdtModel):
    """How one integer parameter of an emitted or hand-written program is computed at run time."""

    parameter: str = Field(min_length=1, description="SequencerProgram parameter name.")
    source: ParameterSource = Field(
        description=(
            "const: `value`. axis_num: the axis's point count. axis_start / axis_step: the axis's start "
            "or step in the parameter's unit, divided by its scale and rounded. axis_value: the stepped "
            "axis's current value, likewise scaled; recomputed at every stepped point."
        )
    )
    axis: str | None = Field(default=None, description="Axis name for the axis_* sources.")
    value: int | None = Field(default=None, description="Integer for the const source.")

    @model_validator(mode="after")
    def _consistent(self) -> "ParameterBinding":
        if self.source == "const" and (self.value is None or self.axis is not None):
            raise ValueError(f"const binding of {self.parameter!r} needs value and no axis")
        if self.source != "const" and (self.axis is None or self.value is not None):
            raise ValueError(f"{self.source} binding of {self.parameter!r} needs axis and no value")
        return self


class SequencerStage(QdtModel):
    """The part of a sweep a `Sequencer` runs: the innermost axes, the per-shot sequence, the shots.

    Exactly one of `sequence` (emitted per backend, ADR 0018) or `program` (hand-written escape hatch,
    bound through `parameters`).
    """

    instrument: str = Field(
        min_length=1, description="Instrument id of the Sequencer that runs it."
    )
    axes: tuple[str, ...] = Field(
        default=(),
        description=(
            "Names of the axes the program sweeps internally, outer to inner. They must be the innermost "
            "axes of the SweepDefinition, in order."
        ),
    )
    sequence: PulseSequence | None = Field(default=None, description="The per-shot sequence.")
    bindings: tuple[SymbolBinding, ...] = Field(
        default=(), description="One binding per Symbol of `sequence`."
    )
    program: SequencerProgram | None = Field(
        default=None, description="Escape hatch: a hand-written program instead of `sequence`."
    )
    parameters: tuple[ParameterBinding, ...] = Field(
        default=(), description="With `program`: one binding per program parameter."
    )
    shots: int = Field(
        default=1, ge=1, description="Repetitions of the sequence per pixel (innermost loop)."
    )
    reduce: dict[str, Reduction] = Field(
        default_factory=dict,
        description=(
            "Per result name: 'keep' every shot (adds a 'shot' dimension when shots > 1), or reduce on "
            "the sequencer by 'mean' or 'sum'. Default keep."
        ),
    )

    @model_validator(mode="after")
    def _consistent(self) -> "SequencerStage":
        if (self.sequence is None) == (self.program is None):
            raise ValueError("stage needs exactly one of sequence or program")
        if len(set(self.axes)) != len(self.axes):
            raise ValueError("stage axes must be unique")
        if self.sequence is not None:
            if self.parameters:
                raise ValueError("parameters bind a program; a sequence is bound through bindings")
            symbols = self.sequence.symbols()
            bound = [b.symbol for b in self.bindings]
            if len(set(bound)) != len(bound):
                raise ValueError("each symbol is bound once")
            unknown = set(bound) - set(symbols)
            if unknown:
                raise ValueError(f"bindings name unknown symbols {sorted(unknown)}")
            unbound = set(symbols) - set(bound)
            if unbound:
                raise ValueError(f"symbols {sorted(unbound)} are unbound")
            results = set(self.sequence.results())
        else:
            if self.bindings:
                raise ValueError("bindings bind a sequence; a program is bound through parameters")
            names = [b.parameter for b in self.parameters]
            if set(names) != {p.name for p in self.program.parameters} or len(set(names)) != len(
                names
            ):
                raise ValueError("parameters must bind every program parameter exactly once")
            results = {r.name for r in self.program.results}
        unknown = set(self.reduce) - results
        if unknown:
            raise ValueError(f"reduce names unknown results {sorted(unknown)}")
        return self

    def results(self) -> tuple[str, ...]:
        return (
            self.sequence.results()
            if self.sequence
            else tuple(r.name for r in self.program.results)
        )

    def reduction(self, result: str) -> Reduction:
        return self.reduce.get(result, "keep")


class SweepDefinition(QdtModel):
    """An experiment as data: axes outer to inner, what is sensed, what a sequencer runs, how often."""

    name: str = Field(min_length=1, description="Human-readable name.")
    axes: tuple[SweepAxis, ...] = Field(default=(), description="Swept axes, outer to inner.")
    sensed: tuple[SensedLevel, ...] = Field(
        default=(), description="Levels sensed at every stepped point."
    )
    stage: SequencerStage | None = Field(default=None, description="Sequencer-run inner part.")
    repeats: int | None = Field(
        default=1,
        ge=1,
        description=(
            "Outermost loop, run by the executor: repeat the whole scan this many times (None = until "
            "stopped). Adds a 'repeat' dimension when not 1; never averaged by the executor (ADR 0018)."
        ),
    )
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict, description="Free-form scalar metadata."
    )

    @model_validator(mode="after")
    def _consistent(self) -> "SweepDefinition":
        names = [a.name for a in self.axes]
        if len(set(names)) != len(names):
            raise ValueError("axis names must be unique")
        if not self.sensed and self.stage is None:
            raise ValueError("a sweep senses something or runs a stage")
        stage_axes = self.stage.axes if self.stage else ()
        if stage_axes and tuple(names[len(names) - len(stage_axes) :]) != tuple(stage_axes):
            raise ValueError(f"stage axes {stage_axes} must be the innermost axes, in order")
        stepped = [a for a in self.axes if a.name not in stage_axes]
        if self.sensed and not stepped and self.repeats == 1:
            raise ValueError(
                "sensed levels need a stepped axis or repeats != 1 to be laid out over"
            )
        reserved = {"repeat", "shot"}
        var_names = [s.name for s in self.sensed] + list(self.stage.results() if self.stage else ())
        clash = reserved & (set(var_names) | set(names))
        if clash:
            raise ValueError(f"{sorted(clash)} are reserved dimension names")
        if len(set(var_names)) != len(var_names) or set(var_names) & set(names):
            raise ValueError("sensed and result names must be unique and distinct from axis names")
        axis_channels = {a.channel for a in stepped}
        if axis_channels & {s.channel for s in self.sensed}:
            raise ValueError("a channel is a stepped axis or a sensed level, not both (ADR 0016)")
        if self.stage:
            for b in self.stage.bindings:
                if b.axis is not None and b.axis not in names:
                    raise ValueError(f"binding of {b.symbol!r} names unknown axis {b.axis!r}")
            for p in self.stage.parameters:
                if p.axis is not None and p.axis not in names:
                    raise ValueError(f"parameter {p.parameter!r} names unknown axis {p.axis!r}")
            for a in stage_axes:
                bound = [b for b in self.stage.bindings if b.axis == a] + [
                    p for p in self.stage.parameters if p.axis == a and p.source == "axis_num"
                ]
                if not bound:
                    raise ValueError(f"stage axis {a!r} is not bound to any symbol or parameter")
        return self

    def axis(self, name: str) -> SweepAxis:
        for a in self.axes:
            if a.name == name:
                return a
        raise KeyError(f"unknown axis {name!r}")

    def stage_axes(self) -> tuple[SweepAxis, ...]:
        return tuple(self.axis(n) for n in (self.stage.axes if self.stage else ()))

    def stepped_axes(self) -> tuple[SweepAxis, ...]:
        inner = set(self.stage.axes) if self.stage else set()
        return tuple(a for a in self.axes if a.name not in inner)


class ResolvedChannel(QdtModel):
    """A logical channel bound to its instrument, physical channel and the role the plan uses it in."""

    logical: str = Field(description="Logical channel name.")
    instrument: str = Field(description="Instrument id.")
    channel: str = Field(description="Vendor channel identifier.")
    quantity: Quantity = Field(description="Declared quantity (unit of every value on it).")
    settle_s: float = Field(description="Settle time after a level change.")
    integration_s: float | None = Field(description="Sensing aperture; None = instrument default.")
    role: Capability = Field(description="Protocol the executor uses this channel through.")


class ExecutionPlan(QdtModel):
    """A SweepDefinition compiled against a stand: resolved, serializable, the record of what runs.

    Structural, not unrolled: the executor walks it (ADR 0019).
    """

    plan_id: str = Field(min_length=1, description="Unique id; also the Dataset id.")
    definition: SweepDefinition = Field(description="The experiment this plan was compiled from.")
    stand_id: str = Field(description="Stand it was compiled against.")
    dataset: Dataset = Field(
        description="The Dataset the run fills; coordinates are exact (ADR 0015)."
    )
    channels: tuple[ResolvedChannel, ...] = Field(
        description="Every logical channel used, resolved."
    )
    stage_program: SequencerProgram | None = Field(
        default=None, description="The program the stage runs (emitted or hand-written)."
    )
    stage_parameters: tuple[ParameterBinding, ...] = Field(
        default=(), description="How each program parameter is computed at run time."
    )
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict, description="Free-form scalar metadata, e.g. emitter version."
    )

    def channel(self, logical: str) -> ResolvedChannel:
        for c in self.channels:
            if c.logical == logical:
                return c
        raise KeyError(f"unknown logical channel {logical!r}")
