# Probe 04 — How fast the QDAC-II settles after `set`

**Status:** PLANNED 2026-10-15 (script written: `bench/probes/probe04/qdac_settling.py`; run pending a
direct QDAC → scope cable). Fixtures land in `bench/fixtures/probe04/` (`settling.json`, one `.npz`
per record).
**Gates:** `ChannelMap.settle_s` for QDAC channels in stand files, and the answer to "how long after a
DC step may a pulse sequence and its acquisition start" in an untriggered stepped sweep (the executor
sets, settles, then runs the stage, ADR 0019).

## What this is
A stepped sweep has no handshake between the DC source and the sequencer: the executor calls
`LevelSource.set`, sleeps `settle_s`, then runs the stage. `settle_s` must cover two things the sweep
cannot see:

1. **Command latency** — from `set()` returning on the host (the driver writes `sour<n>:volt` and does
   not wait for an acknowledgement) to the output starting to move: USB-serial transfer, the QDAC's
   command parsing, the DAC update.
2. **Analog settling** — the output filter (QDAC-II: DC ≈ 10 Hz, MED ≈ 10 kHz, HIGH ≈ 300 kHz, the
   manual's nominal cutoffs) and the DAC's own slew, which depend on the step size.

The probe measures both for each filter and for 10 mV, 100 mV and 1 V steps, three repeats each.

## What you need
- QDAC-II (USB serial), InfiniiVision HD3 on the switch; `[qdac]`, `[keysight]` extras.
- **QDAC ch02 → scope ch2 directly** (DC, 1 MΩ): no combiner board, whose 20 Hz DC side (τ = 7.9 ms,
  Probe 03) would hide the QDAC entirely. The L2 wiring on ch01 / scope ch1 stays as it is.
- Nothing else on the QDAC's serial port (stop `qdt-server --stand` first: one process per port).

## Procedure
```
uv run python bench/probes/probe04/qdac_settling.py --qdac "ASRL/dev/cu.usbserial-NNNN::INSTR" \
    --scope "TCPIP::<scope>::5025::SOCKET" --qdac-channel 2 --scope-channel 2
```
Per (filter, step): the channel sits at 0 V; the scope is armed single-shot (`:SINGle`, NORMal sweep)
on a rising edge at half the step, timebase sized to ≈ 15 nominal time constants with the trigger one
division in; `set(step)` is timed on the host; the scope's trigger event register is polled with host
timestamps; the record is read and the metrics extracted. The channel's filter is restored at the end.

Metrics per record: base and final level, 10–90 % rise, time (from the trigger) to stay within 1 % and
within max(0.1 %, 1 mV) of the final level, overshoot, noise. Host side: the `set()` call's duration
and the time from its return to the trigger first seen (a bound at the poll's round trip, ≈ 1 ms).

## Findings
_Pending the run._

| Filter | Step | `set()` call | return → trigger seen | 10–90 % | settled 1 % | settled fine | overshoot |
|---|---|---|---|---|---|---|---|

## What the findings decide
- `settle_s` per QDAC channel in stand files, by filter: the command latency plus the fine settling time
  for the largest step the sweep takes, with margin.
- Whether the executor's "set, sleep, run" is enough for fast stepped sweeps or a hardware handshake
  (the QDAC's trigger output into the OPX, or the OPX driving the step) is needed for Step 6's rates.
- Which filter a stand file should declare for a gate that is stepped (fast settle) versus one that is
  held (low noise); today the driver never touches the filter.
