# Probe 05 — The sequencer's marker lines: the scope's trigger and the DAC's list advance

**Status:** DONE 2026-10-16 (findings below; ADR 0065). Script: `bench/probes/probe05/sequencer_markers.py`;
fixtures `bench/fixtures/probe05/` (`markers.json`, one `.npz` per record).
**Gates:** `MARKER_NS` and the marker-to-analog offset in `qdt_lab.drivers.qm.opx1000` (ADR 0063);
`trigger_level_v` for the scope in stand files; how the scope acquires a shot capture's records
(ADR 0065); the QDAC-II list-mode commands, the first-trigger behaviour and the trigger-to-output
latency behind `QDac2.load` (ADR 0064, 0065).

## What this is
ADR 0063 and 0064 make the OPX's digital outputs marker lines: at a shot capture the OPX plays a
marker to the scope's EXT TRIG input, and at the top of a triggered axis a marker to the QDAC-II's
external trigger input advances a loaded list. The drivers assume a marker level, a marker length and
a list-mode command set from the manuals; the executor assumes the scope re-arms fast enough between
records. This probe measures each.

## What you need
- OPX1000 (LF-FEM), InfiniiVision HD3, QDAC-II (USB serial); `[opx]`, `[keysight]`, `[qdac]` extras.
- Nothing else on the QDAC's serial port (stop `qdt-server --stand` first).
- Cables (all BNC):

