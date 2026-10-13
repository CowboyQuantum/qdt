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
| 0016 | Capability protocol naming: Level/Waveform × Source/Sense, plus Sequencer; quantity lives on the channel | Accepted (frozen by 0021) |
| 0017 | Protocol signatures: producers are handed the Dataset and return a stream; `SequencerProgram` typed envelope | Accepted (frozen by 0021) |
| 0018 | qdt owns a minimal backend-neutral `PulseSequence`; backends emit their own ISA; shots innermost, repeats outermost | Accepted (amends plan §10, §4.1; frozen by 0022) |
| 0019 | `SweepDefinition` and `ExecutionPlan`: axes bind symbols, stage owns the innermost axes, structural plan, stateless executor | Accepted (frozen by 0022) |
| 0020 | `qdt-sim` written fresh: constant-interaction double dot, periodic charge sensor, clocked noise models | Accepted (amends plan §2) |
| 0021 | Capability protocols frozen; backends are constructed from their channel declarations | Accepted (freezes 0016 + 0017) |
| 0022 | Stand, activity and pulse schema slices frozen at schema_version 1 | Accepted (freezes 0018 + 0019 objects) |
| 0023 | `payload_hdf5` lives in `qdt-schemas` behind the `[hdf5]` extra | Accepted (closes plan #2) |
| 0024 | Registry clients write to a local cache first and sync to Postgres | Accepted (closes plan #4) |
| 0025 | `MeasurementRecord` is a reference-and-hash envelope; Step 3 builds only device identity | Accepted |
| 0026 | Registry storage: one table set for cache and server, append-only, payloads in a file store | Accepted |
| 0027 | Flight Deck may read `source.registry_ref`, for display only | Accepted (narrows the rule-8 test) |
| 0028 | Identity, envelope and `qdt-hdf5-v1` frozen at schema_version 1 | Accepted (freezes 0025 objects + 0023 layout) |
| 0029 | `AnalysisResult` provenance is record + method; transitions detected locally, estimated as a lattice | Accepted |
| 0030 | The charge sensor is a biased SET: source–drain bias in `qdt-sim`, Coulomb diamonds as a sweep and a method | Accepted (regenerates the sim fixture) |
| 0031 | Analysis outputs are Datasets in payloads; methods are curated; one record per result for now | Accepted (Dataset v2, ExecutionPlan v2) |
