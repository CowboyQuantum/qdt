# Analysis 0003 — Registry deployment requirements: dedicated database PC

**Date:** 2026-10-15 · **Informs:** the Step 7 deployment ADRs (payload transport off-box, raw-trace retention,
database roles) and plan §5/§9 · **Step:** 7
**Kind:** analysis note. Not a decision. It records what the registry is as built (ADR 0024–0026), what a
dedicated database PC must provide, and the numbers behind sizing. Decisions are made in ADRs that cite it.

## 1. What the registry is, as built (ADR 0024, 0025, 0026)

- **Two stores on every client, two on the server.** A client writes each record to a local SQLite cache
  (`<root>/cache.sqlite`) and its payload file to a local payload store (`<root>/payloads/`), then syncs to the
  server when reachable. The server is **Postgres** (`QDT_REGISTRY_DSN`) plus a **filesystem payload store**
  (`QDT_PAYLOAD_STORE`). Same table set on both sides; append-only; client-minted UUIDs; sync is
  insert-if-absent.
- **Envelopes in the database, bytes on disk.** A `MeasurementRecord` is small (ids, content hashes, timestamps,
  a `PayloadRef` with relative path, SHA-256, size). Payloads (`qdt-hdf5-v1`) never enter Postgres.
- **What is not yet decided (ADR 0026, "Harder"):** the server's payload store is a directory, so a syncing
  client on a *second machine* needs a way to deliver bytes to it. ADR 0026 names "object storage or an HTTP
  upload endpoint" and defers the choice to Step 7. §3 below lays out the options.
- `deploy/registry.compose.yml` is development-only (localhost, dev credentials). It is **not** the lab
  deployment and nothing below assumes Docker.

## 2. Topology

```
measurement PC(s)                      dedicated DB PC ("qdt-db")
┌──────────────────────────┐           ┌──────────────────────────────┐
│ qdt-server / executor    │  5432/TCP │ Postgres (service)           │
│ qdt-registry client      │ ────────▶ │   db: qdt  roles: admin/     │
│   cache.sqlite           │           │   writer/reader              │
│   payloads/ (local)      │  §3 port  │ payload store (disk)         │
└──────────────────────────┘ ────────▶ │   <QDT_PAYLOAD_STORE>        │
analyst laptop  ───── 5432 (read) ───▶ │ nightly backup → NAS/other   │
                                       └──────────────────────────────┘
```

Clients know the server only as the hostname `qdt-db` (DSN) and one payload endpoint; both are names,
never addresses (plan §5). Moving the server is `pg_dump` → restore, copy the payload store, repoint two names.

## 3. Payload transport off-box — the open decision

Three ways a second machine can land payload bytes in the server's store. All keep ADR 0026's filesystem
store on the server; they differ in how bytes cross the network.

| Option | Mechanism | Client change | Ports | Integrity | Notes |
|---|---|---|---|---|---|
| A. Shared folder | Server exports `<QDT_PAYLOAD_STORE>` over SMB; clients write files directly | none — the filesystem store already exists | 445 (SMB), usually already open on Windows | none in transit; SHA-256 in the envelope verifies after the fact | Simplest on a Windows host. Mounts, credentials and reconnects on every client. Partial files visible during write unless written to a temp name and renamed. |
| B. HTTP upload | `qdt-server` (FastAPI, ADR 0034) on the DB PC exposes `PUT /payloads/{path}` with SHA-256 verification; the client uploads, the server writes the store | a small `PayloadStore` protocol with `filesystem` and `http` implementations | one HTTP(S) port (e.g. 8100) | server verifies SHA-256 before commit; atomic | No mounts, works across subnets, one process already in the stack. The DB PC then runs Python. |
| C. S3-compatible object store | An S3-API server on the DB PC (or anywhere); clients PUT/GET by key | `PayloadStore` protocol with an `s3` implementation (boto3 or similar) | one HTTP(S) port (server-specific; 8333 SeaweedFS, 3900 Garage) | ETag + client-verified SHA-256; atomic per object | Same client code against any S3 provider later. **MinIO is end-of-life (community binaries stopped 2025-10, repo archived 2026) — do not adopt it.** Candidates: SeaweedFS (Apache-2.0), Garage (AGPL). AGPL may need an IT conversation. |

What does not change across A/B/C: the envelope's `PayloadRef` (relative path + SHA-256 + size), the
server-side directory, `qdt-analysis` reading payloads only through objects it is handed (rule 5). A
`PayloadStore` protocol (`put(rel_path, bytes) -> sha256`, `get`, `exists`) makes A/B/C a deployment choice
rather than an architecture choice; the filesystem implementation already exists in substance.

Inputs for the ADR: A is the fastest path on a Windows host with no new services; B is the most self-contained
and needs no IT conversation beyond one port; C pays off only when a managed object store is in sight.

## 4. Host requirements (the dedicated DB PC)

**OS.** Linux (Ubuntu LTS) preferred: Postgres from apt as a systemd service, no containers. The current
candidate is **Windows with WSL**. Recommendation: run **Postgres as a native Windows service** (standard
installer) and do **not** host it inside WSL2 — WSL's NAT networking needs `netsh portproxy` rules that break
when the WSL address changes, the VM does not start at boot without a scheduled task, and the data directory
sits on a virtual disk one layer away from backups. Native service: autostarts, firewall-able, backs up
like any directory.

