"""InfiniiVision driver on its emulator: what `arm` sets beyond the grid (ADR 0063)."""

from datetime import UTC, datetime

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
