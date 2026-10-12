"""Capability protocols. Instruments are described by what they can do, not what they are (ADR 0016).

Names follow two axes: direction (`Source` applies a value to a terminal, `Sense` reads one) and time
structure (`Level` is a value held until changed, `Waveform` is a value over a time axis). `Sequencer` is
the one non-terminal protocol: it runs a compiled, self-clocked program and streams positional results.

    LevelSource     set a level on a terminal, read back the setpoint      (QDAC, SMU)
    LevelSense      sense a level on a terminal                             (SMU, DMM, QDAC-II current readout)
    WaveformSource  play a waveform on a terminal                            (AWG, OPX output)
    WaveformSense   arm a terminal to fill a declared record Dataset         (scope, OPX input)
    Sequencer       compile once, run with int parameters into a Dataset     (OPX)

A driver implements every protocol its instrument honours (an SMU is a LevelSource and a LevelSense on
the same terminal; `get` returns what was applied, `sense` what is measured). The physical quantity
(voltage, current) is a property of the channel, declared in `qdt_schemas.stand.ChannelMap` together
with settle and integration times, not of the method: values are floats in that quantity's SI unit.

Anything that produces arrays (`WaveformSense`, `Sequencer`) is given the `Dataset` it must fill and
returns a stream `Source` for it (ADR 0017): declared coordinates are exact and meeting them is the
producer's job (ADR 0015). Each protocol has a Simulated* twin in ../simulated and is covered by the
single conformance suite in tests/.
"""

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

import numpy as np

from qdt_schemas.activity import SequencerProgram
from qdt_schemas.data import Dataset

from ..stream.source import Source


@runtime_checkable
class LevelSource(Protocol):
    """A terminal that holds a settable level (a DC gate on a QDAC, an SMU source terminal)."""

    def set(self, channel: str, value: float) -> None:
        """Apply `value` (SI unit of the channel's declared quantity) and hold it until changed."""
        ...

    def get(self, channel: str) -> float:
        """Return the setpoint currently applied to `channel` (not a measurement of the load)."""
        ...


@runtime_checkable
class LevelSense(Protocol):
    """A terminal that senses a level (an SMU measure terminal, a DMM input, a QDAC-II current readout)."""

    def sense(self, channel: str) -> float:
        """Measure the level on `channel` (SI unit of its declared quantity), honouring the channel's
        integration time; the caller honours its settle time."""
        ...


@runtime_checkable
class WaveformSource(Protocol):
    """A terminal that plays a waveform (an AWG channel, an OPX analog output)."""

    def play(self, channel: str, samples: np.ndarray, sample_rate: float) -> None:
        """Play the 1-D `samples` (SI unit of the channel's declared quantity) at `sample_rate` Hz."""
        ...

    def stop(self, channel: str) -> None:
        """Stop playing on `channel`; idempotent."""
        ...


@runtime_checkable
class WaveformSense(Protocol):
    """A terminal that captures time-resolved records (a scope channel, an OPX analog input)."""

    def arm(self, channel: str, dataset: Dataset, variable: str) -> Source:
        """Arm `channel` to fill `variable` of `dataset`, whose dims are (record, time) with a
        `LinearCoordinate` on the time dim. Returns the `Source` that yields one whole record per
        frame on that grid; the backend aligns or resamples, never the consumer (ADR 0015).
        Raises ValueError when the variable has no declared time axis."""
        ...


@runtime_checkable
class CompiledProgram(Protocol):
    """A backend's handle to a compiled `SequencerProgram`; carries the program it was compiled from."""

    program: SequencerProgram


@runtime_checkable
class Sequencer(Protocol):
    """A self-clocked program runner (an OPX): compile once, run many times with integer parameters."""

    def compile(self, program: SequencerProgram) -> CompiledProgram:
        """Compile `program` once; raises ValueError for a backend this sequencer does not run."""
        ...

    def run(
        self, compiled: CompiledProgram, parameters: Mapping[str, int], dataset: Dataset
    ) -> Source:
        """Run `compiled` with integer `parameters` to fill `dataset`. Returns the `Source` of
        positional result frames. Raises ValueError unless `compiled.program.check_run` passes."""
        ...
