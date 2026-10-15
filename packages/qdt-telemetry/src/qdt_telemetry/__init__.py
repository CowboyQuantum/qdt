"""Cryo context ingest (Step 7, ADR 0051).

Produces CooldownRecords and per-measurement cryo context from a lab's existing fridge logs or monitoring
store, through the registry adapter path. Not a collector: no daemon, no time-series tables, no dashboards.
"""

__version__ = "0.1.0"
