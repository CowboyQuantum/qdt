"""WaveformSense conformance. Test names are the spec; drivers must pass these unchanged.

The oracle is ADR 0015: records land exactly on the declared time grid, one whole record per frame.
"""

from datetime import UTC, datetime

import numpy as np
import pytest

from qdt_lab.protocols import WaveformSense
from qdt_lab.stream import Source, assemble
from qdt_schemas.data import (
    Dataset,
    DataVariable,
    Dimension,
    LinearCoordinate,
    SourceDescriptor,
    StreamedCoordinate,
)

N_RECORDS, N_SAMPLES = 4, 256


def records(n_records: int | None = N_RECORDS, declared_axis: bool = True) -> Dataset:
    coord = (
        LinearCoordinate(name="time", dim="t", unit="s", start=-1e-7, stop=9e-7, num=N_SAMPLES)
        if declared_axis
        else StreamedCoordinate(name="time", dim="t", unit="s")
    )
    return Dataset(
        dataset_id="records",
        name="records",
        dims=(Dimension(name="record", size=n_records), Dimension(name="t", size=N_SAMPLES)),
        coords=(coord,),
        data_vars=(DataVariable(name="voltage", dims=("record", "t"), unit="V", dtype="float64"),),
        source=SourceDescriptor(kind="simulation"),
        created_at=datetime(2026, 10, 12, tzinfo=UTC),
    )


def test_backend_satisfies_protocol(waveform_sense):
    assert isinstance(waveform_sense, WaveformSense)


def test_arm_returns_a_source_for_the_given_dataset(waveform_sense):
    ds = records()
    src = waveform_sense.arm("ch00", ds, "voltage")
    assert isinstance(src, Source)
    assert src.dataset == ds


def test_records_land_whole_on_the_declared_grid(waveform_sense):
    ds = records()
    frames = list(waveform_sense.arm("ch00", ds, "voltage").frames())
    for f in frames:
        t = next(s for s in f.chunk.region if s.dim == "t")
        assert (t.start, t.stop) == (0, N_SAMPLES), "a frame carries a whole record"
    out = assemble(ds, frames)
    assert out["voltage"].shape == (N_RECORDS, N_SAMPLES)
    assert not np.isnan(out["voltage"].values).any(), "every declared record was filled"
    np.testing.assert_allclose(out["time"].values, np.linspace(-1e-7, 9e-7, N_SAMPLES))


def test_last_frame_is_final(waveform_sense):
    frames = list(waveform_sense.arm("ch00", records(), "voltage").frames())
    assert frames[-1].chunk.final
    assert not any(f.chunk.final for f in frames[:-1])


def test_arm_rejects_a_variable_without_a_declared_time_axis(waveform_sense):
    with pytest.raises(ValueError):
        waveform_sense.arm("ch00", records(declared_axis=False), "voltage")


def test_arm_rejects_an_unknown_variable(waveform_sense):
    with pytest.raises(ValueError):
        waveform_sense.arm("ch00", records(), "current")
