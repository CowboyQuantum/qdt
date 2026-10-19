# 0070 — Captures that follow each other in a shot open together: one acquisition serves the channels a scope arms together, and two sequencer lines step in one shot

**Status:** Accepted
**Date:** 2026-10-19
**Step:** 6 follow-up (amends 0060, 0063; extends 0069; the bench row L2-6)

## Context
ADR 0060 made the shot a timeline of sequential ops, and a `capture` an op that holds the shot for
its window. Two scope channels captured in one shot were therefore two windows in turn, and the
executor armed each capture's channel as its own `WaveformSense` acquisition and started reading it
at once: on a real scope two `:SINGle`s on one instrument, racing for one trigger. A measurement the
bench had not made needs both at once: two OPX lines stepping in one shot, recorded together on two
scope channels, to measure the skew between the ports (the fridge's two-gate pulses depend on it).
The OPX side already expressed two lines: each line is a sticky element and the ops run in order, so
a step of 1 µs on one line and then a step on the other is an edge a microsecond after the first.
The human asked for the two-line acquisition on 2026-10-19, with ao1 on scope ch1 and ao2 on ch3.

## Decision
- **Captures that follow each other in a shot open together**, at the first one's point: each
  distinct marker line plays once, every own input (ADR 0069) records its window, and the shot waits
  out the longest scope window; the next op follows the longest activity. A capture after another
  op is a later window, as before.
- **A scope serves the channels armed together in one acquisition.** The executor arms every shot
  capture before it starts the first drain; the InfiniiVision driver gives channels armed before any
  of them reads one `_Acquisition`: the first source to read sends the `:SINGle` and waits for it,
  the others wait for that, and each then reads its own channel, with `:WAVeform:SOURce` selected
  before every read and the drains' reads serialised on the transport. Channels armed together share
  one window; several records through one `:SINGle` each (an instrument without segmented memory)
  stay one channel's, and a second channel is refused at `arm`. The emulator captures all four
  channels per acquisition, each with its own signal.
- **The simulated device** advances its clock once per group, by the longest scope window beyond
  what its own records took.

## Consequences
- Easier: two lines in one shot, recorded together (L2-6): the scope triggering itself on ch1's edge,
  ch3's edge a programmed microsecond later; the skew between the ports is measured, not assumed.
- Easier: a time-resolved readout can watch two things at once, a stimulus and a response, with one
  trigger and one definition.
- Harder: the group rule is positional. Two captures with an op between them are still two windows,
  and the Pulse widget's rows say nothing about grouping; the order is the user's to get right.
- Harder: the HD304MSO answered a second channel's `:WAVeform:PREamble?` with every field empty right
  after a segmented acquisition, once in four runs; the driver selects the source again and asks
  again (`PREAMBLE_RETRIES`), and the emulator reproduces it. A channel that never answers raises.
- Must now: a scope's second channel in one shot must share the first's window; L2-6 is posted with
  the scope self-triggered, since a capture cannot see an edge played before it (ADR 0063's limit).

## Alternatives considered
- A capture op naming several channels — rejected: a change to the frozen pulse vocabulary (one
  primitive per ADR), and every consumer would learn a list where the positional rule needs nothing.
- Keep one acquisition per channel and let the second `:SINGle` re-arm the first — rejected: it
  works by accident on one record and loses segments on more; the driver would be lying about what
  it acquired.
- Serialise the windows as before and accept two triggers per shot — rejected: the skew between two
  lines cannot be measured from two acquisitions.
