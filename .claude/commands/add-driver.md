Add a new instrument driver to qdt-lab for: $ARGUMENTS

Follow `packages/qdt-lab/CLAUDE.md` exactly:
1. Identify which capability protocol(s) in `qdt_lab/protocols/` the instrument implements. If none fit, stop — a new protocol is an ADR-level decision.
2. Add the vendor SDK as an optional extra in `packages/qdt-lab/pyproject.toml`, never as a core dependency. Check its pins against `qdt-schemas` deps first and report conflicts.
3. Implement the driver under `qdt_lab/drivers/<vendor>/`, importing the SDK lazily inside functions.
4. Do NOT write new tests. Register the driver in the conformance suite's backend parametrization; the existing suite must pass unchanged against the simulated backend, and against the real one under `-m hardware`.
5. Add a loopback entry to `docs/BENCH.md` and a bench test in `bench/` with a numeric oracle.
