"""Step 2 schema slice: stand configuration. Frozen only after Step 2's test ladder passes.

A stand is instruments plus the map from logical channels (what experiments name) to physical ones.
Protocol calls take floats in the SI unit of the channel's declared `quantity` (ADR 0016); settle and
integration times live here too (ADR 0017).
"""

from typing import Literal

from pydantic import Field, model_validator

from ._base import QdtModel
from .data import AttrValue

Capability = Literal[
    "level_source", "level_sense", "waveform_source", "waveform_sense", "sequencer"
]
Quantity = Literal["voltage", "current"]

QUANTITY_UNIT: dict[str, str] = {"voltage": "V", "current": "A"}
"""SI unit per quantity; the unit of every level, pulse level and sensed value on a channel."""


class InstrumentConfig(QdtModel):
    """One instrument of the stand and the capability protocols its driver honours."""

    id: str = Field(
        min_length=1, description="Instrument id, unique within the stand, e.g. 'dac0'."
    )
    backend: str = Field(
        min_length=1,
        description=(
            "Driver / emitter key, e.g. 'simulated', 'qua'. Picks the Emitter for a sequencer and the "
            "driver module for a real instrument."
        ),
    )
    capabilities: tuple[Capability, ...] = Field(
        min_length=1, description="Protocols the driver implements (ADR 0016 names)."
    )
    settings: dict[str, AttrValue] = Field(
        default_factory=dict, description="Driver settings, e.g. address; never site-identifying."
    )


class ChannelMap(QdtModel):
    """Maps a logical channel name to a physical instrument channel."""

    logical: str = Field(description="Logical name used by experiments, e.g. 'gate_L'.")
    instrument: str = Field(description="Instrument id as declared in StandConfig.instruments.")
    channel: str = Field(description="Vendor channel identifier, e.g. 'ch03'.")
    quantity: Quantity = Field(
        description="Physical quantity a level on this channel is expressed in; protocol calls use its SI unit (V or A). ADR 0016."
    )
    settle_s: float = Field(
        default=0.0,
        ge=0,
        description="Seconds the executor waits after changing a level on this channel before sensing through it (ADR 0017).",
    )
    integration_s: float | None = Field(
        default=None,
        gt=0,
        description="Sensing aperture in seconds a LevelSense driver applies on this channel; None means the instrument default (ADR 0017).",
    )


class StandConfig(QdtModel):
    """Instruments and the logical → physical channel map of one measurement stand."""

    stand_id: str = Field(
        min_length=1, description="Stand id; generic, never a site name (rule 7)."
    )
    instruments: tuple[InstrumentConfig, ...] = Field(
        min_length=1, description="Instruments present."
    )
    channels: tuple[ChannelMap, ...] = Field(min_length=1, description="Logical channel map.")
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict, description="Free-form scalar metadata."
    )

    @model_validator(mode="after")
    def _consistent(self) -> "StandConfig":
        ids = [i.id for i in self.instruments]
        if len(set(ids)) != len(ids):
            raise ValueError("instrument ids must be unique")
        names = [c.logical for c in self.channels]
        if len(set(names)) != len(names):
            raise ValueError("logical channel names must be unique")
        for c in self.channels:
            if c.instrument not in ids:
                raise ValueError(
                    f"channel {c.logical!r} maps to unknown instrument {c.instrument!r}"
                )
        return self

    def channel(self, logical: str) -> ChannelMap:
        for c in self.channels:
            if c.logical == logical:
                return c
        raise KeyError(f"unknown logical channel {logical!r}")

    def instrument(self, instrument_id: str) -> InstrumentConfig:
        for i in self.instruments:
            if i.id == instrument_id:
                return i
        raise KeyError(f"unknown instrument {instrument_id!r}")
