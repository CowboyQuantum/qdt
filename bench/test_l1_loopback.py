"""L1 loopbacks (`docs/BENCH.md`): a source instrument drives a known level into a sink instrument,
through the real drivers and the protocols, and the sink reads it back within the tolerance the
datasheets allow. Numbers come from the datasheets; no site tolerance is written here (rule 7).

DC rows: QDAC ch N → scope, SMU → scope. One cable is moved between sources, so `QDT_L1_DC_SOURCES`
(comma list, default `qdac,smu`) says which are cabled; the others skip. The scope input is
`QDT_L1_SCOPE_CHANNEL` (default 1); the QDAC channel is `QDT_L1_QDAC_CHANNEL` (default `ch01`).

The scope reads a DC level as the mean of one captured record. Its datasheet (InfiniiVision HD3,
"Performance characteristics") gives the single-cursor DC voltage measurement accuracy as
± [DC gain accuracy + offset accuracy + 0.08 % full scale] with

    DC vertical gain accuracy   ±1.5 % of full scale          (warranted)
    DC vertical offset accuracy ±0.1 div ± 1 mV ± 1.5 % of the offset setting
    full scale                  8 vertical divisions

Source errors are not budgeted against that: the QDAC-II's 20-bit calibrated DC output is microvolts;
the 2450's voltage source accuracy is ±(0.015 % + 300 µV) on its 2 V range and ±(0.015 % + 2.4 mV) on
20 V (Keithley 2450 datasheet), also well inside.
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


SCOPE_CHANNEL = ScopeChannel(
    number=int(os.environ.get("QDT_L1_SCOPE_CHANNEL", "1")), volts_per_div=0.5
)
LEVELS_V = (0.0, 0.5, -0.5, 1.5, -1.5)
DC_SOURCES = {
    "qdac": lambda: os.environ.get("QDT_L1_QDAC_CHANNEL", "ch01"),
    "smu": lambda: "out",
}


def _cabled() -> set[str]:
    return {s.strip() for s in os.environ.get("QDT_L1_DC_SOURCES", "qdac,smu").split(",") if s}


@pytest.mark.parametrize("source", sorted(DC_SOURCES))
@pytest.mark.parametrize("level", LEVELS_V)
def test_dc_level_is_read_back_by_the_scope_within_datasheet_accuracy(request, source, level):
    if source not in _cabled():
        pytest.skip(f"{source} not cabled to the scope (QDT_L1_DC_SOURCES)")
    # fixtures are taken only once the case is known to be cabled, so a skip opens no instrument
    scope = request.getfixturevalue("scope")
    scope_front_panel = request.getfixturevalue("scope_front_panel")
    backend = request.getfixturevalue(source)
    channel = DC_SOURCES[source]()
    ch = SCOPE_CHANNEL
    scope_front_panel(ch.number, ch.volts_per_div, ch.offset_v, ch.coupling, ch.impedance)
    tol = dc_measurement_tolerance(ch)
    try:
        backend.set(channel, level)
        time.sleep(SETTLE_S)
        read = read_dc(scope, f"ch{ch.number}")
    finally:
        backend.set(channel, 0.0)
    assert abs(read - level) <= tol, (
        f"{source} {channel} set {level:+.3f} V, scope ch{ch.number} mean {read:+.4f} V, "
        f"tolerance ±{tol:.4f} V at {ch.volts_per_div} V/div"
    )
