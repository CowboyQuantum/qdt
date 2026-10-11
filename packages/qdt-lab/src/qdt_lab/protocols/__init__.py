"""Capability protocols. Instruments are described by what they can do, not what they are.

Step 1 fills these in. Each protocol gets a Simulated* twin in ../simulated and is covered by the
single conformance suite in tests/.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class DCSource(Protocol):
    """A settable DC voltage channel (QDAC channel, SMU source)."""

    def set_voltage(self, channel: str, volts: float) -> None: ...

    def get_voltage(self, channel: str) -> float: ...
