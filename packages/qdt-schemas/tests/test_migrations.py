"""Every persisted type has a fixture at every schema_version it ever had, and each loads today."""

import json
import pathlib

import pytest

from qdt_schemas.migrations import PERSISTED, current_version, load, upgrade

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
ALL = sorted((t, v) for t in PERSISTED for v in range(1, current_version(t) + 1))


@pytest.mark.parametrize(("type_name", "version"), ALL, ids=[f"{t}-v{v}" for t, v in ALL])
def test_fixture_at_every_version_loads_as_current(type_name, version):
    path = FIXTURES / type_name / f"v{version}.json"
    assert path.exists(), f"missing {path}; run scripts/make_schema_fixtures.py"
    obj = load(type_name, json.loads(path.read_text()))
    assert type(obj) is PERSISTED[type_name]
    assert obj.schema_version == current_version(type_name)


def test_every_fixture_directory_is_a_persisted_type():
    assert {p.name for p in FIXTURES.iterdir() if p.is_dir()} == set(PERSISTED)


def test_newer_version_than_package_is_refused():
    data = json.loads((FIXTURES / "DeviceRecord" / "v1.json").read_text())
    data["schema_version"] = current_version("DeviceRecord") + 1
    with pytest.raises(ValueError, match="newer"):
        upgrade("DeviceRecord", data)


def test_unknown_type_is_refused():
    with pytest.raises(ValueError, match="not a persisted"):
        upgrade("Nope", {})
