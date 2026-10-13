# 0023 — `payload_hdf5` lives in `qdt-schemas` behind the `[hdf5]` extra (closes #2)

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 3

## Context
ADR 0001 splits a `MeasurementRecord` into a small provenance envelope and a typed payload. The payload's
strictness lives in per-payload specs, and the first spec is `qdt-hdf5-v1`. Step 3 adds the first payload
spec, `payload_hdf5.py` v1, which describes how a `Dataset` and its arrays are laid out in an HDF5 file and
how to write and read that file. Plan §12 left open decision #2: put it in `qdt-schemas[hdf5]` (an extra
already declared in `pyproject.toml` as `hdf5 = ["h5py"]`) or in a new `qdt-io` package.

The forces:
- The payload layout is half of the record contract. A record's `payload_type` names a spec, and readers in
  every package need the spec to validate the file the envelope points at.
- `qdt-schemas` must stay light. Its package rules forbid top-level numpy, xarray or h5py imports and allow
  `[hdf5]` only as a lazy import.
- Rule 5 keeps `qdt-analysis` free of I/O. Rule 4 keeps all database access in `qdt-registry`, but a file
  layout is not database access.

The human chose the `qdt-schemas[hdf5]` extra on 2026-10-13.

## Decision
Put `payload_hdf5.py` in `qdt-schemas`. The layout spec (group and dataset names, attributes, version) is a
pure module. The writer and reader functions import `h5py` and numpy lazily inside the function, available
through `qdt-schemas[hdf5]`. No new package.

## Consequences
- Easier: the envelope and the payload spec it names version together in one package, with one migration
  module and one fixture tree. Any package that already depends on `qdt-schemas` can read a payload by adding
  the extra, with no new dependency edge.
- Harder: `qdt-schemas` now contains file I/O code. It stays behind lazy imports, so a core install without
  the extra still imports cleanly, and a test must enforce that.
- Must now: a test imports `qdt_schemas` with h5py absent, or with the import blocked, and passes.
  `payload_hdf5` carries its own spec version, and a layout change follows the frozen-object rule (ADR,
  version bump, migration, old-version fixture). `qdt-analysis` reads payloads only through objects it is
  handed, never by opening files (rule 5).

## Alternatives considered
- A new `qdt-io` package — rejected: it separates the payload spec from the envelope that names it, adds a
  workspace package and a lockstep version for one module, and every reader would still depend on both.
- Put it in `qdt-registry` — rejected: payload files must be readable without a database (offline cache,
  ADR 0024), and other packages must not depend on the registry to read data.
