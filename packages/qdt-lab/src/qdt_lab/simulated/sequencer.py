"""Simulated sequencer: runs any backend's program by ignoring its body."""

import math
import time
import uuid
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import NamedTuple

import numpy as np

from qdt_schemas.activity import SequencerProgram
from qdt_schemas.data import Dataset, DatasetChunk, IndexSlice

from ..stream.frame import Frame


class CompiledSimulatedProgram(NamedTuple):
    """Handle returned by `SimulatedSequencer.compile`."""

    program: SequencerProgram
    compiled_id: str


class SimulatedSequencer:
    """Every result is filled with its flat loop index, cast to the declared dtype: exactly what the
    Probe 01 program produced on the OPX, so the positional-addressing oracle holds here and on hardware.
    Chunks one slab of the first axis per frame (a line for a 2-D result), the ADR 0015 default."""

    def __init__(self, points_per_second: float | None = None) -> None:
        self.points_per_second = points_per_second

    def compile(self, program: SequencerProgram) -> CompiledSimulatedProgram:
        return CompiledSimulatedProgram(program, uuid.uuid4().hex)

    def run(
        self, compiled: CompiledSimulatedProgram, parameters: Mapping[str, int], dataset: Dataset
    ) -> "_SequencerSource":
        compiled.program.check_run(parameters, dataset)
        return _SequencerSource(self, compiled.program, dict(parameters), dataset)


class _SequencerSource:
    """The `Source` a `SimulatedSequencer.run` returns."""

    def __init__(
        self,
        sequencer: SimulatedSequencer,
        program: SequencerProgram,
        parameters: dict[str, int],
        dataset: Dataset,
    ) -> None:
        self._sequencer, self._program, self._parameters = sequencer, program, parameters
        self.dataset = dataset

    def frames(self) -> Iterator[Frame]:
        variables = {v.name: v for v in self.dataset.data_vars}
        plan = []
        for r in self._program.results:
            shape = self._program.result_shape(r.name, self._parameters)
            plan.extend((r, shape, i) for i in range(shape[0]))
        t0, done = time.perf_counter(), 0
        for seq, (r, shape, i) in enumerate(plan):
            values = np.arange(math.prod(shape), dtype=np.int64).reshape(shape)[i : i + 1]
            done += values.size
            if self._sequencer.points_per_second:
                delay = t0 + done / self._sequencer.points_per_second - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
            dims = variables[r.name].dims
            yield Frame(
                DatasetChunk(
                    dataset_id=self.dataset.dataset_id,
                    seq=seq,
                    region=(
                        IndexSlice(dim=dims[0], start=i, stop=i + 1),
                        *(IndexSlice(dim=d, start=0, stop=n) for d, n in zip(dims[1:], shape[1:])),
                    ),
                    variables=(r.name,),
                    produced_at=datetime.now(UTC),
                    final=seq == len(plan) - 1,
                ),
                {r.name: values.astype(r.dtype)},
            )
