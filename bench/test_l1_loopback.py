"""L1 loopbacks (`docs/BENCH.md`): a source instrument drives a known level into a sink instrument,
through the real drivers and the protocols, and the sink reads it back within the tolerance the
datasheets allow. Numbers come from the datasheets; no site tolerance is written here (rule 7).

QDAC ch N → scope ch 1. The scope reads a DC level as the mean of one captured record. Its datasheet
(InfiniiVision HD3, "Performance characteristics") gives the single-cursor DC voltage measurement
accuracy as ± [DC gain accuracy + offset accuracy + 0.08 % full scale] with

    DC vertical gain accuracy   ±1.5 % of full scale          (warranted)
    DC vertical offset accuracy ±0.1 div ± 1 mV ± 1.5 % of the offset setting
    full scale                  8 vertical divisions

The QDAC-II's 20-bit, calibrated DC output contributes microvolts against that and is not budgeted.
The channel the loopback cable is on comes from `QDT_L1_QDAC_CHANNEL` (default `ch01`).
"""

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_lab.stream import assemble
from qdt_schemas.data import (
    Dataset,
    DataVariable,
    Dimension,
    LinearCoordinate,
    SourceDescriptor,
)


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

SETTLE_S = 0.05
"""Wait after a level change before capturing (QDAC-II output filter HIGH settles in well under this)."""

RECORD_SPAN_S, RECORD_SAMPLES = 1e-3, 1000


def dc_measurement_tolerance(ch: ScopeChannel) -> float:
    """± volts within which the scope's mean of a DC level must agree with the applied level."""
    return (
        GAIN_ACCURACY * ch.full_scale_v
        + OFFSET_ACCURACY_DIV * ch.volts_per_div
        + OFFSET_ACCURACY_FIXED_V
        + OFFSET_ACCURACY_OF_SETTING * abs(ch.offset_v)
        + MEASUREMENT_TERM * ch.full_scale_v
    )


def one_record() -> Dataset:
    """One record of `RECORD_SAMPLES` samples over `RECORD_SPAN_S`, on a declared grid (ADR 0015)."""
    return Dataset(
        dataset_id="l1-dc",
        name="l1-dc",
        dims=(Dimension(name="record", size=1), Dimension(name="t", size=RECORD_SAMPLES)),
        coords=(
            LinearCoordinate(
                name="time", dim="t", unit="s", start=0.0, stop=RECORD_SPAN_S, num=RECORD_SAMPLES
            ),
        ),
        data_vars=(DataVariable(name="voltage", dims=("record", "t"), unit="V", dtype="float64"),),
        source=SourceDescriptor(kind="live"),
        created_at=datetime.now(UTC),
    )


def read_dc(scope, channel: str) -> float:
    """The mean of one captured record on `channel`, through the `WaveformSense` protocol."""
    ds = one_record()
    out = assemble(ds, scope.arm(channel, ds, "voltage").frames())
    return float(np.mean(out["voltage"].values))


SCOPE_CH1 = ScopeChannel(number=1, volts_per_div=0.5)
LEVELS_V = (0.0, 0.5, -0.5, 1.5, -1.5)


@pytest.mark.parametrize("level", LEVELS_V)
def test_qdac_level_is_read_back_by_the_scope_within_datasheet_accuracy(
    qdac, scope, scope_front_panel, level
):
    qdac_channel = os.environ.get("QDT_L1_QDAC_CHANNEL", "ch01")
    scope_front_panel(
        SCOPE_CH1.number,
        SCOPE_CH1.volts_per_div,
        SCOPE_CH1.offset_v,
        SCOPE_CH1.coupling,
        SCOPE_CH1.impedance,
    )
    tol = dc_measurement_tolerance(SCOPE_CH1)
    try:
        qdac.set(qdac_channel, level)
        time.sleep(SETTLE_S)
        read = read_dc(scope, "ch1")
    finally:
        qdac.set(qdac_channel, 0.0)
    assert abs(read - level) <= tol, (
        f"QDAC {qdac_channel} set {level:+.3f} V, scope ch1 mean {read:+.4f} V, "
        f"tolerance ±{tol:.4f} V at {SCOPE_CH1.volts_per_div} V/div"
    )
