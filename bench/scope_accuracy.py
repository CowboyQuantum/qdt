"""The scope's DC measurement accuracy from its datasheet, shared by the L1 and L2 rows.

InfiniiVision HD3, "Performance characteristics": the single-cursor DC voltage measurement accuracy is
± [DC gain accuracy + offset accuracy + 0.08 % full scale] with

    DC vertical gain accuracy   ±1.5 % of full scale          (warranted)
    DC vertical offset accuracy ±0.1 div ± 1 mV ± 1.5 % of the offset setting
    full scale                  8 vertical divisions

A `ScopeChannel` is an input as a row uses it: the vendor channel number and the vertical settings the
row applies before arming, which the tolerance is computed from. No site tolerance lives here (rule 7).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeChannel:
    """A scope input as the loopback uses it: the vendor channel number and the vertical settings the
    test applies before arming, which the tolerance is computed from."""

    number: int
    volts_per_div: float
    offset_v: float = 0.0
    coupling: str = "DC"
    impedance: str = "ONEMeg"

    @property
    def full_scale_v(self) -> float:
        """8 vertical divisions (the datasheet's definition for accuracy calculations)."""
        return 8 * self.volts_per_div


GAIN_ACCURACY = 0.015
"""DC vertical gain accuracy, fraction of full scale (warranted)."""
OFFSET_ACCURACY_DIV = 0.1
"""DC vertical offset accuracy, in divisions, plus the fixed and proportional terms below."""
OFFSET_ACCURACY_FIXED_V = 1e-3
OFFSET_ACCURACY_OF_SETTING = 0.015
MEASUREMENT_TERM = 0.0008
"""The single-cursor measurement term, fraction of full scale."""


def dc_measurement_tolerance(ch: ScopeChannel) -> float:
    """± volts within which the scope's mean of a DC level must agree with the applied level."""
    return (
        GAIN_ACCURACY * ch.full_scale_v
        + OFFSET_ACCURACY_DIV * ch.volts_per_div
        + OFFSET_ACCURACY_FIXED_V
        + OFFSET_ACCURACY_OF_SETTING * abs(ch.offset_v)
        + MEASUREMENT_TERM * ch.full_scale_v
    )
