# 0065 — What Probe 05 decided: the scope acquires by `:SINGle` with segmented memory, the marker leads the analog edge by 85 ns, the QDAC-II list re-arms on every trigger and restarts past its end

**Status:** Accepted
**Date:** 2026-10-16
**Step:** 6 open decision (amends 0063 and 0064 on what the bench measured)

## Context
ADR 0063 and 0064 were written off the bench with five numbers assumed and marked for Probe 05: the
marker's level and its delay to the analog edge, how fast the scope re-arms between a shot's records,
the QDAC-II's list-mode commands and what its first trigger does. The probe ran on 2026-10-16
(`docs/probes/05-sequencer-trigger-lines.md`). Three findings change code, so this ADR records them;
a merged ADR is never edited.

## Decision
- **The scope acquires by `:SINGle`, never `:DIGitize`.** `:DIGitize` blocks the instrument's parser
  until the acquisition triggers; one left waiting (a shot that never fired) wedged every later
  session until a device clear, which the raw socket cannot send (HiSLIP can:
  `TCPIP::<scope>::hislip0::INSTR`). The driver writes `:SINGle`, waits for `:AER?` to report the
  arm (the run state still reads the old value until then), then polls `:RSTate?` until STOP. The HD3
  has no `:OPERegister`. A trigger that never comes ends in `:STOP` and a TimeoutError after
  `settings["acquire_timeout_s"]` (600 s), not a wedged scope.
- **Several records are one segmented acquisition.** With more than one record the driver sets
  `:ACQuire:MODE SEGMented` and the count, reads the mode back (an instrument without the option falls
  back to one `:SINGle` per record), arms once, and reads each segment by index after the scope
  stops. One `:SINGle` per record cost 0.43–0.50 s each and lost every marker inside that; segmented,
  10 of 10 records landed at every spacing down to 20 ms. A shot capture's sequence therefore no
  longer paces itself to the scope: ADR 0063's "ends in a wait of a few hundred ms" is withdrawn; the
  bench rows wait 50 ms for the settle. The executor's `CAPTURE_ARM_GRACE_S` stays 0.5 s (the arm
  itself is a few hundred ms of SCPI).
- **The marker leads the analog edge by 85 ns**, recorded as `MARKER_TO_ANALOG_NS` in the OPX driver
  and not applied: a record's t = 0 is the marker at the scope's input; the op's analog effect lands
  85 ns later, below any window a shot capture declares. The marker is 3.27 V into 1 MΩ and 1.93 V
  into 50 Ω, 401 ns; `EXT_TRIGGER_LEVEL_V` stays 1.0 V and `MARKER_NS` 400.
- **The QDAC-II list re-arms on every trigger and restarts past its end.** `dc:init` alone arms the
  trigger system once: the first trigger played point 0 and the four after it nothing. The driver arms
  with `dc:init:cont on`; each external trigger then advances one point (5 of 5, three repeats, with
  a trigger-to-output latency and a settle both under 0.2 ms into 1 MΩ). A trigger after the last
  point starts the list again at point 0 rather than holding, so `TriggeredLevelSource.load` now says
  so and a caller plays exactly one trigger per point; the simulated source, the emulator and the
  simulated device restart likewise. `sour<n>:volt?` reports the point last played, so `get` asks the
  instrument instead of believing a counter, and `release` holds the point the channel is at.
- **A list command's bus trigger** (`*TRG`, `trigger_in: bus`) is the conformance suite's way to fire
  it; the bench's stand file uses `ext1` from the OPX's `do2`.

## Consequences
- Easier: L2-4 (the triggered staircase) passes through `qdt-server --stand` with a 50 ms shot:
  five records at −1, −0.5, 0, 0.5, 1 V, the sweep in 4 s, the DAC holding its last point.
- Easier: a wedged scope is a thing of the past for the drivers; the probe doc records the HiSLIP
  device clear for a scope wedged by anything else.
- Harder: reading segments is 0.3–0.5 s each over the socket, after the acquisition; a sweep of a
  thousand shots spends minutes in readout. Reading all segments in one transfer is a later driver
  slice.
- Harder: the LF-FEM's digital outputs need its digital I/O adapter screwed on; nothing in software
  can tell when it is not (the simulator shows the markers). BENCH.md says so.
- Harder: the QDAC-II's outputs were at 0 V again after its power cycle, with the setpoint reported,
  until `*RST` (BENCH.md's quirk, now seen twice); a bench session still starts by checking a channel.

## Alternatives considered
- Keep `:DIGitize` and lengthen the VISA timeout — rejected: the parser block, not the timeout, is
  what wedges the instrument.
- Pace the shot to the scope (0.5 s per record) instead of segmented memory — rejected: the probe
  showed the scope catches every trigger in hardware; a shot's timing should be the measurement's.
- Apply the 85 ns in the driver as a time-axis offset — rejected: the capture window is the scope's
  grid from the marker; an offset would make a declared t = 0 land before the record's first sample.
- Make the driver hide the list's restart (refuse a trigger past the end) — impossible: the
  trigger is hardware; the protocol tells the caller instead.
