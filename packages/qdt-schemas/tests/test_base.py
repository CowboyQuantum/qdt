import pytest
from pydantic import ValidationError

from qdt_schemas._base import QdtModel
from qdt_schemas.stand import ChannelMap


def test_channel_map_round_trips():
    m = ChannelMap(logical="gate_L", instrument="qdac0", channel="ch03")
    assert ChannelMap.model_validate_json(m.model_dump_json()) == m
    assert m.schema_version == 1


def test_models_are_frozen_and_strict():
    m = ChannelMap(logical="a", instrument="b", channel="c")
    with pytest.raises(ValidationError):
        m.logical = "x"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ChannelMap(logical="a", instrument="b", channel="c", extra="no")  # type: ignore[call-arg]
    assert issubclass(ChannelMap, QdtModel)
