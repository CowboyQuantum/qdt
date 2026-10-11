# 0005 — Flight Deck restarted under a language-neutral Dataset contract

**Status:** Accepted
**Date:** 2026-10-09
**Step:** 2

## Context
Prior front-end work grew without a stable data contract. The front end must be source-agnostic across instruments and across languages (Python producers, TypeScript consumer) and must be extensible toward dot-tuning features without a rewrite.

## Decision
Restart Flight Deck from scratch at apps/flightdeck. It consumes only the Dataset stream contract: Arrow-encoded array chunks with a small JSON/protobuf envelope for metadata and Annotations. The contract is derived from docs/FINISH_LINE.md before any UI code. TypeScript types are generated from the JSON Schema export, never hand-written. Rule 8: the front end never imports a driver or knows the producing instrument. Transport and UI stack are chosen at Step 2 by a throughput benchmark (plan Open Decisions #8, #9).

## Consequences
- Easier: sources are pluggable (replay, live, registry, sim); source-equivalence is testable in CI
- Harder: no reuse of prior UI code; the contract must be right early
- Must now: write FINISH_LINE.md first; add an import-boundary test for rule 8; generate TS types in CI with a drift check

## Alternatives considered
- Adapt the existing front end — rejected: no contract to adapt to.
- Pickled/pydantic-shaped stream — rejected: Python-only, breaks the cross-language claim.
