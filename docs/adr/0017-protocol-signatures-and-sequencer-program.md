# 0017 — Protocol signatures: producers are handed the Dataset and return a stream; `SequencerProgram` is a typed envelope around an opaque body

**Status:** Accepted
**Date:** 2026-10-12
**Step:** 2

## Context
ADR 0016 fixed the five protocol names. Their signatures were open, with four questions decided with the
human on 2026-10-12:

1. Where do settle and integration times live for `LevelSense`?
2. Does `WaveformSense` return a record, or only arm and let the records flow?
3. What does the executor hand a `Sequencer`? Probe 01 (ADR 0015) showed the OPX compiles one program
   and varies step count, step size and averaging through an integer input stream; fractional values must
   travel as scaled integers; results are positional with nothing in band. A simulated sequencer cannot
   run QUA, so it needs something other than the body to know what a run produces.
4. Is `WaveformSource` reached directly before Step 5?

Two constraints shape every answer: ADR 0015 (a Dataset's declared coordinates are exact; meeting them is
the producer's job) and the executor's need to validate a run without understanding any backend language.

## Decision
Settle and integration times are channel configuration (`ChannelMap.settle_s`, `ChannelMap.integration_s`),
not method arguments. Anything that produces arrays is handed the `Dataset` it must fill and returns a
stream `Source` for it: `WaveformSense.arm(channel, dataset, variable) -> Source` and
`Sequencer.run(compiled, parameters, dataset) -> Source`. `Sequencer.compile` takes a `SequencerProgram`
(`qdt_schemas.activity`): a typed contract of integer parameters (name, unit, scale) and result streams
(name, parameter-valued dims, dtype, unit) around an opaque `body` for a named `backend`. `LevelSense.sense`
is the measurement verb, distinct from `LevelSource.get`, the setpoint. `WaveformSource` is `play`/`stop`
with a minimal simulated twin.

## Consequences
- Easier: the executor validates a run from the envelope alone (`SequencerProgram.check_run`: every
  parameter supplied as an int, every result a data variable of matching rank, sizes and dtype), so a
  simulated and a real sequencer share one conformance suite; the simulated sequencer ignores the body and
  fills results with the flat loop index, which is exactly Probe 01's program, so the positional oracle is
  the same on L0 and L1. Coordinates never pass through a backend: the executor declares them in the
  Dataset, the backend fills index regions. The scale factor from ADR 0015 has one home
  (`SequencerParameter.scale`). An SMU driver implements `get` and `sense` on one terminal without a
  collision.
- Harder: a backend must accept the executor's Dataset rather than produce its own, so a driver that
  natively names dims differently maps them by position. `WaveformSense` requires a declared
  `LinearCoordinate` on the time dim and refuses a streamed one, by design (ADR 0015); a free-running record
  dim is allowed (`size=None`). `SequencerResult.dims` ties every result axis to an integer parameter, so a
  fixed-size result needs a constant parameter.
- Must now: `SweepDefinition` (next) produces the Dataset plus a `SequencerProgram` and parameter values;
  the executor honours `settle_s` between `LevelSource.set` and `LevelSense.sense`; a driver honours
  `integration_s`. The activity slice stays unfrozen until Step 2 exit; the protocols freeze then with
  their own ADR. A real `Sequencer` registers in the conformance parametrization with its own body for the
  flat-index program.

## Alternatives considered
- Settle and integration as `sense` arguments — rejected: every caller would re-state stand facts; the
  stand configuration is where wiring-dependent timing belongs.
- `WaveformSense.capture(...) -> np.ndarray` — rejected: a blocking call per record defeats live streaming
  and leaves alignment to the caller, against ADR 0015.
- Backends build their own Dataset and the executor re-labels it — rejected: `Dataset` is frozen, so
  relabelling means re-keying every frame; handing the definition in is one line in the backend.
- Opaque `backend_payload` (a dict the schema does not inspect) — rejected: nothing validates a run before
  the OPX does, the simulated twin has nothing to emulate from, and the integer scale lives in convention.
- A fully typed program model (an IR) — rejected: out of scope (plan §10); the envelope is the smallest
  thing that lets two sequencers share a suite.
- One verb `get` for both level protocols — rejected: an SMU implements both on one terminal and the two
  readings differ (applied vs measured).
