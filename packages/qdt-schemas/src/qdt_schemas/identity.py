"""Step 3 schema slice: identity — what a measurement is *of* (ADR 0025). Frozen by ADR 0028.

`DeviceRecord`: Step 3's exit query is by device, stand and definition, and the stand and definition
already exist as Step 2 objects. `DeviceLayout` (ADR 0089, Step 6c): a device's gates seen from above,
which Flight Deck's Device widget draws to scale; served by the stand server, never stored. Further
identity families (assets, baselines, ...) enter in the step that first consumes them, each with an ADR
that defines it (plan §4.1).
"""

from typing import Annotated

from pydantic import AwareDatetime, Field, model_validator

from ._base import QdtModel
from .data import AttrValue


class DeviceRecord(QdtModel):
    """A device under test (or a simulated one) that measurements are recorded against."""

    device_id: str = Field(
        min_length=1,
        description=(
            "Stable id chosen when the device is registered, e.g. 'sim-double-dot'. Generic in this repo; "
            "site-specific naming lives in the internal extension (rule 7)."
        ),
    )
    kind: str = Field(
        min_length=1, description="Device type, e.g. 'double_dot'; free text, used for filtering."
    )
    simulated: bool = Field(description="True for a model behind a simulated backend (qdt-sim).")
    description: str = Field(default="", description="Human-readable notes.")
    attrs: dict[str, AttrValue] = Field(
        default_factory=dict, description="Free-form scalar metadata, e.g. model parameters."
    )
    registered_at: AwareDatetime = Field(description="When the device was first registered.")


Rect = Annotated[tuple[float, ...], Field(min_length=4, max_length=4)]
"""A rectangle in nanometres: (x_min, x_max, y_min, y_max). Written as a sized `tuple[float, ...]`, not
a fixed tuple, so the generated TypeScript types keep its element type."""
Point = Annotated[tuple[float, ...], Field(min_length=2, max_length=2)]
"""A point in nanometres: (x, y)."""


def _check_rect(rect: Rect | None, name: str) -> None:
    if rect is not None and not (rect[0] < rect[1] and rect[2] < rect[3]):
        raise ValueError(f"{name} must be (x_min, x_max, y_min, y_max) with min < max, got {rect}")


class GateOutline(QdtModel):
    """One gate electrode of a device, seen from above (ADR 0089)."""

    name: str = Field(min_length=1, description="The device's name for the gate.")
    role: str = Field(
        min_length=1,
        description=(
            "What the gate does, as the layout names it ('gate' when the layout does not say); free "
            "text, used for labels."
        ),
    )
    channel: str | None = Field(
        description=(
            "The stand's logical channel that sets this gate's voltage (`ChannelMap.logical`); null "
            "when the stand wires none."
        ),
    )
    polygon_nm: tuple[Point, ...] = Field(
        min_length=3,
        description=(
            "The gate's outline as (x, y) vertices in nanometres, in order, in the layout's own frame "
            "(y up). Approximate: what the device's layout declares, not a lithography file."
        ),
    )


class DeviceLayout(QdtModel):
    """A device's gates seen from above, to scale (ADR 0089): what the Device widget draws, coloured by
    the voltage each gate sits at. Served by `GET /device/layout`; never stored."""

    device_id: str = Field(
        min_length=1, description="The device this layout is of (`DeviceRecord`)."
    )
    material: str = Field(
        default="", description="The heterostructure, e.g. 'SiGe' or 'MOS'; empty when unknown."
    )
    gates: tuple[GateOutline, ...] = Field(min_length=1, description="Every gate, in layout order.")
    channel_nm: Rect | None = Field(
        default=None,
        description=(
            "The conducting channel under the gates, as (x_min, x_max, y_min, y_max) in nanometres; "
            "null when the layout does not give it."
        ),
    )
    sensor_nm: Rect | None = Field(
        default=None,
        description=(
            "The sensing element's region, as (x_min, x_max, y_min, y_max) in nanometres; null when "
            "the layout does not give it."
        ),
    )
    source: str = Field(
        default="",
        description=(
            "Where the layout comes from, e.g. 'Phantom 0.2.0, device file two-dot-sige-a'; shown "
            "under the diagram."
        ),
    )

    @model_validator(mode="after")
    def _well_formed(self) -> "DeviceLayout":
        names = [g.name for g in self.gates]
        if len(set(names)) != len(names):
            raise ValueError(f"gate names repeat: {names}")
        _check_rect(self.channel_nm, "channel_nm")
        _check_rect(self.sensor_nm, "sensor_nm")
        return self
