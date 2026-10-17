"""The scope reads every segment of an acquisition in one transfer (ADR 0063, 0065's follow-on).

One segmented acquisition of `RECORDS` records on input 1, triggered by the driver's AUTO force (nothing
need be cabled), is read twice: in one transfer (`:WAVeform:SEGMented:ALL`) and segment by segment
(`:ACQuire:SEGMented:INDex`). The two must give the same records, value for value, and the one transfer
must be the faster: segment by segment cost 0.3–0.5 s each on the HD3 (Probe 05). `QDT_SCOPE_ADDRESS`.
"""

import time
from datetime import UTC, datetime

import numpy as np

from qdt_schemas.data import Dataset, DataVariable, Dimension, LinearCoordinate, SourceDescriptor

RECORDS, POINTS = 10, 200


def _records() -> Dataset:
    return Dataset(
        dataset_id="segments",
        name="segments",
        dims=(Dimension(name="record", size=RECORDS), Dimension(name="time", size=POINTS)),
        coords=(
            LinearCoordinate(name="time", dim="time", unit="s", start=0.0, stop=1e-3, num=POINTS),
        ),
        data_vars=(DataVariable(name="v", dims=("record", "time"), unit="V", dtype="float64"),),
        source=SourceDescriptor(kind="live", label="segments"),
        created_at=datetime.now(UTC),
    )


def test_segments_read_in_one_transfer_equal_the_segments_read_one_by_one(scope, scope_front_panel):
    scope_front_panel(
        1, 0.05, 0.0, trigger_level_v=0.02
    )  # AUTO sweep: the driver forces what does not come
    source = scope.arm("ch1", _records(), "v")
    source.acquire()
    t0 = time.perf_counter()
    together = source.segments()
    one_transfer_s = time.perf_counter() - t0
    assert together is not None and scope.segments_in_one_transfer is True, (
        "the scope refused :WAVeform:SEGMented:ALL or returned another layout; segments stay read one by one"
    )
    t0 = time.perf_counter()
    one_by_one = [source.record(k + 1) for k in range(RECORDS)]
    by_index_s = time.perf_counter() - t0
    np.testing.assert_array_equal(np.stack(together), np.stack(one_by_one))
    assert len({r.tobytes() for r in together}) == RECORDS, (
        "ten different records, not one ten times"
    )
    print(
        f"one transfer {one_transfer_s:.2f} s; one by one {by_index_s:.2f} s ({by_index_s / RECORDS:.2f} s each)"
    )
    assert one_transfer_s < by_index_s
