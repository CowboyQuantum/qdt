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
| 0014 | CI gates the renderer bench on rendered rate; latency advisory there | Superseded by 0039 |
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
| 0032 | The control path (server + UI) comes before instrument drivers, as Step 4b | Accepted (amends the ADR 0007 order) |
| 0033 | Modeling slice frozen at schema_version 1: `FitModel`, `Estimate`, `AnalysisResult` | Accepted (freezes 0029 objects; closes Step 4) |
| 0034 | `qdt-server`: FastAPI over the schema objects, REST for commands and queries, the existing WebSocket for data | Accepted |
| 0035 | The Step 4b pulse-sequence editor is a form over `PulseSequence` (rows, number-or-symbol cells, bindings), not a timeline; 1-D sweeps | Accepted |
| 0036 | Control slice frozen at schema_version 1: `Run`, `MethodSpec`, `ParameterSpec`, `EstimateSpec` | Accepted (closes Step 4b) |
| 0037 | Chopped readout: `Affine` values and a `difference` primitive in `PulseSequence`, additive without a version bump | Accepted (amends the 0022 pulse slice) |
| 0038 | A sweep carries its operating point: `SweepDefinition.levels`, fixed DC levels held for the whole scan | Accepted |
| 0039 | Wall-clock rate targets are advisory on shared CI runners; a floor at half the target still gates | Accepted (supersedes 0014) |
| 0040 | L2 is instrument-on-instrument with off-the-shelf parts (bias tee, the scope's 1 MΩ input); no surrogate DUT board | Accepted (closes #10; amends 0004's L2) |
| 0041 | Step 5 drivers: one SCPI transport, an emulator per driver, the OPX building QUA from the emitted stage; `qdt-server --stand` | Accepted |
| 0042 | Bench reports are written by pytest: one file per day, a section per run, addresses redacted | Accepted |
| 0043 | The QDAC-II is also reachable over its USB serial port; `open_visa` takes a baud rate; pyserial in `[qdac]` | Accepted |
| 0044 | OPX1000 LF-FEM input constants are measured (Probe 02): inverted, 1.155 × 2⁻¹², 180 ns of flight | Accepted |
| 0045 | The curated plane fit: least squares with standard errors, failure below `min_r2`, iso-lines as `line` overlays, fitted plane + residual as output | Accepted |
| 0046 | The curated single exponential: an edge-anchored window, nonlinear least squares with standard errors, markers on the time axis, fitted curve + residual as output; `MethodSpec.applies_to` gains `trace_1d` additively | Accepted (amends 0036 additively) |
| 0047 | Waveform capture as an activity: `CapturedWaveform` in the sweep, a `(record, time)` slab per stepped point, a simulated scope on the server's stand, traces drawn as traces | Accepted (amends 0022 additively) |
| 0048 | Step 6's modeling objects: `SimScenario`, `CalibrationNode` with a `DecisionRule`, `NodeOutcome`, `SimResult`; nodes and rules in `qdt-tuning` (pure), the runner in `qdt-server` | Accepted (adds to 0033 as reserved) |
| 0049 | Virtual gates as coupled axes (`SweepAxis.couplings`), node inputs bound from upstream outcomes (`InputBinding`), the first tune-up runner | Accepted (amends 0022 additively; extends 0048) |
| 0050 | The tune-up as a lifecycle object (`TuneUp`), outcomes persisted (`tuning_outcomes`, DDL v3), a topological order, the tune-up API and Flight Deck's DAG state | Accepted (adds to 0036, 0026; extends 0048, 0049) |
| 0051 | `qdt-telemetry` ingests cryo context; no collector, time series, or monitoring | Accepted |
| 0052 | The sensor operating point as the first node: Coulomb diamonds → a gate parked on a peak's flank, held by the stability nodes through `levels` | Accepted (extends 0048–0050) |
| 0053 | Click-to-set: the server holds the stand's operating point (`/levels`), every sweep inherits it, Flight Deck's map click is the one "up" edge | Accepted (extends 0038; closes the default-operating-point decision) |
| 0054 | Flight Deck is a workspace of widgets: three columns, plots only in the centre, one Run; themes are data | Accepted |
| 0055 | Plot panes: any number over the shared stores, following the stream or pinned to a record through the replay stream; six at most (one WebGL2 context each); click stays click-to-set, the cut comes from the ⚙ menu | Accepted (extends 0054) |
| 0056 | One Run, bound to the compiled plan: the Sweep widget compiles and shows the plan's identity, an edit marks it stale, Run compiles again and runs; the Pulse widget's sequence travels over the bus; the panel shrinks | Accepted (extends 0054) |
| 0057 | The stand's channel state: `ChannelLevel` and `GET /levels/state` (setpoint, held, readback; null where not sensed; one live instrument set on the server); the Levels widget takes click-to-set, the limit is a browser setting; the Virtual gates widget feeds `SweepAxis.couplings` | Accepted (extends 0038, 0049, 0053, 0054) |
| 0058 | The panel is gone: Analysis and Tune-up are widgets; a record is chosen by id from History's "analyse" or a picker; no ids in form widgets, e2e drives panes | Accepted (extends 0054) |
| 0059 | The Script widget is a placeholder: the allowed API as data, stage lints and never runs; Step 6b closes on it | Accepted (extends 0054) |
| 0060 | The shot is the timeline: `capture` is an op of the pulse sequence (one record per shot, time from the capture), `step`/`ramp` are the stimulus, no `PlayedWaveform`; the executor arms the scope per point and re-keys records to shots; the OPX trigger line is the next slice | Accepted (amends 0022 additively; revises a consequence of 0047) |
| 0061 | Flight Deck follow-ups: colormaps (viridis, magma, grey) as a per-pane view setting with one LUT both renderers read; a pane remembers its view in the layout; web fonts opt-in; the UI queues runs; tune-up `c_21`/`c_12` offered to the coupling matrix; the record a plot shows is analysable | Accepted (extends 0054–0058) |
| 0062 | The sensor sits on its fitted wing: `fit_sensor_peak` (sech², width, the inflection with an error), the `sensor_wing` rule, a `sensor-wing` node that is also a retune (`InputBinding.scale/offset/held`), `CalibrationNode.holds` so the stand is held where a node decides | Accepted (extends 0030, 0049, 0050, 0052, 0053) |
| 0063 | The shot capture runs on the OPX: the scope triggers itself until it has a marker line; a digital output `do<p>` is a marker line a stand wires to a trigger input (`settings['trigger_from']` on the receiver); the executor drains a shot capture on a thread while the shots play; a shot capture's sequence paces itself | Accepted (closes 0060's trigger-line slice; extends 0047) |
| 0064 | The sequencer paces the bench: `TriggeredLevelSource` beside the frozen five (load, advance, release), `SweepAxis.stepping = "triggered"` for one innermost stepped axis the program advances by marker, the QDAC-II list mode (`trigger_in`), the simulated device its own trigger | Accepted (closes Step 6's sub-ms stepping; adds a protocol beside 0021; extends 0019, 0049); where pacing is decided superseded by 0066 |
| 0065 | What Probe 05 decided: the scope acquires by `:SINGle` (wait `:AER?`, poll `:RSTate?`) with segmented memory for several records, never `:DIGitize`; the marker leads the analog edge by 85 ns (recorded, not applied); the QDAC-II list arms with `init:cont on`, restarts past its end, reports its point on `volt?` | Accepted (amends 0063, 0064 on the bench's numbers) |
| 0066 | Pacing is the plan's: the compiler decides from the stand how each axis advances (`software`, `triggered` with its marker lines, `sequencer`) and records it in `ExecutionPlan.pacing` and the Dataset attrs; `SweepAxis.stepping` is a preference defaulting to "auto" ("triggered" required, "software" forced); the Sweep widget shows the decision and offers the override | Accepted (partly supersedes 0064; extends 0019, 0063) |
| 0067 | Readout is the sweep's choice: a DC sweep reads its sensor per point or in a one-measure shot of its sequencer, a capture records per point or in a shot from the sequencer's marker (the builders of #64); the stepping preference applies to the innermost stepped axis of any sweep with a shot; the compiler still decides the pacing | Accepted (extends 0060, 0066) |
