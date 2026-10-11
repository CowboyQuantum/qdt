# Architecture Decision Records

Immutable once merged (except a `Superseded by` status line). New decision = new ADR. Write one via `/adr <title>`.

| # | Title | Status |
|---|---|---|
| 0001 | Envelope/payload hybrid for MeasurementRecord | Accepted |
| 0002 | Public engine / internal extension seam | Accepted |
| 0003 | Apache-2.0 license | Accepted |
| 0004 | Instrument-up sequencing with mandatory test ladder | Accepted |
| 0005 | Flight Deck restarted under a language-neutral Dataset contract | Accepted |
| 0006 | Dependency fences: extras for vendor SDKs, lockstep versioning, generated TS types | Accepted |
| 0007 | Simulation-first sequencing; instrument drivers as the last mile | Accepted (supersedes ordering in 0004) |
| 0008 | Stream transport, encoding, and renderer class | Accepted (analysis: `docs/analysis/0001-stream-budget.md`) |
| 0009 | Dataset contract draft: envelope-only chunks, region addressing, implicit/explicit coordinates | Accepted (draft; freeze after Probe 01) |
| 0010 | Stream wire protocol, recordings, and server delivery model | Accepted (draft; frozen with the contract after Probe 01) |
| 0011 | Flight Deck may start against the drafted contract; the freeze gates Step 1 exit only | Accepted |
| 0012 | Flight Deck v0 architecture: one decoder, raw WebGL2, cross-language oracles | Accepted (renderer library provisional until #9) |
| 0013 | Flight Deck 2D renderer: raw WebGL2, no library (closes #9) | Accepted (analysis: `docs/analysis/0002-renderer-benchmark.md`) |
