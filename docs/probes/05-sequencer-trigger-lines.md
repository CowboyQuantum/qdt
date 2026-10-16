# Probe 05 — The sequencer's marker lines: the scope's trigger and the DAC's list advance

**Status:** SPECIFIED 2026-10-16, not yet run. Script: `bench/probes/probe05/sequencer_markers.py`;
fixtures `bench/fixtures/probe05/` (`markers.json`, one `.npz` per record).
**Gates:** `MARKER_NS` and the marker-to-analog offset in `qdt_lab.drivers.qm.opx1000` (ADR 0063);
`trigger_level_v` for the scope in stand files; the shot-rate floor a shot capture's sequence must
pace itself to (ADR 0063); the QDAC-II list-mode commands, the first-trigger behaviour and the
trigger-to-output latency behind `QDac2.load` (ADR 0064). Until it has run, the bench runs the
self-trigger interim (ADR 0063) and the L2-4 staircase row is unproven.

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
    [--fem 1] [--sections marker,pacing,qdac] [--qdac-channel 1] [--qdac-trigger ext1]
```
The OPX runs the driver's own config (`Opx1000.config()` with the two lines), so the elements, the
`marker` pulse and `MARKER_NS` are what a sweep uses.

1. **marker** (5 repeats): one shot of [marker on do1 | marker on do2 | a 0.25 V, 2 µs step on ao1],
   the scope single-shot on EXT, 4 µs window. From ch2: the marker's high and low level into 1 MΩ and
   its width at half level. From ch1: the analog edge's time in the EXT-triggered record, which is the
   marker-to-analog delay (t = 0 is the marker at the EXT input). The EXT level is set to half the
   measured marker level after the first repeat.
2. **pacing**: the scope through the driver (`InfiniiVisionX` with `external_trigger_level_v`, so
   `arm` sets EXT, NORMal), armed for 10 records and drained on a thread as the executor does; the
   OPX plays 10 markers s apart for s = 500, 200, 100, 50, 20 ms; records received per s. Then
   `:ACQuire:MODE SEGMented` with a count of 10, the mode read back, the error queue read, the mode
   restored.
3. **qdac** (3 repeats): ch01 set to −0.25 V (a level no list point has), then `QDac2.load` with
   (0, 0.25, 0.5, 0.75, 1.0) V on `trigger_in` ext1; the scope single-shot on EXT with a 650 ms
   window; the OPX plays one marker on do1 (the scope's trigger) and then 5 markers on do2, 100 ms
   apart. From ch3: the level before the first do2 marker (did `init` move the output?), each step's
   edge time against its marker's time (trigger-to-output latency), the time each step takes to
   settle within 1 % (Probe 04's metric), the plateau levels, and the count of steps against markers.

Everything lands in `--out` as `.npz` (records) and `markers.json` (findings).

## Findings
Not yet run. The table to fill:

| Item | Value |
|---|---|
| marker high / low into 1 MΩ | |
| marker width | (`MARKER_NS` is 400 ns) |
| marker-to-analog delay | |
| records per 10 markers at 500 / 200 / 100 / 50 / 20 ms | |
| segmented mode accepted | |
| QDAC list commands accepted (error queue) | |
| output moved at `init`, before the first marker | |
| trigger-to-output latency, median | |
| settle within 1 % per step | |
| steps per 5 markers, 3 repeats | |

## What the findings decide
- `trigger_level_v` default (`EXT_TRIGGER_LEVEL_V`, 1.0 V) and whether `MARKER_NS` stays 400 ns.
- The marker-to-analog delay: whether the driver offsets a record's t = 0 by it (a constant like
  `TIME_OF_FLIGHT_NS`) or the ADR records it as the known offset of the capture op.
- The shot-rate floor for a self-paced shot capture, or segmented acquisition as the next scope slice.
- The QDAC-II driver's list commands as written, or corrected; whether the executor's "the output
  moves on the first trigger" holds or `init` already plays point 0 (then the driver plays one fewer
  marker's worth: the program's first marker would be dropped or the list offset by one).
- `settle_s` for a triggered channel: the trigger-to-output latency plus the analog settle, in place
  of Probe 04's serial-path figure.
