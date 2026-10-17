"""InfiniiVision driver on its emulator: what `arm` sets beyond the grid (ADR 0063)."""

from datetime import UTC, datetime

import numpy as np

from qdt_lab.drivers.keysight.infiniivision import EXT_TRIGGER_LEVEL_V, InfiniiVisionX
from qdt_lab.drivers.keysight.infiniivision_emulator import InfiniiVisionEmulator, emulated
from qdt_schemas.data import Dataset, DataVariable, Dimension, LinearCoordinate, SourceDescriptor
from qdt_schemas.stand import ChannelMap, InstrumentConfig


def record_dataset() -> Dataset:
    return Dataset(
        dataset_id="r",
        name="r",
        dims=(Dimension(name="record", size=1), Dimension(name="time", size=100)),
        coords=(
            LinearCoordinate(name="time", dim="time", unit="s", start=0.0, stop=1e-3, num=100),
        ),
        data_vars=(DataVariable(name="v", dims=("record", "time"), unit="V", dtype="float64"),),
        source=SourceDescriptor(kind="live", label="r"),
        created_at=datetime(2026, 10, 16, tzinfo=UTC),
    )


def test_a_scope_with_a_trigger_line_arms_on_its_external_input_and_leaves_the_rest_alone():
    plain = emulated()
    list(plain.arm("ch00", record_dataset(), "v").frames())
    assert plain._t.trigger == {}  # no line: the trigger is the user's (ADR 0047)

    channels = (ChannelMap(logical="ch00", instrument="scope0", channel="1", quantity="voltage"),)
    triggered = InfiniiVisionX(InfiniiVisionEmulator(), channels, external_trigger_level_v=1.5)
    list(triggered.arm("ch00", record_dataset(), "v").frames())
    assert triggered._t.trigger == {
        ":TRIGger:MODE": "EDGE",
        ":TRIGger:EDGE:SOURce": "EXTernal",
        ":TRIGger:EDGE:SLOPe": "POSitive",
        ":TRIGger:EDGE:LEVel": "1.5",
        ":TRIGger:SWEep": "NORMal",
    }


def test_from_config_reads_the_trigger_line_and_its_level(monkeypatch):
    made = {}

    def fake_open(address, **kw):
        made["address"] = address
        return InfiniiVisionEmulator()

    monkeypatch.setattr("qdt_lab.drivers.keysight.infiniivision.open_visa", fake_open)
    inst = InstrumentConfig(
        id="scope0",
        backend="infiniivision",
        capabilities=("waveform_sense",),
        settings={"address": "TCPIP::x::5025::SOCKET", "trigger_from": "scope_trigger"},
    )
    assert InfiniiVisionX.from_config(inst, ()).external_trigger_level_v == EXT_TRIGGER_LEVEL_V
    with_level = inst.model_copy(update={"settings": {**inst.settings, "trigger_level_v": 0.8}})
    assert InfiniiVisionX.from_config(with_level, ()).external_trigger_level_v == 0.8
    untriggered = inst.model_copy(update={"settings": {"address": inst.settings["address"]}})
    assert InfiniiVisionX.from_config(untriggered, ()).external_trigger_level_v is None


def _records(n: int) -> Dataset:
    return record_dataset().model_copy(
        update={"dims": (Dimension(name="record", size=n), Dimension(name="time", size=100))}
    )


def _data_queries(em) -> int:
    return sum(c == ":WAVeform:DATA?" for c in em.log)


def test_several_records_are_one_segmented_acquisition_read_in_one_transfer():
    """ADR 0063, 0065: one `:SINGle` catches every trigger in hardware, and every segment comes back in
    one `:WAVeform:DATA?`. An instrument without the mode falls back to one `:SINGle` per record. Never
    `:DIGitize`."""
    scope = emulated()
    frames = list(scope.arm("ch00", _records(4), "v").frames())
    em = scope._t
    assert len(frames) == 4 and em.singles == 1 and em.acquire_mode == "SEGM"
    assert em.segment_count == 4
    assert _data_queries(em) == 1 and scope.segments_in_one_transfer is True
    assert not any(c.startswith(":ACQuire:SEGMented:INDex") for c in em.log)
    assert em.log[-1] == ":WAVeform:SEGMented:ALL OFF"  # the scope is left reading one segment
    assert not any(c.startswith(":DIGitize") for c in em.log)
    assert [f.chunk.region[0].start for f in frames] == [0, 1, 2, 3]

    plain = emulated(segmented=False)
    frames = list(plain.arm("ch00", _records(3), "v").frames())
    assert len(frames) == 3 and plain._t.singles == 3 and plain._t.acquire_mode == "RTIM"
    assert not any(c.startswith(":WAVeform:SEGMented") for c in plain._t.log)

    one = emulated()
    list(one.arm("ch00", _records(1), "v").frames())
    assert one._t.singles == 1 and one._t.acquire_mode == "RTIM"  # a single record stays real-time
    assert one.segments_in_one_transfer is None  # nothing segmented was read


def test_one_transfer_gives_the_records_the_segments_read_one_by_one_give():
    """The bench oracle in software: split the one block and read each segment by index, same values."""
    scope = emulated()
    source = scope.arm("ch00", _records(5), "v")
    together = np.stack([f.arrays["v"][0] for f in source.frames()])
    one_by_one = np.stack([source.record(k + 1) for k in range(5)])
    np.testing.assert_array_equal(together, one_by_one)
    assert (
        len({row.tobytes() for row in together}) == 5
    )  # five different records, not one five times


def test_a_scope_without_the_one_transfer_readout_is_read_segment_by_segment_and_asked_once():
    scope = emulated(all_segments=False)
    frames = list(scope.arm("ch00", _records(3), "v").frames())
    em = scope._t
    assert len(frames) == 3 and scope.segments_in_one_transfer is False
    assert [c for c in em.log if c.startswith(":ACQuire:SEGMented:INDex")] == [
        f":ACQuire:SEGMented:INDex {k}" for k in (1, 2, 3)
    ]
    list(scope.arm("ch00", _records(3), "v").frames())
    assert sum(c == ":WAVeform:SEGMented:ALL ON" for c in em.log) == 1  # decided once


def test_a_block_of_the_wrong_length_is_not_split_and_the_segments_are_read_one_by_one():
    """A scope that accepts the command but returns one segment's worth must not be cut into pieces of
    it: the block is checked against records × the preamble's points."""
    scope = emulated()
    em = scope._t
    em.query_block = lambda command, dtype: (em.log.append(command), em._served()[2].copy())[1]
    frames = list(scope.arm("ch00", _records(4), "v").frames())
    assert len(frames) == 4 and scope.segments_in_one_transfer is False
    assert sum(c.startswith(":ACQuire:SEGMented:INDex") for c in em.log) == 4
