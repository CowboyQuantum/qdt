"""Render the registry's DDL as SQL text, for the committed export and its no-diff check (plan §4.3)."""

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateIndex, CreateTable

from .tables import DDL_VERSION, metadata

DIALECTS = {"postgresql": postgresql.dialect(), "sqlite": sqlite.dialect()}


def render_ddl(dialect: str = "postgresql") -> str:
    """CREATE TABLE / CREATE INDEX statements for every registry table, in dependency order."""
    d = DIALECTS[dialect]
    out = [
        f"-- qdt registry DDL, ddl_version {DDL_VERSION}, dialect {dialect}. Generated; do not edit."
    ]
    for table in metadata.sorted_tables:
        out.append(str(CreateTable(table).compile(dialect=d)).strip() + ";")
        for index in sorted(table.indexes, key=lambda i: i.name):
            out.append(str(CreateIndex(index).compile(dialect=d)).strip() + ";")
    return "\n\n".join(out) + "\n"
