# 0021 — Capability protocols frozen; backends are constructed from their channel declarations

**Status:** Accepted
**Date:** 2026-10-12
**Step:** 2

## Context
ADR 0007 planned two deliberate freezes: the `Dataset` stream contract (Step 1, ADR 0015) and the capability
protocols (Step 2). ADR 0016 named the five protocols (`LevelSource`, `LevelSense`, `WaveformSource`,
`WaveformSense`, `Sequencer`), and ADR 0017 fixed their signatures. ADR 0017 also moved settle and integration
times out of method arguments and onto `ChannelMap`. Step 2 then exercised the protocols end to end:
`compile_sweep` and `Executor` drive `SimulatedDevice` through `LevelSource`, `LevelSense` and `Sequencer`,
`python -m qdt_sim` streams the result into Flight Deck, and the human confirmed on 2026-10-12 that the live
map renders.

The pre-freeze review compared each signature with what the executor and `SimulatedDevice` actually needed.
It found one gap and one exposure:

- **Channel declarations had no path to the backend.** `ChannelMap.quantity` and `ChannelMap.integration_s`
  were declared, and `LevelSense.sense` was documented to honour the integration time. But the methods take
  only a channel string, the executor never passed the declarations on, and `SimulatedDevice` used its own
  constructor argument instead. No conformance test covered it, so a Step 5 SMU driver had no defined way to
  learn its aperture.
- **The waveform protocols have no consumer yet.** `WaveformSource` and `WaveformSense` are implemented only
  by their `Simulated*` twins and covered only by conformance. Scope captures per stepped point were deferred
  by ADR 0019, so neither the executor nor `SimulatedDevice` calls them.

## Decision
Freeze all five protocols with the signatures they have at commit 60ae1c7, and fix how a backend learns its
channel declarations. Every backend is built by a `BackendFactory`,
`(instrument: InstrumentConfig, channels: tuple[ChannelMap, ...]) -> backend`, and is given the stand's
`ChannelMap`s for that instrument (`StandConfig.instrument_channels`). From then on it honours each channel's
quantity and integration time on every call.

## Consequences
- Easier: a driver's whole configuration surface is one call. `build_backends(stand, {backend: factory})`
  wires a stand, and a driver can reject a channel or quantity it cannot serve at construction time rather
  than mid-sweep. `SimulatedDevice.from_config` already does this: it checks that gate channels are declared
  `voltage` and the sensor `current`. The method signatures did not change, so no consumer moved.
- Easier: the integration time is now spec. The conformance test `sense_honours_declared_integration_time`
  requires that a sense on a channel declared with `integration_s = T` takes at least `T` of wall time. The
  simulated twin meets it by sleeping. `SimulatedDevice` advances its device clock instead, which its own
  test checks.
- Harder: the waveform protocols are frozen before a real call site has used them. If the Step 5 scope
  driver or the deferred per-point captures need a different shape, that is a superseding ADR, with every
  twin, the conformance suite and every consumer changed in the same commit.
- Harder: channel declarations are fixed for a backend's lifetime. Changing an aperture mid-session means
  building a new backend from an edited stand, which is deliberate, because the stand is the record of what
  ran.
- Must now: every driver has a `from_config` classmethod, or another `BackendFactory`
  (`packages/qdt-lab/CLAUDE.md`, `/add-driver`). Any change to a protocol method, to `CompiledProgram`, or to
  the factory signature is a new ADR that supersedes this one. A new capability is a new protocol, which is
  also ADR-level (ADR 0016). Settle time stays the executor's job: it is the only consumer that knows when a
  level changed.

## Alternatives considered
- A `configure(channel, ChannelMap)` method on `LevelSource` and `LevelSense`, called by the executor before
  a run. Rejected: it changes every protocol and twin, lets declarations change between calls (so the stand
  stops being the record), and still needs a construction step for instrument-level settings.
- Pass the declarations per call, e.g. `sense(channel, integration_s)`. Rejected: ADR 0016 and ADR 0017 kept
  channel declarations out of method signatures, so an SMU's `sense` would differ from a DMM's in
  everything but name.
- Freeze only `LevelSource`, `LevelSense` and `Sequencer`, and leave the waveform protocols provisional until
  their first consumer lands. This was proposed in review and declined by the human: ADR 0007 planned the
  freeze for all five, and the twins plus conformance already pin their behaviour. A change found later
  costs one superseding ADR.
