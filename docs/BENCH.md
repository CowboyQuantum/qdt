# BENCH — hardware-in-the-loop fixture

**Status:** SKELETON — human-authored before Step 1 driver work.
**Purpose:** the single description of the bench that `bench/` tests assume. If the bench changes, this file changes first.
Keep it generic: roles and models, not site names (rule 7).

## Instruments
| Role (protocol) | Instrument | Address | Notes |
|---|---|---|---|
| `LevelSource` (+ `LevelSense` current readout) | QDAC-II | TODO | channels used: TODO |
| `Sequencer` (owns `WaveformSource`, `WaveformSense`) | OPX | TODO | |
| `WaveformSense` | Keysight benchtop scope (model TODO) | TODO | |
| `LevelSource` + `LevelSense` on one terminal | benchtop SMU (model TODO) | TODO | |

## Loopback map (L1)
| Source → Sink | Oracle | Tolerance |
|---|---|---|
| QDAC ch N → scope ch 1 | set V, read V | TODO |
| SMU → scope ch 2 | set V, read V | TODO |
| OPX analog out → scope ch 3 | known pulse amplitude/width | TODO |

## Surrogate DUT (L2) — plan Open Decision #10
Proposed: resistor divider + RC leg + diode on one board. Record here: schematic, part values, expected
analytic response (IV for the diode leg, divider ratio, RC time constant), and the first hand-measured
golden fixture (`bench/fixtures/dut_golden_v1.*`).

## Reports
Every `-m hardware` run writes `bench/reports/YYYY-MM-DD-<step>.md` and is committed. The repo must always
show when hardware was last proven.
