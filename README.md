# qdt — Quantum Dot Toolkit

A generic engine for silicon spin qubit measurement: instrument capability protocols, a source-agnostic
front end (Flight Deck), experiments-as-data, a provenance-first measurement registry, physics simulation,
and schema-validated frameworks. Apache-2.0. Published by Cowboy Quantum.

- Humans: start at `docs/DEVELOPMENT_PLAN.md` (roadmap §7).
- Agents: start at `CLAUDE.md`, then `docs/STATUS.md`.

```
uv sync --all-packages --all-extras && uv run pytest && bash scripts/check_all.sh
```
