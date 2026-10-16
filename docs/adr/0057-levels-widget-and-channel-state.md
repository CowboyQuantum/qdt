# 0057 — The stand's channel state: `GET /levels/state` with setpoint, held level and readback; the Levels and Virtual gates widgets

**Status:** Accepted
**Date:** 2026-10-16
**Step:** 6b (deliverable 4; extends 0038, 0049, 0053, 0054)

## Context
ADR 0053 gave the server a held operating point (`/levels`: the DC levels every sweep inherits) and
Flight Deck a click-to-set edge. The Step 6b spec asks for an operating-point widget over every channel of
the stand with readbacks, filterable and pinnable, with an inline set that refuses a level beyond a limit.
Three things were undecided: what a "readback" is for a gate, what the server returns for a channel that
cannot be sensed, and where a limit comes from. The simulator also rebuilds its device per run, seeded by
the run's options, so "set now, read later" had nowhere to live.

## Decision
- **A new control-slice object, `ChannelLevel`** (additive beside `Run`, `MethodSpec`, `TuneUp`): one
  channel's `channel`, `instrument`, `quantity`, `setpoint` (what the `LevelSource` reports it applies,
  `get`), `held` (the server's operating point for it, ADR 0053) and `readback` (what the `LevelSense`
  senses on it). Never stored.
- **A new endpoint, `GET /levels/state`** → `list[ChannelLevel]`: every channel whose instrument declares
  `level_source` or `level_sense`. `/levels` (GET/POST/DELETE) is unchanged.
- **Null, not omitted.** `setpoint` is null when the instrument is not a `LevelSource` or refuses the
  channel; `readback` is null when the instrument declares no `level_sense` or refuses to sense the channel.
  The simulated device senses its sensor and refuses its gates ("sense the sensor"), so in the simulator
  the gates read back null and the sensor reads back the current at the operating point. A real SMU or a
  QDAC-II with a readout fills the gate column. A refusal is a `ValueError` or `KeyError` from the backend,
  caught per channel; anything else propagates.
- **The server keeps one live instrument set.** `RunManager.live_backends()` builds the backends once and
  keeps them: a level set now is the level read back later, and the sensor readback follows the gates. On
  hardware these are the same objects every run uses (`stand_backends`). On the simulator a run still
  builds its own seeded device; the live set is the stand's standing state and knows nothing of where a
  run left its own device. That is the simulator's limitation, stated, not papered over.
- **The limit is a browser setting** (default ±1 in the channel's SI unit, editable in the widget,
  remembered per browser). The stand declares no limits yet; a `ChannelMap` field is an additive change
  for the day a stand needs one, and the widget would prefer it.
- **Click-to-set moves to the Levels widget.** The plot offers a point (`map:click`); the widget turns the
  coordinates that are DC channels into levels and sets them (the pure `setpointFor` moved with it). The
  panel's operating-point section is gone.
- **The Virtual gates widget** is a coupling matrix over the stand's DC channels, per browser: a row is a
  gate used as a stepped axis, its entries the volts per volt other gates move with it. It publishes the
  matrix (`gates:couplings`); the Sweep widget gives each stepped axis its row as `SweepAxis.couplings`
  (ADR 0049), never the inner axis of a stage sweep (that couples in the pulse sequence; the pure builder
  refuses it). The sweep form now exposes couplings, closing a Step 6 gap.

## Consequences
- Easier: the operating point is one table with what was asked, what the instrument holds and what it
  reads; the sensor current at the operating point is live in the simulator; a virtual-gate sweep can be
  crafted in the UI.
- Harder: the widget polls (2 s) because nothing pushes channel state; a readback costs a `sense` per
  channel per poll, which on hardware honours integration times (a slow aperture makes the poll slow; the
  interval is the widget's, not the server's, and can grow). The simulator's live device and a run's
  device diverge after a run.
- The panel keeps records, analysis and the tune-up runner only; deliverable 5 deletes it.

## Alternatives considered
- Change `GET /levels` to return the richer rows — rejected: a response-shape change on a frozen-slice
  endpoint for the sake of one fewer route.
- Omit the readback field when there is none — rejected: a row with a missing key reads as a schema
  drift in the generated client; null says "asked, none".
- Limits in the `ChannelMap` now — deferred: a stand-slice change needs a stand that has limits to declare.
