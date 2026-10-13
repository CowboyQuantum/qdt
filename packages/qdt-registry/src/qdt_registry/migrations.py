"""Additive DDL migrations for the registry (ADR 0026, ADR 0030): one step per `DDL_VERSION` bump.

A step is a function of an `Engine` that creates what the new version adds (tables, indexes, columns)
and never drops or rewrites anything. `migrate` reads `registry_meta.ddl_version`, applies every step
from that version up to `DDL_VERSION` in order, and records the new version in the same database.
A database newer than this package is refused. Steps are idempotent (`checkfirst`), so an interrupted
migration can be rerun.
"""

from collections.abc import Callable

from sqlalchemy import Engine, select

from .tables import DDL_VERSION, analyses, metadata, registry_meta

Step = Callable[[Engine], None]


def _v1_to_v2(engine: Engine) -> None:
    """DDL 2 (ADR 0030): the `analyses` table."""
    analyses.create(engine, checkfirst=True)


STEPS: dict[int, Step] = {1: _v1_to_v2}
"""from version → step to from version + 1."""


def stored_version(engine: Engine) -> int | None:
    """The database's `ddl_version`, or None for an empty database."""
    if not engine.dialect.has_table(engine.connect(), "registry_meta"):
        return None
    with engine.connect() as conn:
        row = conn.execute(
            select(registry_meta.c.value).where(registry_meta.c.key == "ddl_version")
        ).scalar_one_or_none()
    return int(row) if row is not None else None


def migrate(engine: Engine) -> int:
    """Bring `engine`'s database to `DDL_VERSION`; returns the version it started at (0 if empty)."""
    version = stored_version(engine)
    if version is None:
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(registry_meta.insert().values(key="ddl_version", value=str(DDL_VERSION)))
        return 0
    if version > DDL_VERSION:
        raise RuntimeError(
            f"registry at {engine.url!r} has ddl_version {version}; this client knows {DDL_VERSION}: "
            "upgrade qdt-registry"
        )
    started = version
    while version < DDL_VERSION:
        step = STEPS.get(version)
        if step is None:
            raise RuntimeError(f"no migration from ddl_version {version} to {version + 1}")
        step(engine)
        version += 1
        with engine.begin() as conn:
            conn.execute(
                registry_meta.update()
                .where(registry_meta.c.key == "ddl_version")
                .values(value=str(version))
            )
    return started
