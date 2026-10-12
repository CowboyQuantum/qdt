"""Capability protocols. Instruments are described by what they can do, not what they are (ADR 0016).

Names follow two axes: direction (`Source` applies a value to a terminal, `Sense` reads one) and time
structure (`Level` is a value held until changed, `Waveform` is a value over a time axis). `Sequencer` is
the one non-terminal protocol: it runs a compiled, self-clocked program and streams positional results.

    LevelSource     set a level on a terminal, read back the setpoint      (QDAC, SMU)
    LevelSense      read a level from a terminal                            (SMU, DMM, QDAC-II current readout)
    WaveformSource  play a waveform on a terminal                            (AWG, OPX output)
    WaveformSense   capture a time-resolved record                           (scope, OPX input)
    Sequencer       compile and run a timed program; positional results      (OPX)

A driver implements every protocol its instrument honours (an SMU is a LevelSource and a LevelSense on
the same terminal). The physical quantity (voltage, current) is a property of the channel, declared in
`qdt_schemas.stand.ChannelMap`, not of the method: values are floats in that quantity's SI unit.
Each protocol gets a Simulated* twin in ../simulated and is covered by the single conformance suite in
tests/. The remaining four protocols are added in Step 2 as the executor consumes them.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class LevelSource(Protocol):
    """A terminal that holds a settable level (a DC gate on a QDAC, an SMU source terminal)."""

    def set(self, channel: str, value: float) -> None:
        """Apply `value` (SI unit of the channel's declared quantity) and hold it until changed."""
        ...

    def get(self, channel: str) -> float:
        """Return the setpoint currently applied to `channel` (not a measurement of the load)."""
        ...