**No Docker required** in any flavor: Postgres is a native package/installer on both OSes; a payload transport
is a share (A), a Python process (B) or a single static binary (C).

**Power/sleep.** Never sleeps; auto-restart after power loss; Windows Update policy agreed with IT (plan §9).

**Network.** Static IP or DHCP reservation; DNS name `qdt-db` (or a `hosts` entry on each client until DNS
exists); gigabit Ethernet — payload transfer is where a client waits, not CPU.

## 5. Ports and settings — the complete list

On the DB PC:
1. `postgresql.conf`: `listen_addresses = '*'` (default is localhost-only) or the LAN interface IP.
2. `pg_hba.conf`: per-role lines scoped to the lab subnet, e.g.
   `host qdt qdt_writer 192.168.10.0/24 scram-sha-256` and the same for `qdt_reader`. Never `0.0.0.0/0`.
3. Firewall inbound **TCP 5432**, scoped to the lab subnet or the measurement PC(s).
4. Payload transport port per §3: **445** (A, usually already open), **8100** (B), or the S3 port (C). Scoped the same way.
5. TLS on 5432 and the payload port the moment any client is on another subnet.

On the measurement PC: nothing inbound. One `hosts` entry if no DNS. `QDT_REGISTRY_DSN` and the payload
endpoint use the name `qdt-db`.

This replaces plan §9's "Docker approval; 5432/8100 (+9000/9001)" with: a Postgres installer, one inbound rule
on 5432, one inbound rule for the payload transport, a DNS name. (9000/9001 were MinIO defaults; retire them.)

## 6. Roles and secrets

Three Postgres roles: `qdt_admin` (creates tables / future Alembic migrations; nothing else uses it),
`qdt_writer` (executor / sync), `qdt_reader` (analysts, dashboards). No client connects as superuser.
Passwords in a local `.env` outside git. `deploy/registry-init.sql` is the development seed; the lab
version lives in the internal extension (ADR 0002).

## 7. Sizing

Load model, per stand: 100–1,000 sweeps/day; one envelope row of ~1–2 KB each → < 1 GB/year in Postgres
including indexes, analysis results and configuration objects. Telemetry (Step 7) at ~1 sample/10 s × ~20
channels ≈ 170k rows/day ≈ 60M rows/year ≈ 3–6 GB/year raw. Concurrency: one writer, a few readers.

| Resource | Minimum | Comfortable | Notes |
|---|---|---|---|
| RAM | 8 GB | **16 GB** | `shared_buffers` ≈ 25 % of RAM, `effective_cache_size` ≈ 50–75 %. 32 GB only if analysis runs *on* the box. |
| CPU | 4 cores | 4–8 cores | idle most of the time |
| Postgres disk | 250 GB SSD | 500 GB SSD | a decade of envelopes + telemetry |
| Payload disk | 2 TB | **4 TB**, growable | ~0.2–1 TB/year/stand (see below) |
| Backup target | ≥ payload disk | separate machine or NAS | never the same disks |
| Network | 1 GbE | 1 GbE | |

Payload growth: a 2048² float64 map is ~32 MB (ADR 0026); 1000² float32 is 4 MB; typical tuning sweeps are
tens of KB; raw-ADC bursts tens of MB. At ~1 MB average and 500 sweeps/day: ~0.5 GB/day ≈ 180 GB/year;
with raw traces retained by default, up to ~1 TB/year. **The retention policy for raw traces is the single
largest sizing lever** and should be an explicit line in the Step 7 ADR.

## 8. Initialization runbook (order matters)

1. OS set up per §4; static address; `qdt-db` resolvable from a client.
2. Disks: Postgres data on SSD; payload store on the large disk; backup target reachable.
3. Install Postgres (native). Create database `qdt`, the three roles (§6), `pg_hba.conf` lines (§5).
4. Firewall rules (§5). Verify from a client: `psql`/`pg_isready` against `qdt-db`.
5. Schema: `uv run python -m qdt_registry init` (or the equivalent `create_all` entry point) as `qdt_admin`;
   confirm the reported `ddl_version` matches the client's `DDL_VERSION` (ADR 0026 — a client refuses a
   mismatched server).
6. Payload transport per §3; verify a client can land a file and the server sees it at the relative path.
7. Seeds: stand and device identity from the internal extension's seed scripts.
8. **Smoke test:** write one record offline on a client, sync, query it back from a *different* client.
9. **Backup proven:** nightly `pg_dump` + payload mirror configured; restore last night's dump into a scratch
   database and re-run the step-8 query against it. Calendar a repeat.
10. Monitoring, minimal: disk usage and "Postgres up" alerts.

## 9. Transitions

Personal machine → lab DB PC → managed VM: each is `pg_dump` → restore, mirror the payload store, repoint
`qdt-db` and the payload endpoint. No client code changes. Prototype data is a seed corpus and comes along
(plan §5).

## 10. Decisions this note feeds

- Payload transport off-box (A/B/C in §3) — Step 7 ADR; a `PayloadStore` protocol is the common prerequisite.
- Raw-trace retention default — Step 7 ADR (sizing lever, §7).
- Database roles and the `.env` convention — Step 7 ADR or internal-extension runbook.
- Plan §9 checklist rewrite: drop Docker approval and 9000/9001; add native Postgres, 5432 + one transport port, DNS name.
- Cryo context source (ADR 0050): the lab's existing fridge monitoring/log store is a deployment input — its location, access mode and read credentials for the ingest adapter; no collector runs on the DB PC.
