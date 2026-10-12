import pytest
from pydantic import ValidationError

from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig


def stand() -> StandConfig:
    return StandConfig(
        stand_id="sim-stand",
        instruments=(
            InstrumentConfig(id="dac0", backend="simulated", capabilities=("level_source",)),
            InstrumentConfig(id="seq0", backend="simulated", capabilities=("sequencer",)),
        ),
        channels=(
            ChannelMap(logical="gate_R", instrument="dac0", channel="ch00", quantity="voltage"),
            ChannelMap(logical="gate_L", instrument="seq0", channel="ao1", quantity="voltage"),
        ),
    )


def test_round_trip():
    s = stand()
    assert StandConfig.model_validate_json(s.model_dump_json()) == s
    assert s.channel("gate_L").instrument == "seq0"
    assert s.instrument("seq0").capabilities == ("sequencer",)


def test_channel_must_map_to_a_declared_instrument():
    with pytest.raises(ValidationError, match="unknown instrument"):
        StandConfig(
            stand_id="s",
            instruments=(
                InstrumentConfig(id="a", backend="simulated", capabilities=("level_source",)),
            ),
            channels=(ChannelMap(logical="g", instrument="b", channel="c", quantity="voltage"),),
        )


def test_names_unique():
    with pytest.raises(ValidationError, match="unique"):
        StandConfig(
            stand_id="s",
            instruments=(
                InstrumentConfig(id="a", backend="simulated", capabilities=("level_source",)),
                InstrumentConfig(id="a", backend="simulated", capabilities=("level_source",)),
            ),
            channels=(ChannelMap(logical="g", instrument="a", channel="c", quantity="voltage"),),
        )
