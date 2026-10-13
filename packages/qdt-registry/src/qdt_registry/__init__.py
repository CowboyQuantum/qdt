"""record-keeping engine; the only package that touches a database (rule 4).

`Registry` is the client: a local SQLite cache and payload store, synced to Postgres when reachable
(ADR 0024, ADR 0026). `render_ddl` produces the committed DDL export.
"""

from .client import DSN_ENV, STORE_ENV, Registry, SyncReport
from .ddl import render_ddl

__version__ = "0.1.0"
__all__ = ["DSN_ENV", "STORE_ENV", "Registry", "SyncReport", "__version__", "render_ddl"]
