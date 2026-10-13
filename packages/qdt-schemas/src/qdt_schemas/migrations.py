"""Upgrade stored schema objects to the current `schema_version` on load (plan §4.3, ADR 0025).

A migration is a pure function on the JSON-mode dict of one object type, from version n to n + 1,
registered in `MIGRATIONS` under (type name, n). `load` applies them in order and validates the result.
Every persisted type has a fixture at every version it ever had under `tests/fixtures/<Type>/v<n>.json`,
and the migration test loads each one. A breaking change bumps the type's `schema_version` default,
adds the step here and the old-version fixture, and carries an ADR (`packages/qdt-schemas/CLAUDE.md`).

Only top-level `schema_version` is consulted. A nested object keeps its own version; its parent's
migration upgrades it when that nested type changes.
"""

from collections.abc import Callable
from typing import Any

from ._base import QdtModel
from .activity import ExecutionPlan, SweepDefinition
from .data import Annotation, Dataset
from .envelope import MeasurementRecord
from .identity import DeviceRecord
from .modeling import AnalysisResult
from .stand import StandConfig

Migration = Callable[[dict[str, Any]], dict[str, Any]]

PERSISTED: dict[str, type[QdtModel]] = {
    t.__name__: t
    for t in (
        AnalysisResult,
        Annotation,
        Dataset,
        DeviceRecord,
        ExecutionPlan,
        MeasurementRecord,
        StandConfig,
        SweepDefinition,
    )
}
"""Types the registry or a payload stores; each must have a fixture per version."""

def _dataset_1_to_2(data: dict[str, Any]) -> dict[str, Any]:
    """v2 only widens `source.kind` (adds 'analysis', ADR 0031): every v1 Dataset is a v2 Dataset."""
    return data


def _plan_1_to_2(data: dict[str, Any]) -> dict[str, Any]:
    """v2 carries a Dataset v2 (ADR 0031): the nested definition is upgraded in place."""
    data["dataset"] = upgrade("Dataset", dict(data["dataset"]))
    return data


MIGRATIONS: dict[tuple[str, int], Migration] = {
    ("Dataset", 1): _dataset_1_to_2,
    ("ExecutionPlan", 1): _plan_1_to_2,
}
"""(type name, from version) → transform to from version + 1."""


def current_version(type_name: str) -> int:
    return PERSISTED[type_name].model_fields["schema_version"].default


def upgrade(type_name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Return `data` migrated to the current version of `type_name`; raises ValueError for a version
    newer than this package knows, or a missing migration step."""
    if type_name not in PERSISTED:
        raise ValueError(f"{type_name!r} is not a persisted schema type")
    target = current_version(type_name)
    version = data.get("schema_version", 1)
    if version > target:
        raise ValueError(
            f"{type_name} v{version} is newer than this qdt-schemas (v{target}); upgrade the package"
        )
    while version < target:
        step = MIGRATIONS.get((type_name, version))
        if step is None:
            raise ValueError(f"no migration for {type_name} v{version} → v{version + 1}")
        data = step(dict(data))
        version += 1
        data["schema_version"] = version
    return data


def load(type_name: str, data: dict[str, Any]) -> QdtModel:
    """Upgrade then validate: the one way stored objects are read back."""
    return PERSISTED[type_name].model_validate(upgrade(type_name, data))