| From | To | Section |
|---|---|---|
| OPX LF-FEM ao1 | scope ch1, 50 Ω | marker, pacing (the analog edge) |
| OPX do1 | scope EXT TRIG IN (rear) | all (the scope's trigger line) |
| OPX do2 | scope ch2, 1 MΩ | marker (the marker itself: level, width) |
| OPX do2 | QDAC-II ext1 (rear) | qdac (move the same cable) |
| QDAC-II ch01 | scope ch3, 1 MΩ | qdac (the staircase) |

Check the FEM's digital output specification before cabling do2 into the QDAC's input: both are
LVTTL-class, and the marker section reports the level before the qdac section needs it.

## Procedure
```
uv run python bench/probes/probe05/sequencer_markers.py --opx <qm-host> \
    --scope "TCPIP::<scope>::5025::SOCKET" --qdac "ASRL/dev/cu.usbserial-NNNN::INSTR" \
    [--fem 1] [--sections marker,pacing,qdac] [--qdac-channel 1] [--qdac-trigger ext1] \
    [--qdac-scope-channel 2]
```
Sections run one at a time merge into `markers.json`. A `:DIGitize` left waiting by an earlier
session blocks the scope's parser; the probe fires markers first, and the drivers no longer use
`:DIGitize` (ADR 0065). A stuck scope is freed by a device clear over HiSLIP
(`TCPIP::<scope>::hislip0::INSTR`, pyvisa `clear()`); the raw socket cannot send one.
The OPX runs the driver's own config (`Opx1000.config()` with the two lines), so the elements, the
`marker` pulse and `MARKER_NS` are what a sweep uses.

1. **marker** (5 repeats): one shot of [marker on do1 | marker on do3 | a 0.25 V, 2 µs step on ao1],
   the scope single-shot on EXT, 4 µs window. From ch3: the marker's high and low level into 1 MΩ and
   its width at half level. From ch1: the analog edge's time in the EXT-triggered record, which is the
   marker-to-analog delay (t = 0 is the marker at the EXT input). The EXT level is set to half the
   measured marker level after the first repeat.
2. **pacing**: the scope through the driver (`InfiniiVisionX` with `external_trigger_level_v`, so
   `arm` sets EXT, NORMal), armed for 10 records under an endless marker train s apart, for s = 500,
   200, 100, 50, 20 ms: records received, and the time per record (the capture cycle through one
   `:SINGle` per record, or the readout per segment once the driver acquires segmented). Then whether
   `:ACQuire:MODE SEGMented` is accepted.
3. **qdac** (3 repeats): ch01 set to −0.25 V (a level no list point has), then `QDac2.load` with
   (0, 0.25, 0.5, 0.75, 1.0) V on `trigger_in` ext1; the scope single-shot on EXT with a 650 ms
   window; the OPX plays one marker on do1 (the scope's trigger) and then 5 markers on do2, 100 ms
   apart. From ch2: the level before the first do2 marker (did `init` move the output?), each step's
   edge time against its marker's time (trigger-to-output latency), the time each step takes to
   settle within 1 % (Probe 04's metric), the plateau levels, and the count of steps against markers.

Everything lands in `--out` as `.npz` (records) and `markers.json` (findings).

## Findings
Run 2026-10-16: OPX1000 LF-FEM 1 (QOP 3.7.1, qm-qua 1.4.1), HD304MSO, QDAC-II firmware 14-1.70 over
USB serial. Fixtures in `bench/fixtures/probe05/`.

| Item | Value |
|---|---|
| marker high / low into 1 MΩ (ch3) | 3.27 V / 0.00 V; into 50 Ω 1.93 V |
| marker width | 401 ns (`MARKER_NS` 400) |
| marker edge in an EXT-triggered record | +6 to +8 ns |
| marker-to-analog delay (do1/do3 marker → ao1 edge, same shot) | **85 ns**, 5 of 5 repeats (the simulator said 172) |
| records per 10 markers, one `:SINGle` per record (first pass) | 10/10 at 500 ms; 1 record per 3, 5, 9, 22 markers at 200, 100, 50, 20 ms: **0.43–0.50 s per record** |
| records per 10 markers, segmented acquisition (driver after ADR 0065) | **10/10 at every spacing down to 20 ms**; readout 0.31–0.50 s per segment afterwards |
| segmented mode accepted | yes (`:ACQuire:MODE?` reads SEGM, no error); `:WAVeform:SEGMented:COUNt?` counts segments as they land; `:RSTate?` reads SING until the last one |
| `:OPERegister:CONDition?` | undefined header on the HD3; `:RSTate?` (RUN / SING / STOP) is the run state |
| QDAC list commands accepted | all, no error; `sour:volt?` in list mode reports the point last played |
| QDAC `dc:init` alone | the first trigger plays point 0 and nothing after it: the trigger system goes idle; **`dc:init:cont on`** re-arms after every trigger |
| output moved at arm, before the first marker | no (−0.25 V held until the first marker) |
| a trigger after the last point | **starts the list again at point 0** (does not hold) |
| trigger-to-output latency (ext1, 400 ns marker) | median 0.01 ms, within ±0.07 ms: below the 0.16 ms sample of the 650 ms record |
| settle within 1 % per step (0.25 V steps into 1 MΩ) | below one sample (0.16 ms) |
| steps per 5 markers, 3 repeats | 5/5, 5/5, 5/5 (0, 0.25, 0.5, 0.75, 1.0 V) |
| QDAC after its power cycle | outputs at 0 V with the setpoint reported, again (BENCH.md's quirk); `*RST` brought them back |

## What the findings decide
- `EXT_TRIGGER_LEVEL_V` stays 1.0 V (a third of the marker into the AUX input); `MARKER_NS` stays 400.
- The marker-to-analog delay, 85 ns, is recorded in the driver as `MARKER_TO_ANALOG_NS` and in ADR
  0065, not applied: a record's t = 0 is the marker; the op's analog effect lands 85 ns later, below
  any scope window a shot capture declares.
- The scope driver acquires by `:SINGle`, waits for `:AER?`, polls `:RSTate?`, and with more than one
  record uses segmented memory (ADR 0065): a shot capture's sequence no longer paces itself to the
  scope; the bench rows wait 50 ms, for the settle, not the scope.
- `QDac2.load` arms with `dc:init:cont on`; `get` queries the instrument in list mode; a trigger past
  the end restarts the list, so the protocol says so and a caller plays one trigger per point
  (ADR 0065 amends 0064's "holds after the last").
- `settle_s` for a triggered QDAC channel into a high-impedance input: the trigger-to-output latency
  and the settle are both under 0.2 ms; `0.01` stays the stand file's value with margin.
