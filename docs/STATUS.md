# STATUS

> Rewritten at the end of every session. Never appended. History: `git log -- docs/STATUS.md`.
> A fresh session must be able to continue from this file alone.

**Current step:** 3 — Measurement registry → `docs/steps/03-registry.md`
**Branch:** `step-3/registry` (PR against `main` open; the human merges).
**Last session:** 2026-10-13, session (12, continued after the PR #6 merge). Closed open decisions #2 and #4
(ADR 0023, 0024); built the identity + envelope slice, the `qdt-hdf5-v1` payload, migrations, the
registry client with cache-first sync, the run recorder, and replay to Flight Deck (ADR 0025, 0026).

## Step 3 exit criteria
| Criterion | State |
|---|---|
| any simulated measurement answerable by query (device, stand, definition) | ✔ `Registry.find`, offline and on the server; Tutorial 02 |
| envelope + identity slices frozen with ADR | ✘ objects complete; freeze ADR at exit, after the human runs it on local Postgres |
| L0: ephemeral Postgres round trip | ✔ in CI (`postgres:17.6` service, `QDT_TEST_PG_DSN`); not yet run locally (no Docker) |
| L0: migration fixtures at every `schema_version` | ✔ `tests/fixtures/<Type>/v1.json` for all 7 persisted types |
| L0: JSON Schema + DDL export no-diff | ✔ `records.schema.json`, `exports/ddl/*.sql`, both in `check_all` |
| L0: Step 2 sweep → record → replay from registry | ✔ through the reference stream client (Tutorial 02, registry tests); Flight Deck itself only by hand |

## Done
- Steps 0–2 DONE. ADR 0001–0026. Frozen: `Dataset` contract (0015), protocols (0021), stand/activity/pulse (0022).
- **Schemas (ADR 0023, 0025):** `identity.DeviceRecord`; `envelope.MeasurementRecord` + `PayloadRef`
  (client UUID hex ids, stand/definition by `content_sha256`, aware timestamps); `QdtModel.canonical_json`
  / `content_sha256`; `payload_hdf5` write/read (lazy h5py, never overwrites); `migrations.PERSISTED`,
  `upgrade`, `load`; `scripts/make_schema_fixtures.py` (writes missing versions only).
- **Registry (ADR 0024, 0026):** `qdt_registry.Registry`: SQLite cache + payload store, validated `ingest`,
  `find/get/object/device/payload`, append-only idempotent `sync` to Postgres + a payload directory;
  `python -m qdt_registry find|sync|serve` (`serve` needs the `[serve]` extra). `deploy/registry.compose.yml`.
- **qdt-lab:** `RunRecorder` (frames → payload + `MeasurementRecord`, no DB); `stream.PayloadSource`
  (a payload as a `registry`-kind stream). Depends on `qdt-schemas[hdf5]`.
- `CIRecord`, `AssetRecord`, `BaselineRecord` deferred until a step consumes them (human, ADR 0025).

## In flight
- Nothing uncommitted. PR `step-3/registry` → `main` open.

## Known broken / not yet real
- **No Docker on the Windows dev box** (human installing Docker Desktop). Until then the Postgres tests
  run only in CI.
- Flight Deck cannot show which record it replays: a rule-8 test forbids reading `dataset.source` in
  Flight Deck. `serve` prints the record id. Whether `registry_ref` may be displayed is a decision for
  the human, and an ADR if yes.
- The server payload store is a directory (ADR 0026); a second machine needs object storage or an
  upload endpoint (Step 7).
- `RunRecorder` keeps every frame in memory until `finish`, and hashes the payload by reading it whole.
  Fine at demo sizes.
- Two wall-clock-bound CI gates flake on shared runners: the Flight Deck renderer bench's rendered rate
  (failed on `main` at cc2aec1: 890k vs 950k points/s), and `test_wire_path_keeps_design_target_line_rate`.
  Decide advisory treatment (cf. ADR 0014).
- Carried over: model physics gaps (ADR 0020); waveform protocols frozen without a call site (ADR 0021);
  QUA emitter and real drivers (Step 5); `FINISH_LINE.md` TODO (human); `BENCH.md` skeleton; DUT #10.
- Windows: `pnpm` is not on PATH; use `corepack pnpm ...` in `apps/flightdeck`.

## Next action
**Human:** install Docker Desktop. Merge the `step-3/registry` PR. Then try it:
`docker compose -f deploy/registry.compose.yml up -d`, set
`QDT_TEST_PG_DSN=postgresql+psycopg://qdt:qdt@localhost:5432/qdt_test`, and run `uv run pytest packages/qdt-registry`.
**Then** a session closes Step 3: review the envelope and identity objects against what the registry and
recorder actually used, write the freeze ADR, decide the `registry_ref` display question, mark Step 3 DONE,
and open Step 4 (analysis overlays).

## Decisions pending
- Flight Deck showing `registry_ref` (rule-8 test vs "datasets addressable by record ref"). #10 surrogate DUT,
  by Step 5 entry. Advisory treatment of the two wall-clock CI gates.
