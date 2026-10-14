# Probe 03 — The combiner board

**Status:** DONE 2026-10-14 (findings below). Script: `bench/probes/probe03/combiner_probe.py`;
fixtures `bench/fixtures/probe03/` (`combiner.json`, step and sine records as `.npz`).
**Gates:** the L2 wiring in `docs/BENCH.md`. The board replaces the bias tee of ADR 0040 as the part that
adds a QDAC DC level and an OPX pulse into one line. Its divisions, bandwidth and output impedance decide
what sink it can drive, how fast a DC sweep may step, and how long a pulse may be.

## What this is
The board has a DC input (QDAC ch01), a pulse input (OPX LF-FEM ao1) and one output. Nominal divisions:
2.5 on the DC side, about 1.8 on the pulse side. One probe measures, through the drivers:
- the DC division from a set of QDAC levels, and from a hand meter the open-circuit value and the output
  impedance;
- the DC side's time constant from a 0 → 1 V step, and its frequency response from the QDAC's own sine
  generator (20 Hz – 20 kHz);
- the pulse side's division, edge speed and droop from a long OPX pulse, and its frequency response from
  OPX sines (20 kHz – 5 MHz), all played through `WaveformSource.play`;
- superposition: a QDAC level and an OPX pulse at once.

The sink is the scope's 1 MΩ input (`WaveformSense`), not the OPX's 50 Ω input: see finding 1.

## What you need
- QDAC-II (USB serial that day), OPX1000 LF-FEM, InfiniiVision HD3 on the switch; `[qdac]`, `[opx]`,
  `[keysight]` extras.
- QDAC ch01 → board DC in; OPX ao1 → board pulse in; board out → scope ch1 (DC, 1 MΩ). The board's
  ground switches **up** (the first attempt had them grounding the inputs).
- A hand meter reading of the board output with 1 V on the QDAC side (`--meter-mv`).

## Procedure
```
uv run python bench/probes/probe03/combiner_probe.py --qdac "ASRL/dev/cu.usbserial-NNNN::INSTR" \
    --opx <qm-host> --scope "TCPIP::<scope>::5025::SOCKET" --meter-mv 396 \
    [--sections dc_qdac,step_qdac,step_opx,superposition,sines_opx,sines_qdac]
```
Amplitudes stay at ≤ 1 V on the QDAC side and ≤ 0.25 V on the OPX side. Sections accumulate in
`combiner.json`, so one can be rerun alone.

## Findings
Run 2026-10-14 (HD304MSO at 1 MΩ as the sink; meter 396 mV at 1 V on the QDAC side).

| Item | Measured | Note |
|---|---|---|
| DC-side division, open circuit | **2.525** | from the meter (10 MΩ) |
| DC-side division into 1 MΩ | 2.589 | five levels ±1 V, residual 1.7 mV, offset −2.1 mV |
| **Board output impedance** | **≈ 25 kΩ** | from the meter-vs-scope difference |
| DC-side time constant | **τ = 7.9 ms**, 10–90 % in 18 ms, f₋₃dB ≈ 20 Hz | 0 → 1 V step; 34 % at 1 ms, 78 % at 10 ms, settled at 50 ms |
| DC-side frequency response | −3.2 dB at 20 Hz, −18 dB at 100 Hz, nothing above 500 Hz | QDAC sine generator, 1 Vpp |
| Pulse-side edge | **2 ns** 10–90 % (sample-limited) | ≥ 175 MHz from the edge |
| Pulse-side gain, 200 kHz – 5 MHz | **0.81** flat (division 1.23 into 1 MΩ) | sines at 0.2 V |
| Pulse-side gain, 100 / 50 / 20 kHz | 0.75 / 0.66 / 0.60 | the capacitive path handing over to the resistive one |
| Pulse-side gain at DC (30 µs plateau) | 0.59 (division 1.69 into 1 MΩ, ≈ 1.65 open circuit) | the nominal "about 1.8" is this DC value |
| Pulse droop over 30 µs | 14 % | from the 0.81 → 0.59 transition, time constants of µs to 100s of µs |
| Superposition | baseline 0.188 V vs 0.191 V expected; pulse 0.1477 V with the DC on vs 0.1476 V alone | adds to 3 mV |

Three findings:
1. **The board needs a high-impedance sink.** With ≈ 25 kΩ of output impedance, the OPX's 50 Ω input
   divides the output by ≈ 500 (0.5 mV per volt of QDAC level was all the OPX saw). A resistor cannot
   fix that; a unity-gain buffer at the board output can, or the sink is the scope. L2-1 as written
   (sink = OPX input) needs the buffer; the 1 MΩ scope does L2-2.
2. **The DC side is a 20 Hz low-pass.** A DC sweep through this board must settle ≥ 50 ms per step
   (`ChannelMap.settle_s`), or the map smears along the outer axis.
3. **The pulse side is not a flat divider.** 0.81 above 200 kHz, 0.59 at DC, with a 14 % droop over
   30 µs. A pulse of a few µs sees ≈ 0.75–0.81; a level held for 100 µs sees ≈ 0.6. Its edge is fast.

Two driver bugs surfaced on the way and are fixed in `qdt_lab.drivers.qm.opx1000`: looped waveform
playback on the sticky stage element walked to the rail (a non-sticky twin element plays waveforms now),
and the first sine records were taken before the OPX had reloaded its machine (the probe settles 2 s).

## What the findings decide
- `docs/BENCH.md` § L2: the combiner's numbers, the sink rule and the settle time.
- Whether L2-1 gets a buffer (sink = OPX input, as the step defines it) or is restated with the scope
  as the sink (human).
- The pulse length for L2-1 (≤ a few µs for a flat response, or budget the droop).
