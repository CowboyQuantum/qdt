# `qdt-db` — the registry server on a Windows PC

The runbook for Step 6c goal 1 (ADR 0074, 0080; Analysis 0003 §4–§8): one PC that holds the registry
database, the payload store and the read server, readable from every computer on the lab network and
alive when the measurement PC is off. Written for a Windows host (ADR 0080: Postgres as a native
service, never inside WSL2; the share over SMB). It is rehearsed first on a personal PC standing in as
`qdt-db`, then run again, unchanged, on the lab PC. A Linux section is added when there is a Linux host.

Names in this file are placeholders (rule 7): `qdt-db` the database PC, `<lab-subnet>` such as
`10.0.0.0/24`, `<measurement-pc>`, `<share-user>`. Real names, addresses and passwords live on each
machine, never in this repository or its issues.

What ends up where:

| On `qdt-db` | On the measurement PC | On any other desk |
|---|---|---|
| PostgreSQL service, database `qdt`, roles `qdt_admin` / `qdt_writer` / `qdt_reader` | `QDT_REGISTRY_DSN` as `qdt_writer`, `QDT_PAYLOAD_STORE` = the mounted share | `QDT_REGISTRY_DSN` as `qdt_reader` for scripts, or nothing at all |
| `D:\qdt\payloads`, shared read/write to `<share-user>` | `python -m qdt_server` (the stand server; syncs after every record, ADR 0080) | Flight Deck pointed at the read server; `GET /records/{id}/payload` for bytes |
| `python -m qdt_server --read-only` as a task at start-up | | |
| nightly `pg_dump` + payload mirror to a second disk | | |

## 0. Before you start

- Analysis 0003 §4: the PC never sleeps, restarts after power loss, has a fixed address or a DHCP
  reservation, and the name `qdt-db` resolves from the clients (DNS, or a `hosts` line on each client).
- Two disks, or two volumes: an SSD for Postgres (`C:` is fine), a large one for payloads and the backup
  of Postgres (`D:` below). The backup target of the payloads is a third place (NAS or another machine).
- This repository cloned and `uv sync --all-packages --all-extras` done, on `qdt-db` too: the read server
  and the schema step run from it.
