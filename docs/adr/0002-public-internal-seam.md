# 0002 — Public engine / internal extension seam

**Status:** Accepted
**Date:** 2026-10-09
**Step:** all

## Context
The toolkit is generic to any silicon spin qubit lab, but the pilot serves one organization whose stands, lots, tolerances, and systems must never appear in a public repository.

## Decision
The public, Apache-2.0 engine is this repo. All site-specific content lives in a separate internal extension package that consumes tagged releases through the adapter registry. The engine never imports or names the internal package. A grep test enforces the seam at every commit.

## Consequences
- Easier: the public repo is auditable; upstreaming generic improvements is frictionless
- Harder: two repos, two CIs; site adapters must be written against public APIs only
- Must now: run scripts/provenance_check.sh in CI; keep scripts/provenance_terms.txt current

## Alternatives considered
- One private monorepo — rejected: no public artifact, no clean upstream.
- Site content as git-resident YAML in the public repo — rejected: provenance leak and files-as-database antipattern.
