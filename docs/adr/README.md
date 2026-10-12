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
| 0009 | Dataset contract draft: envelope-only chunks, region addressing, implicit/explicit coordinates | Accepted (draft; frozen by 0015) |
| 0010 | Stream wire protocol, recordings, and server delivery model | Accepted (draft; frozen by 0015) |
| 0011 | Flight Deck may start against the drafted contract; the freeze gates Step 1 exit only | Accepted |
| 0012 | Flight Deck v0 architecture: one decoder, raw WebGL2, cross-language oracles | Accepted (renderer library provisional until #9) |
| 0013 | Flight Deck 2D renderer: raw WebGL2, no library (closes #9) | Accepted (analysis: `docs/analysis/0002-renderer-benchmark.md`) |
| 0014 | CI gates the renderer bench on rendered rate; latency advisory there | Accepted |
| 0015 | Dataset stream contract frozen against Probe 01; time alignment is the producer's job | Accepted (freezes 0009 + 0010) |
| 0016 | Capability protocol naming: Level/Waveform × Source/Sense, plus Sequencer; quantity lives on the channel | Accepted |
| 0017 | Protocol signatures: producers are handed the Dataset and return a stream; `SequencerProgram` typed envelope | Accepted |
| 0018 | qdt owns a minimal backend-neutral `PulseSequence`; backends emit their own ISA; shots innermost, repeats outermost | Accepted (amends plan §10, §4.1) |
| 0019 | `SweepDefinition` and `ExecutionPlan`: axes bind symbols, stage owns the innermost axes, structural plan, stateless executor | Accepted |
| 0020 | `qdt-sim` written fresh: constant-interaction double dot, periodic charge sensor, clocked noise models | Accepted (amends plan §2) |
