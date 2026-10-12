"""Step 2 schema slice: stand configuration. Frozen only after Step 2's test ladder passes."""

from typing import Literal

from pydantic import Field

from ._base import QdtModel


class ChannelMap(QdtModel):
    """Maps a logical channel name to a physical instrument channel."""

    logical: str = Field(description="Logical name used by experiments, e.g. 'gate_L'.")
    instrument: str = Field(description="Instrument id as declared in StandConfig.instruments.")
    channel: str = Field(description="Vendor channel identifier, e.g. 'ch03'.")
    quantity: Literal["voltage", "current"] = Field(
        description="Physical quantity a level on this channel is expressed in; protocol calls use its SI unit (V or A). ADR 0016."
    )
