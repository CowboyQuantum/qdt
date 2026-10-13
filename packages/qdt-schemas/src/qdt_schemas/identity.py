"""Step 3 schema slice: identity — what a measurement is *of* (ADR 0025).

Only `DeviceRecord` for now: Step 3's exit query is by device, stand and definition, and the stand and
definition already exist as Step 2 objects. Further identity families (assets, baselines, ...) enter in
the step that first consumes them, each with an ADR that defines it (plan §4.1).
"""

from pydantic import AwareDatetime, Field

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
