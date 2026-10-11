# 0006 — Dependency fences

**Status:** Accepted
**Date:** 2026-10-09
**Step:** 0

## Context
Vendor instrument SDKs (qm-qua, QDAC, Keysight VISA) pin numerical and serialization libraries aggressively and are the dominant source of resolution conflicts. One person maintains seven packages and a front end.

## Decision
Single uv workspace and lockfile, checked in CI. Vendor SDKs are optional extras on qdt-lab only. Upper bounds only on pydantic, numpy, sqlalchemy, xarray; everything else floats under the lock. All qdt-* packages version in lockstep; schema_version stays decoupled. Front end uses pnpm with a committed lockfile; TS types are generated from JSON Schema. CI runs an extras matrix (each extra alone, all together) with import-time checks.

## Consequences
- Easier: conflicts are localized to one package; core installs light; CI catches drift
- Harder: extras must be remembered when installing on the bench (uv sync --all-extras)
- Must now: check qm-qua's current pins against qdt-schemas before Step 1 starts

## Alternatives considered
- Per-package semver — rejected: coordination cost with no consumer that needs it.
- Vendor SDKs as core deps — rejected: every conflict becomes everyone's conflict.
