# 0074 — The registry and the control path on the lab network: a read server on `qdt-db`, the stand server for commands, an HTTP read API for other applications, three database roles, payloads on a share

**Status:** Proposed
**Date:** 2026-10-19
**Step:** 6c (deployment goal 1; plan §12 #6; Analysis 0003 §3, §6; ADR 0026's deferral)

## Context
Deployment goal 1: the registry on a database PC (`qdt-db`), readable from any networked computer as well
as the measurement PC — Flight Deck, any Python script with the address and credentials, any
schema-aware application. Three existing rules bound how:
- Rule 4: only `qdt-registry` opens a database connection. A script reads through its public API.
- Rule 8: Flight Deck talks only to `qdt-server`, so "Flight Deck reads the registry from any computer"
  means some `qdt-server` is reachable from that computer.
- The DDL (v3) is internal. If third-party applications read Postgres directly, the DDL becomes a public
  contract that every migration must honour.
ADR 0032/0034 ran the server on one machine with no authentication. Today the registry's server side
takes a DSN (`QDT_REGISTRY_DSN`) and a payload store that is a path (`QDT_PAYLOAD_STORE`), and payload
writes already go through a temp file and a rename. The measurement PC must keep working when `qdt-db`
is unreachable (ADR 0024's offline cache).

## Decision
**Two kinds of server.**
- The **stand server** (`qdt-server --stand …` on the measurement PC) is the only place commands go: runs,
  levels, tune-ups, aborts, the queue (ADR 0075). One per stand.
- A **read server** (`qdt-server --read-only` on `qdt-db`) holds no backends and accepts no commands. It
  serves Flight Deck, records, results, outcomes, payload bytes and replay, reading the registry through
  `qdt-registry` with the reader role. It answers when the measurement PC is off.
Flight Deck is the same build on both; on a read server its command controls are absent, not disabled.

**Other applications read over HTTP, not SQL.** The read server's GET endpoints, documented by the
generated OpenAPI document, are the public read contract, versioned with the API. Postgres accepts
connections only from `qdt-registry` clients; the DDL stays internal. A payload is fetched as bytes from
the read server (`GET /records/{id}/payload`, SHA-256 in a header), so no reader mounts a share.

**Python scripts read through `qdt-registry`** with the reader DSN (rule 4), or over HTTP like any other
application. The step adds a documented read path for scripts and, if the client reads only its local
cache today, a reader mode that queries the server without one.

**Three database roles** (Analysis 0003 §6): `qdt_admin` (migrations only), `qdt_writer` (stand servers'
sync), `qdt_reader` (the read server and scripts). Credentials live in each machine's environment or an
`.env` outside git; none in the repo or its issues (rule 7).

**Payloads reach `qdt-db` on a share (Analysis 0003 option A).** The DB PC exports its payload directory;
only stand servers mount it, as `QDT_PAYLOAD_STORE`, and write through the existing temp-file-and-rename.
Everyone else reads payloads over HTTP from the read server. An HTTP upload endpoint (option B) waits for
the hub (ADR 0076), which needs it for workers off the lab subnet.

**Authentication: commands need a token; reads need the network.** A stand server bound to a
non-loopback address refuses `POST`/`DELETE` without a bearer token from a server-side token file (one
token per desk or person, revocable by deleting its line). Reads on both servers are open to the
subnets the firewall admits. Bound to loopback, nothing changes (ADR 0032). Logins and roles are the
hub's (ADR 0076).

## Consequences
- Easier: the registry is browsable with the measurement PC off; third parties get a stable, documented
  contract without freezing the DDL; one bad desk cannot drive a stand without a token.
- Harder: two server roles to deploy (two systemd units, or a Windows service and a unit); a reader mode in
  `qdt-registry` if one is missing; the share is SMB on a Windows host, so the stand server's mount must
  survive reboots.
- Must now: `--read-only` in `qdt-server` with an L0 test that no command route exists; the payload GET;
  the token check with L0 tests for refusal and loopback exemption; Flight Deck hides commands when the
  server reports read-only; the readiness checks of Analysis 0003 §8 run against `qdt-db`.

## Alternatives considered
- Third parties read Postgres with a read-only role and a frozen, documented DDL — rejected: every
  migration becomes a breaking change for unknown consumers; HTTP gives the same data with a versioned API.
- One server per desk, each with its own registry client — rejected: N writers' worth of credentials and
  caches on N desks, and still no single place that refuses commands.
- One shared server on `qdt-db` holding the backends — rejected: the instruments are on the measurement
  PC's network; backends stay where the drivers reach the hardware.
- No authentication on the lab subnet — rejected: a limit and a stand are safety settings once more than
  one desk can reach them (issue #79).