- Windows: `uv` from the installer; Node through `corepack` (`corepack enable` once, then every pnpm
  command is `corepack pnpm …`, which is how `apps/flightdeck/` is run on Windows — #114).

## 1. PostgreSQL as a native service

1. Install PostgreSQL 17 from the EDB installer (the standard Windows build). Take the defaults: service
   `postgresql-x64-17` running as *Network Service*, data directory under `C:\Program Files\PostgreSQL\17\data`,
   port 5432. Set a superuser (`postgres`) password and keep it off the network.
2. Confirm the service starts with the machine: `services.msc` → PostgreSQL → *Automatic*. Reboot once and
   check `pg_isready -h 127.0.0.1` from a *Command Prompt* (the installer puts `bin\` on the PATH for the
   SQL Shell; add it to the system PATH if not).
3. Create the database as the superuser, in the SQL Shell (psql):
   ```sql
   CREATE DATABASE qdt;
   ```
4. The three roles, with `deploy/qdt-db/roles.sql` from the clone, passwords typed on the command line
   (they go nowhere else; the file commits no secret):
   ```
   psql -U postgres -d postgres -v db=qdt -v admin_pw='...' -v writer_pw='...' -v reader_pw='...' -f deploy\qdt-db\roles.sql
   ```
   `qdt_admin` creates the tables and nothing else uses it; `qdt_writer` is what stand servers sync as
   (insert only — rows are never updated, ADR 0026); `qdt_reader` is what the read server and every script
   read as.
5. Listen on the lab network, and admit only it. In the data directory:
   - `postgresql.conf`: `listen_addresses = '*'` (or the lab interface's address).
   - `pg_hba.conf`, appended, one line per role, scoped to the subnet, never `0.0.0.0/0`:
     ```
     host    qdt    qdt_writer    <lab-subnet>    scram-sha-256
     host    qdt    qdt_reader    <lab-subnet>    scram-sha-256
     host    qdt    qdt_admin     127.0.0.1/32    scram-sha-256
     ```
   Restart the service (`services.msc`, or `net stop postgresql-x64-17 && net start postgresql-x64-17` as
   administrator).
6. Windows Firewall, inbound, scoped to the subnet (PowerShell as administrator):
   ```powershell
   New-NetFirewallRule -DisplayName "qdt-db Postgres" -Direction Inbound -Protocol TCP -LocalPort 5432 -RemoteAddress <lab-subnet> -Action Allow
   ```
7. The schema, once, as the admin role, from the clone on `qdt-db` (this creates the tables as `qdt_admin`,
   which is what makes the writer's and reader's default privileges in `roles.sql` apply):
   ```
   set QDT_REGISTRY_DSN=postgresql+psycopg://qdt_admin:<admin_pw>@127.0.0.1:5432/qdt
   uv run python -m qdt_registry init
   ```
   It prints `server ready, ddl_version N`. A client with another DDL version refuses the server (ADR 0026),
   so upgrade clients and server together.

## 2. The payload store and its share

Envelopes go in Postgres; payload bytes are files (ADR 0026). Stand servers write them to the store over a
share; the read server reads them from the local disk; every other reader gets them over HTTP (ADR 0074).

1. The directory: `D:\qdt\payloads`. Give the read server's account (the user that runs the task in §3)
   read access; give `<share-user>` (a local account made for the stand servers, no other rights) modify
   access.
2. Share it (PowerShell as administrator):
   ```powershell
   New-SmbShare -Name qdt-payloads -Path D:\qdt\payloads -FullAccess <share-user>
   ```
   SMB uses TCP 445, which Windows opens for the *Private* profile; scope it to the subnet as for 5432 if
   the firewall is stricter.
3. On the measurement PC, mount it so it survives a reboot, as the user that runs the stand server:
   ```
   net use Z: \\qdt-db\qdt-payloads /user:qdt-db\<share-user> * /persistent:yes
   ```
   `QDT_PAYLOAD_STORE` may name the drive (`Z:\`) or the UNC path (`\\qdt-db\qdt-payloads`); the UNC path
   needs no drive letter and does not depend on the mount being re-established at logon, so prefer it.
   The stand server writes through a temp file and a rename (`qdt_registry` `_place`), so a copy that is
   cut off never leaves a half file under its final name.

## 3. The read server as a task at start-up

`python -m qdt_server --read-only` holds no instrument and accepts no command (ADR 0074): Flight Deck
against it shows the records and the plots and nothing that would run a stand.

1. A `.cmd` beside the clone, e.g. `D:\qdt\read-server.cmd`:
   ```
   @echo off
   set QDT_REGISTRY_DSN=postgresql+psycopg://qdt_reader:<reader_pw>@127.0.0.1:5432/qdt
   set QDT_PAYLOAD_STORE=D:\qdt\payloads
   cd /d D:\qdt\repo
   uv run python -m qdt_server --read-only --host 0.0.0.0 --port 8700 --stream-port 8765 --ui apps\flightdeck\dist --root D:\qdt\read-server
   ```
   `--ui` serves the built Flight Deck at `http://qdt-db:8700/` (build it once: `corepack pnpm install
   --frozen-lockfile && corepack pnpm build` in `apps\flightdeck`). Without `--ui`, open the dev server's
   Flight Deck with `?api=http://qdt-db:8700&ws=ws://qdt-db:8765`.
2. Task Scheduler → *Create Task*: run whether the user is logged on or not, as the account from §2.1;
   trigger *At startup*; action: that `.cmd`; settings: restart every minute if it fails, do not stop it
   when it runs long.
3. Firewall, inbound, 8700 and 8765, scoped to the subnets that may read (the lab subnet; the office subnet
   too if desks there are to see records — deliverable 6 asks IT for that):
   ```powershell
   New-NetFirewallRule -DisplayName "qdt read server" -Direction Inbound -Protocol TCP -LocalPort 8700,8765 -RemoteAddress <lab-subnet> -Action Allow
   ```
4. From another computer: `http://qdt-db:8700/server` answers `{"read_only": true, ...}`, `/docs` is the
   read contract (the OpenAPI document of this server: GET routes and replay, no command), `/records` lists
   what has been synced.

## 4. The measurement PC

The stand server is unchanged except for two environment variables, set for the account that runs it
(System Properties → Environment Variables, or `setx` once):
```
setx QDT_REGISTRY_DSN postgresql+psycopg://qdt_writer:<writer_pw>@qdt-db:5432/qdt
setx QDT_PAYLOAD_STORE \\qdt-db\qdt-payloads
```
Then `uv run python -m qdt_server …` as before. It syncs after every record it ingests and once at start
(ADR 0080): with `qdt-db` reachable a record is on the server seconds after the run ends; unreachable, the
record waits in the local cache and the next sync carries everything. `uv run python -m qdt_registry sync`
does the same by hand, and `find --remote` shows what the server holds.

## 5. Backup and the restore drill

Nightly, as a second scheduled task on `qdt-db` (02:00, as the §2.1 account, `.pgpass` for the admin
password in that account's profile, mode owner-only):
```
pg_dump -U qdt_admin -h 127.0.0.1 -Fc qdt > D:\qdt\backup\qdt-%date:~-4%%date:~-7,2%%date:~-10,2%.dump
robocopy D:\qdt\payloads \\<backup-host>\qdt-payloads /MIR /R:2 /W:5 /LOG:D:\qdt\backup\payloads.log
```
Keep thirty dumps. **The drill, once now and in the calendar:** restore last night's dump into a scratch
database and read it from another computer —
```
createdb -U postgres qdt_drill
pg_restore -U postgres -d qdt_drill D:\qdt\backup\qdt-<date>.dump
```
then, from a desk, `QDT_REGISTRY_DSN=postgresql+psycopg://qdt_reader:<reader_pw>@qdt-db:5432/qdt_drill uv run python -m qdt_registry find --remote`
lists the records; `dropdb -U postgres qdt_drill` afterwards. (`roles.sql` granted `qdt_reader` CONNECT on
`qdt` only; grant it on `qdt_drill` for the drill, or run the find as `qdt_admin`.)

## 6. The smoke test (Analysis 0003 §8 step 8) — the goal 1 demo

1. On the measurement PC, start the stand server and Flight Deck; run one sweep. The server's log says
   nothing about sync (it succeeded) or warns `registry sync failed; records stay in the local cache`.
2. On `qdt-db`, open `http://qdt-db:8700/`: History lists the record; *open* shows it. There is no Run.
3. From any desk, as a script — `docs/tutorials/test_04_remote_read.py` is the pattern, both reads:
   ```python
   from qdt_registry import Registry
   reg = Registry("~/.qdt/registry", remote_dsn="postgresql+psycopg://qdt_reader:<reader_pw>@qdt-db:5432/qdt")
   for r in reg.find(remote=True): print(r.started_at, r.definition_name, r.record_id)
   ```
   and the bytes over HTTP: `GET http://qdt-db:8700/records/<record_id>/payload`, whose `X-Content-SHA256`
   header must equal the record's `payload.sha256`; `qdt_schemas.payload_hdf5.read_payload` opens the file.
4. Stop the stand server. Steps 2 and 3 still pass (row R-2). Reboot `qdt-db` and leave it alone; they pass
   again (row R-3).

## 7. What only a person at the machine can check

The agent sessions that wrote this cannot see `qdt-db`. After each run of this file, tick these:

- [ ] PostgreSQL service *Automatic*, running after a reboot; `pg_isready` from a client on the lab subnet.
- [ ] `psql` as `qdt_writer` and as `qdt_reader` from a client connects; as either from outside the subnet,
      or as `qdt_admin` from any other machine, is refused.
- [ ] `\\qdt-db\qdt-payloads` writable by `<share-user>` from the measurement PC after that PC reboots;
      not readable anonymously.
- [ ] `http://qdt-db:8700/server` from a desk after `qdt-db` reboots with nobody logged on.
- [ ] Last night's dump exists and is not zero bytes; the payload mirror's log has no failed copies.
- [ ] The restore drill done once, with the date noted in `bench/reports/<date>-step6c.md`.
- [ ] Windows Update's restart policy agreed with whoever administers the machine (plan §9).

## 8. The Postgres half of the test suite without Docker (#112)

The same native PostgreSQL serves a developer: create `qdt_test` owned by a role `qdt` with password `qdt`
(`CREATE ROLE qdt LOGIN PASSWORD 'qdt' CREATEDB; CREATE DATABASE qdt_test OWNER qdt;`), run `roles.sql`
against it with `-v db=qdt_test` and any passwords, then
```
set QDT_TEST_PG_DSN=postgresql+psycopg://qdt:qdt@127.0.0.1:5432/qdt_test
set QDT_TEST_PG_READER_DSN=postgresql+psycopg://qdt_reader:<reader_pw>@127.0.0.1:5432/qdt_test
uv run pytest packages/qdt-registry docs/tutorials
```
runs the five Postgres-parametrized registry tests and tutorial 04 against it, as CI does. The tests drop
and recreate the tables in `qdt_test`; never point them at `qdt`. Use `127.0.0.1`, not `localhost`: on
Windows `localhost` tries IPv6 first and each connection stalls.
