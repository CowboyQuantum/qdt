# 0011 — Flight Deck may start against the drafted contract; the freeze gates Step 1 exit only

**Status:** Accepted
**Date:** 2026-10-11
**Step:** 1

## Context
`apps/flightdeck/CLAUDE.md` allowed no UI code until the `Dataset` contract was *frozen*. ADR 0008 later
made Probe 01 gate the freeze, and Probe 01 needs lab time that is not currently available. Step 1's
deliverables build Flight Deck v0 within the step, and its exit criteria require a frozen contract. Read
together, the old gate blocked Step 1 indefinitely on lab access. The contract is now drafted (ADR 0009),
has a wire protocol (ADR 0010), a JSON Schema export with a drift check, and source-equivalence tests in Python.

## Decision
Allow Flight Deck UI code once `FINISH_LINE.md` is authored and the contract is drafted with ADRs. The
contract freeze stays a Step 1 exit criterion; it no longer gates the start of UI work.

## Consequences
- Easier: Step 1 continues without lab access; the Flight Deck work tests the draft contract from the
  consumer side before the freeze, which is the cheapest time to find problems.
- Harder: a contract change between now and the freeze touches both Python and TypeScript. Generated
  types, the schema drift check and the source-equivalence tests make this visible; it is not free.
- Must now: Flight Deck consumes only generated types and the ADR 0010 wire protocol. Any contract change
  regenerates `src/schema/` and keeps Flight Deck tests green in the same commit. The freeze ADR lists
  every contract change made after this point.

## Alternatives considered
- Keep the gate and wait for Probe 01 — rejected: blocks the step on lab access for no information gain;
  the probe answers addressing questions the draft already accommodates both ways.
- Hand-written TS types until the freeze — rejected by ADR 0005/0006 (types are generated, never hand-written).
- Freeze now without Probe 01 — rejected: ADR 0008 requires the probe for the freeze.
