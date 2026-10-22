# 0080 — ADR 0074 accepted and amended: the stand server syncs after every record and at start, falling back to its cache; goal 1 is rehearsed on a personal Windows PC with the lab PC's runbook

**Status:** Accepted
**Date:** 2026-10-22
**Step:** 6c (goal 1; closes the step's open decisions on ADR 0074 and on the lab PC's OS)

## Context
ADR 0074 (proposed 2026-10-19) set goal 1's design: a read server on `qdt-db` that takes no commands, the
stand server for commands, an HTTP read API for other applications with the DDL kept internal, three
database roles, payloads on a share written only by stand servers, a bearer token for commands off loopback.
Step 6c gates deliverables 2–5 on accepting or amending it. On 2026-10-22 the human accepted it with three
directions, and asked one question that is worth answering here because a future session will ask it again.

**Why other applications read over HTTP and not SQL.** The tables are a few indexed columns and a `body`
column holding the whole schema object as JSON; a SQL reader would parse bodies whose shape is the schema,
which grows one slice per step, so opening SQL to outside applications freezes the DDL and every body as a
public contract and makes each migration a breaking change for consumers nobody knows about. The HTTP API
is generated from the schema objects and published as OpenAPI (ADR 0034), so it is versioned and can carry a
deprecation rule. SQL alone does not deliver a measurement: envelopes are in Postgres and the bytes are
files (ADR 0026), so a SQL-only reader also needs the share mounted, while `GET /records/{id}/payload`
hands over the bytes with a SHA-256 header over one port. Flight Deck cannot speak SQL (rule 8), so a server
reading the registry must exist on `qdt-db` regardless. And SQL readers need a database login on every
desk; HTTP readers need only to be on an admitted subnet. qdt's own client keeps SQL (rule 4): a Python
script may read through `qdt_registry` with the reader role or over HTTP, as 0074 says.

**The three directions.** (1) "I don't want to do manual sync — please add a sync attempt after every
measurement, and if the database PC is not reachable default to the local cache." Today the stand server
ingests each record into its local cache and nothing calls `Registry.sync()`; the human would have run
`python -m qdt_registry sync` by hand. (2) "For this demo, the database PC is not the real lab database PC.
I want to demo this on my personal PC before trying to clone this repo on the lab PC." (3) "Both my personal
PC and the lab PC are Windows, for now. We can keep the desire to have the lab be a Linux box with
documented reasons, but for now it's Windows." Analysis 0003 §4 records the Linux preference and its
reasons, and recommends Postgres as a native Windows service rather than inside WSL2.

## Decision
1. **ADR 0074 is accepted as written.**
2. **The stand server syncs after every record and once at start.** After `RunManager` ingests a record it
   calls `Registry.sync()` off the event loop; the server's lifespan calls it once after the registry opens.
   A failure (the DSN unreachable, the share not mounted) is logged, the run's outcome is unchanged, and the
   record stays in the cache marked unsynced. `sync` is insert-if-absent and uploads everything unconfirmed
   (ADR 0024, 0026), so the next successful attempt carries every record missed before it; there is no
   separate retry loop or timer. A read-only server (ADR 0074) never syncs: it has no writer role and
   ingests nothing. Flight Deck on the measurement PC keeps reading that PC's cache, which is complete for
   that PC; the read server reads Postgres, complete up to the last successful sync.
3. **Goal 1 is rehearsed on a personal PC standing in as `qdt-db`,** deliverables 1–4, with a laptop as the
   measurement PC and a simulated stand. `deploy/qdt-db/README.md` is written on that PC with placeholder
   names; the lab PC is a second run of the same runbook, not a second runbook. Deliverable 6 (the IT ask)
   stays with the lab. Rule 7 holds for the personal PC: no hostname, address or credential enters the repo
   or an issue.
4. **The host is Windows for now:** Postgres as a native Windows service, the payload share over SMB, per
   Analysis 0003 §4. The preference for a Linux host and its reasons stay recorded there; a Linux section
   is added to the runbook when a Linux host exists. This settles the step's open decision on the lab PC's
   OS (plan §12 #6) for the present.

## Consequences
- Easier: a measurement is in the database the moment it exists, when the database is reachable; catch-up
  after an outage costs nothing extra; the runbook's gaps are found on hardware the human owns before IT is
  involved; the Windows questions of Analysis 0003 §4 are answered by doing.
- Harder: every run pays a sync round-trip at its end (small: one insert per new row, one file copy per
  payload over the share); a sync that hangs on a half-reachable share must not hold the run's `completed`
  state, so the sync runs after the state is set and in its own thread; Windows services and SMB mounts
  that survive reboots are their own craft, and the runbook must prove them (Analysis 0003 §8 step 4).
- Must now: Step 6c deliverables 1 and 2 and its L0 list carry the sync and the Windows host; the ADR
  index marks 0074 accepted (amended by this ADR); the next session begins goal 1's deliverables 1–4 on
  the personal PC; the L0 rows: with the server unreachable a run completes and its record is in the cache
  unsynced; with it reachable again the next ingest uploads every unsynced record and payload; a read-only
  server never syncs.

## Alternatives considered
- A periodic sync timer — rejected: the moment data exists is the moment to send it; a timer adds a second
  clock and a second failure mode, and catch-up already comes free from insert-if-absent.
- Sync triggered from Flight Deck or by a scheduled task — rejected: Flight Deck holds no registry (rule 8),
  and a task outside the server is one more thing to install and forget on every measurement PC.
- The lab PC first — rejected by the human: rehearsing on a personal PC finds the runbook's gaps before IT
  is involved and before the repo is cloned onto a machine the human does not administer.
- Postgres inside WSL2 — rejected: Analysis 0003 §4 (NAT port-proxy rules that break when the address
  changes, no start at boot without a scheduled task, data one virtual disk away from backups).
- Switching the lab PC to Linux now — deferred by the human: the preference and its reasons stay on record;
  the runbook grows a Linux section when there is a Linux host to run it on.
