# Probe 04 — How fast the QDAC-II settles after `set`

**Status:** DONE 2026-10-15 (findings below). Script: `bench/probes/probe04/qdac_settling.py`;
fixtures `bench/fixtures/probe04/` (`settling.json`, one `.npz` per record).
**Gates:** `ChannelMap.settle_s` for QDAC channels in stand files, and the answer to "how long after a
DC step may a pulse sequence and its acquisition start" in an untriggered stepped sweep (the executor
sets, settles, then runs the stage, ADR 0019).

## What this is
A stepped sweep has no handshake between the DC source and the sequencer: the executor calls
`LevelSource.set`, sleeps `settle_s`, then runs the stage. `settle_s` must cover two things the sweep
cannot see:

1. **Command latency** — from `set()` returning on the host (the driver writes `sour<n>:volt` over
   USB serial and does not wait for an acknowledgement) to the output starting to move.
2. **Analog settling** — the output filter (QDAC-II: DC, MED, HIGH; the manual's nominal 10 Hz, 10 kHz,
   300 kHz) and the DAC's own slew, which may depend on the step size.

The probe measures both for each filter and for 10 mV, 100 mV and 1 V steps, three repeats each, at
two timebases (400 µs for the edge, 2 ms or 250 ms for any slow tail); then the command latency by
bracketing the edge between scope trigger-register polls (12 repeats); then the latency's variation
from two `set`s 10 ms apart on the host (6 repeats).

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
Per (filter, step, timebase): the channel sits at 0 V; the scope is armed single-shot (`:SINGle`,
NORMal sweep, both event registers cleared first) on a rising edge at half the step with the trigger
one division in; `set(step)` is timed on the host; the record is read and the metrics extracted. The
channel's filter is restored at the end, also after a failure.

## Findings
Run 2026-10-15, QDAC-II firmware 14-1.70 over USB serial, HD304MSO ch2 at 1 MΩ.

**The edge, 400 µs window (100 ns per sample), medians of three:**

| Filter | Step | 10–90 % rise | within 1 % after | within max(0.1 %, 1 mV) after | overshoot |
|---|---|---|---|---|---|
| DC | 100 mV | 1.9 µs | 2.6 µs | 2.6 µs | 0.5 % |
| DC | 1 V | 1.9 µs | 2.8 µs | 241 µs | 0.14 % |
| MED | 100 mV | 1.9 µs | 2.8 µs | 2.8 µs | 0.3 % |
| MED | 1 V | 1.9 µs | 2.8 µs | 228 µs | 0.11 % |
| HIGH | 100 mV | 1.9 µs | 3.2 µs | 3.2 µs | 0.2 % |
| HIGH | 1 V | 1.9 µs | 2.7 µs | 263 µs | 0.15 % |

The 10 mV rows are noise-limited (1 % of 10 mV is 0.1 mV, the scope's floor at 2 mV/div) and are in
`settling.json` only. In the 2 ms windows the 1 V steps reach 1 mV after 556–780 µs: a tail of about
0.1 % of the step with a time constant of a few hundred µs, present for every filter. In the 250 ms
windows (DC filter) the scope's own noise is 1.07 mV rms, above the fine tolerance, and the records
show no slow component at all: a 1 V step is within 1 % from its first sample.

**Command latency (HIGH filter, 1 V step):** `set()` returns after 0.1–0.5 ms (the serial write is
buffered). The scope's trigger register, polled at its 4.5 ms round trip, read 1 on the first poll
after the set in all 12 repeats, so the output edge follows the return by **less than 4.5 ms**; the
poll cannot resolve it further. Two sets 10.2 ms apart on the host produced edges 10.06–10.39 ms apart
on the scope: the latency **varies by ±0.2 ms** between commands. The serial query round trip
(`sour2:volt?`) is 16 ms, so waiting for an acknowledgement would cost more than the latency it removes.

Three findings:
1. **The output filter setting does not change this unit's step response.** DC, MED and HIGH all show
   the same 1.9 µs edge and the same tails; a 10 Hz or 10 kHz low-pass would show a 35 ms or 35 µs
   rise. The firmware does read the setting back and refuses its sine generator under DC ("settings
   conflict" at 5–100 Hz), so the setting is known to it; MED and HIGH are also indistinguishable for
   a 100 kHz sine (0.88 of 1 Vpp through either). Whether the relays switch on this unit, or the
   firmware applies the filter only in some mode, is for QDevil or the front panel to say; the
   driver never touches the filter, and nothing in this repo relies on it.
2. **The latency is the wait.** Analog settling to 1 % takes 3 µs and to 0.1 % under 1 ms; the serial
   command path takes up to ~4.5 ms and is steady to 0.2 ms. `settle_s = 0.01` covers a direct QDAC
   channel with margin. Through the combiner's DC side the 20 Hz low-pass sets `settle_s ≥ 0.05`
   (Probe 03), unchanged.
3. **Step size does not matter** to the edge: 10 mV, 100 mV and 1 V steps rise in the same 1.9 µs
   (no slew limit at 1 V), and overshoot stays under 1 % for the steps that are above the noise.

## What the findings decide
- Stand files: `settle_s: 0.01` for a QDAC channel driving a high-impedance input directly;
  `settle_s: 0.05` through the combiner (BENCH.md).
- The executor's "set, sleep, run" is adequate at the ms level; a sweep that needs sub-ms stepping must
  move the step onto the sequencer (the OPX's own DC offset or a QDAC list with a hardware trigger),
  which is Step 6's business, not a driver change.
- A later probe on the QDAC's Ethernet link (ADR 0043 records both links) could tighten the 4.5 ms
  bound; a `*OPC?`-style acknowledgement in `set` is not worth 16 ms per point.
- The filter finding goes to the human: verify the relays on the front panel or with QDevil before a
  stand file assumes a low-noise DC filter on a held gate.
