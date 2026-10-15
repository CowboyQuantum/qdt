# 0051 — `qdt-telemetry` ingests cryo context into the registry; it does not collect, store time series, or monitor

**Status:** Accepted
**Date:** 2026-10-15
**Step:** 7

## Context
Plan §3.1 and `qdt-telemetry`'s package description call it a "cryo telemetry collector," and Step 7's
deliverable is "parsers against fixture logs." Reviewed on 2026-10-15 against the org test (a thing earns
its own place by audience, cadence and coupling), fridge telemetry splits in two:

- The **join** — "what was the mixing-chamber temperature during this sweep", "this device's last three
  cooldowns" — is coupled to the registry. It is `CooldownRecord`, per-record cryo context, and a query.
  ADR 0001's envelope was designed for exactly this kind of external source. It is the Step 7 exit criterion.
- The **collector** — a daemon tailing fridge logs, format parsers, time-series storage at ~60M rows/year,
  retention and downsampling, dashboards, alerting — is operational monitoring. Its audience includes people
  who never run a sweep; its cadence is "runs for months"; it is a service, not a library; nothing in it uses
  qdt's protocols or executor. Labs typically already have it (vendor logging, a Grafana box). Rebuilding it
  inside a measurement toolkit duplicates what exists and ties qdt's release to a daemon's uptime.

The human chose on 2026-10-15 to keep the join and drop the collector.

## Decision
`qdt-telemetry` **ingests**: given a log corpus or an existing monitoring store, it produces `CooldownRecord`s
and per-record cryo context through the registry's adapter path, verified by golden-file tests. It runs no
daemon, keeps no time-series tables beyond what a cooldown summary needs, and ships no dashboards or alerts.
Raw logs may be retained as payload files on the envelope (ADR 0001, 0026), never as rows. The cryo schema
slice is reduced to what the join needs: `CooldownRecord` and `FridgeEvent` now; `TelemetryChannel` and
`TelemetrySample` are deferred until a consumer needs them (plan §4.1 rule). A fridge *collector*, if ever
justified, is a separate Cowboy Quantum repo that writes to the same envelope through the same adapter.

## Consequences
- Easier: Step 7's deliverable is an adapter against what the lab already runs, plus a cooldown schema —
  smaller, and the substrate pilot shows correlation (which nothing else does) rather than a second monitor.
  Postgres stays small; registry backups stay cheap (Analysis 0003 §7).
- Harder: cryo context at measurement time depends on an external store being readable; when it is not, the
  record carries no cryo context rather than failing (the same stance as ADR 0024 for the registry itself).
- Must now: package description and plan §3.1 say "ingest"; Step 7 deliverables and schema slice updated;
  Analysis 0003 §10 lists the external monitoring store as a deployment input; the "existing monitoring"
  access mode replaces "Bluefors log access mode" in the §9 IT checklist.

## Alternatives considered
- Keep the collector in `qdt-telemetry` — rejected: wrong audience and cadence for this repo; duplicates
  existing lab monitoring; makes a daemon part of the measurement toolkit's release.
- No telemetry in qdt at all — rejected: the join is the one thing only the measurement registry can provide.
