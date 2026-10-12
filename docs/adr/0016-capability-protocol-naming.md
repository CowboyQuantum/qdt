# 0016 — Capability protocol naming: Level/Waveform × Source/Sense, plus Sequencer; quantity lives on the channel

**Status:** Accepted
**Date:** 2026-10-12
**Step:** 2

## Context
The plan named four capability protocols: `DCSource`, `Digitizer`, `PulseSequencer`, `SourceMeasure`. The
names mix vocabularies. `DCSource` names a signal regime, `Digitizer` names a box, `PulseSequencer` names a
role, and `SourceMeasure` names an instrument class (the SMU) whose two halves are separately useful: a QDAC-II
also reads channel current, and an SMU is also a plain DC gate. `DCSource` carried the quantity in its methods
(`set_voltage`), so an SMU sourcing current would need a second verb for the same act. The protocols are
frozen at Step 2 exit (ADR 0007), and only `DCSource` existed in code, so renaming is cheap now and expensive
later. The executor (Step 2) cares about two things per terminal: whether it applies or reads a value, and
whether that value is a scalar or a record. SCPI already abstracts instruments into `SOURce` and `SENSe`
subsystems; those words carry no instrument.

## Decision
Name terminal protocols on two axes, direction × time structure: `LevelSource`, `LevelSense`, `WaveformSource`,
`WaveformSense`; add `Sequencer` as the one non-terminal protocol (a compiled, self-clocked program streaming
positional results). Drop `SourceMeasure`: a driver implements every protocol its instrument honours, and an
SMU is a `LevelSource` and a `LevelSense` on the same terminal. The physical quantity is declared on the channel
(`ChannelMap.quantity`), never in a method name; protocol methods are `set`/`get` taking floats in that
quantity's SI unit.

## Consequences
- Easier: names say what the executor needs and nothing about hardware or frequency. A `SweepDefinition`
  reads as "set levels, run the sequencer, sense a waveform". A driver claims exactly the capabilities it has:
  QDAC-II = `LevelSource` + `LevelSense`; SMU = `LevelSource` + `LevelSense`; scope = `WaveformSense`;
  OPX = `Sequencer` (owning `WaveformSource` and `WaveformSense`). Compliance is a limit on a source, not a
  capability. The conformance suite for `LevelSource` stays trivial (set 1.000, get 1.000 within tolerance);
  the load-dependent oracle belongs to `LevelSense` against the surrogate DUT (L2).
- Harder: unit safety moves from the type system to the stand configuration. `ChannelMap.quantity` is
  required, and the conformance suite and executor must check a plan binds a terminal to one role at a time:
  the executor refuses to bind one terminal as both `LevelSource` and `LevelSense` in the same plan step.
- Harder: `Sequencer` is not reducible to `WaveformSource` + `WaveformSense`. Probe 01 (ADR 0015) showed a
  compiled program has its own constraints (int-only runtime parameters, positional results, nothing in band);
  the protocol must expose them rather than hide them behind a waveform API.
- Must now: `DCSource` → `LevelSource` with `set`/`get`; `SimulatedDCSource` → `SimulatedLevelSource`;
  conformance fixture `level_source`; `ChannelMap.quantity` added (Step 2 slice, unfrozen, no migration).
  The remaining four protocols are defined in Step 2 as the executor consumes them, each with a `Simulated*`
  twin and conformance tests, and frozen together at Step 2 exit. `BENCH.md` roles renamed.

## Alternatives considered
- Keep the plan's names — rejected: `DCSource` and `Digitizer` are prescriptive in ways `PulseSequencer` is
  not (no "RF" there), and `SourceMeasure` forces the SMU's coupled semantics onto every DC gate or needs an
  alias for the SMU-as-gate case.
- `Static`/`Bias` instead of `Level` — rejected: "static" describes the signal, "bias" a purpose; "level" is
  the value itself and pairs with "waveform" on the same axis (value vs value-over-time).
- `Measure` instead of `Sense` — rejected: "measure" implies a result type; "sense" names the terminal's
  role and is the SCPI word.
- `Actuator`/`Transducer` or `Stimulus`/`Response` — rejected: more abstract, less legible at the call site;
  a physicist reading a sweep should recognise the words at once.
- Quantity in the method name (`set_voltage`, `set_current`) — rejected: doubles every verb per quantity and
  makes an SMU channel's role depend on which method was called rather than how the stand is wired.
- Keep `SourceMeasure` as a convenience alias over the two protocols — rejected: an alias that is not a
  capability invites drivers to implement it instead of the two it stands for.
