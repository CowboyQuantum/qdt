"""Step 2 schema slice: activity — what an experiment asks a stand to do. Frozen only after Step 2's
test ladder passes.

`SequencerProgram` (ADR 0017) is the envelope the executor hands to a `Sequencer`: a typed contract
(runtime parameters, result streams) around an opaque program body. The executor and a simulated
sequencer validate names, integer parameters and result shapes from the envelope alone; only the real
driver reads the body. Probe 01 (ADR 0015) fixed the constraints the envelope encodes: one compiled
program, runtime parameters as integers (fractional values as scaled integers), positional results with
no in-band coordinates.

`SweepDefinition` and `ExecutionPlan` join this module when the compiler consumes them.
"""

from collections.abc import Mapping

from pydantic import Field, model_validator

from ._base import QdtModel
from .data import AttrValue, Dataset, DType


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
