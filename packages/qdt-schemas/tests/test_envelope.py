"""Identity + envelope slice (ADR 0025): validation and content addressing."""

import json
import pathlib
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from qdt_schemas.envelope import MeasurementRecord
from qdt_schemas.identity import DeviceRecord
from qdt_schemas.stand import StandConfig

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def record(**update) -> MeasurementRecord:
    data = json.loads((FIXTURES / "MeasurementRecord" / "v1.json").read_text())
    return MeasurementRecord.model_validate(data | update)


def test_record_round_trips_through_json():
    r = record()
    assert MeasurementRecord.model_validate_json(r.model_dump_json()) == r


@pytest.mark.parametrize(
    "bad", ["123", "0" * 31 + "G", "0" * 33, "00000000-0000-0000-0000-000000000001"]
)
def test_record_id_is_32_lowercase_hex(bad):
    with pytest.raises(ValidationError):
        record(record_id=bad)


def test_finished_cannot_precede_started():
    t = datetime(2026, 10, 13, tzinfo=UTC)
    with pytest.raises(ValidationError, match="precedes"):
        record(started_at=t.isoformat(), finished_at=(t - timedelta(seconds=1)).isoformat())


def test_naive_timestamps_are_refused():
    with pytest.raises(ValidationError):
        record(started_at="2026-10-13T12:00:00", finished_at="2026-10-13T12:00:00")


@pytest.mark.parametrize("path", ["/abs/x.h5", r"\\server\x.h5", r"a\b.h5"])
def test_payload_path_is_relative_and_slash_separated(path):
    data = record().model_dump(mode="json")
    data["payload"]["path"] = path
    with pytest.raises(ValidationError):
        MeasurementRecord.model_validate(data)


def test_device_record_needs_aware_registration_time():
    with pytest.raises(ValidationError):
        DeviceRecord(device_id="d", kind="k", simulated=True, registered_at=datetime(2026, 1, 1))


def test_content_hash_ignores_attr_insertion_order_and_sees_any_change():
    stand = StandConfig.model_validate(
        json.loads((FIXTURES / "StandConfig" / "v1.json").read_text())
    )
    a = stand.model_copy(update={"attrs": {"x": 1, "y": 2}})
    b = stand.model_copy(update={"attrs": {"y": 2, "x": 1}})
    assert a.content_sha256() == b.content_sha256()
    assert a.content_sha256() != stand.content_sha256()
    assert len(stand.content_sha256()) == 64
