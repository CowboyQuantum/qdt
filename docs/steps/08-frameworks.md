# Step 8 — Frameworks extraction

> Fixed headings. Agents read this file for the current step; the narrative is in `DEVELOPMENT_PLAN.md`.

## Goal
Governance content becomes schema-validated data rendered by `qdt-frameworks`; HTML is demoted to a renderer.

## Schema slice
`contracts.py`: `ContractDefinition`.

## Deliverables
- resolve the three DAG contract decisions
- extract F-01/F-03 to YAML; renderers

## L0 tests (CI)
- render round trip; deleting an HTML file loses no data

## L1 tests (bench loopback)
- none

## L2 tests (instrument-on-instrument)
- none

## Exit criteria
- all governance HTML regenerable from data

## Open decisions
- #3 DAG contract scoping

## Status
NOT STARTED
