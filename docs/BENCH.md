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
**Status: PROPOSED (draft for human review, 2026-10-14).** Once the values are agreed, an ADR records #10
and this section becomes the spec. The board is then built and hand-characterized into the golden fixture.

**Purpose.** A passive board with a response known in closed form. It stands in for the device in the
Step 5 L2 tests, which exercise the whole chain on real instruments: definition → hardware → Flight Deck
→ registry → fit → overlay. Each leg mirrors something the simulated double dot already exercises:

| Leg | Instruments (roles) | Mirrors in the simulator | Oracle |
|---|---|---|---|
| 1 Summing divider | QDAC ch A, ch B (`LevelSource`, current `LevelSense`); SMU (`LevelSense`, voltage) | gate × gate map with lever arms (stability diagram) | a plane with known coefficients |
| 2 Diode + series R | SMU (`LevelSource` + `LevelSense` on one terminal) | a 1-D sensed sweep with a nonlinear response | Shockley with series R (Lambert W) |
| 3 RC low-pass | OPX analog out (`Sequencer`/`WaveformSource`); scope (`WaveformSense`) | a pulse sequence and a waveform capture | single-exponential step response |

The legs are independent (separate connectors, common ground), so each L2 test uses only its own
instruments.

### Schematic
```
Leg 1  QDAC A ──[R_A 10k]──┐                     Leg 2  SMU F/S ──[R_S 10k]──►|── GND
                           ├── N ──► SMU sense (V, high Z)                  D (small-signal Si)
       QDAC B ──[R_B 20k]──┤
                           └──[R_L 10k]── GND     Leg 3  OPX AO ──[R 1k]──┬── M ──► scope (1 MΩ)
                                                                          └──[C 10n]── GND
Every source line also has R_P = 1 kΩ in series at its connector (fault limiting): ≤ 5 mA into a short at
±5 V. On legs 1 and 2, R_P is inside the measured branch, so the golden fixture records R_A + R_P etc. as
measured totals. On leg 3, R_P is replaced by the 1 kΩ R itself.
```

### Parts (nominal; the fixture records measured values)
| Part | Value | Grade | Why this value |
|---|---|---|---|
| R_A, R_B, R_L | 10 kΩ, 20 kΩ, 10 kΩ | 0.1 %, thin film | unequal on purpose: the two coefficients differ (0.4 vs 0.2), so a swapped axis or channel shows |
| R_S | 10 kΩ | 0.1 % | keeps the diode current ≤ 250 µA at +3 V, and the exponential region (0.2–0.8 V) spans two decades |
| D | small-signal silicon switching diode | — | well-known SPICE parameters; reverse current is far below the SMU floor |
| R, C | 1 kΩ, 10 nF | 0.1 %; C0G/NP0 | τ ≈ 10 µs: 10⁴ samples at 1 GS/s per time constant; C0G is stable in temperature and bias |
| R_P | 1 kΩ | 1 % | fault limiting only |

### Analytic responses (nominal values; L2 tests use the measured values from the fixture)
**Leg 1.** With conductances G = 1/R:

  V_N = α_A·V_A + α_B·V_B, with α_A = G_A/ΣG = 0.400, α_B = G_B/ΣG = 0.200 (ΣG = G_A + G_B + G_L,
  output resistance 4.0 kΩ).

  The QDAC channel currents are I_A = (V_A − V_N)/R_A and I_B = (V_B − V_N)/R_B. Each is a second plane
  oracle, for the QDAC current readout. Example: V_A = +2 V, V_B = −2 V → V_N = +0.400 V, I_A = +160 µA,
  I_B = −120 µA.

  The iso-voltage lines of V_N have slope dV_B/dV_A = −α_A/α_B = −2, the analogue of a charge
  transition's slope.

**Leg 2.** I = (nV_T/R_S)·W[(I_s R_S/nV_T)·exp((V + I_s R_S)/nV_T)] − I_s, with W the Lambert W
function and V_T = kT/q (25.69 mV at 25 °C). Nominal model values: I_s ≈ 2.5 nA, n ≈ 1.75.

| V (V) | −1.0 | 0.3 | 0.5 | 0.7 | 1.0 | 2.0 | 3.0 |
|---|---|---|---|---|---|---|---|
| I (µA) | −0.0025 | 1.43 | 11.9 | 28.1 | 55.0 | 150.5 | 248.2 |

  I_s and n are temperature dependent. The fixture and every L2 report record the ambient temperature.

**Leg 3.** For a step of amplitude A from the OPX, the node voltage is V_M(t) = A_eff·(1 − e^(−t/τ)),
with τ = (R + R_src)·C.
- R_src ≈ 50 Ω is the OPX output impedance, giving τ = 10.5 µs (10.0 µs from R·C alone).
- The scope's 1 MΩ input loads the node by about 0.1 %.
- A_eff is fitted from the plateau. The OPX amplitude is specified into 50 Ω and may read up to 2× into
  this high-impedance load, so the oracle is τ, not A.
- Pulse at least 100 µs high and 100 µs low (1 % settling takes 48 µs).

### L2 tests this board serves (Step 5)
| Test | Sweep | Fit (curated `qdt-analysis` method, new in Step 5) | Pass condition |
|---|---|---|---|
| L2-1 divider surface (Step 5 exit: end to end, live in Flight Deck, recorded, overlay) | QDAC A × QDAC B, ±2 V, 21 × 21; SMU senses V_N | plane fit → α_A, α_B, offset; iso-lines as overlays | α within the combined instrument accuracy of the fixture values |
| L2-2 QDAC current readout | same sweep, QDAC current on A and B | plane fit of I_A, I_B | against (V − V_N)/R from the fixture |
| L2-3 diode IV | SMU −1 … +3 V, 401 points, current sensed | diode fit (Lambert W) → I_s, n, R_S | R_S within instrument accuracy of the fixture; n and I_s within the spread of the fixture's own fit |
| L2-4 RC step | OPX pulse sequence; scope capture | single-exponential fit → τ, A_eff | τ against (R + R_src)·C from the fixture |

Pass thresholds come from instrument specifications and the fixture's measured values, never from a site
tolerance (rule 7). The test code computes them; no number is written here.

### Golden fixture (after the board is built)
`bench/fixtures/dut_golden_v1.json`, hand-measured with a calibrated bench DMM and the scope. Fields:
- `board_revision`;
- `measured_at` (ISO date) and `ambient_c`;
- every resistor as measured, including R_P totals per branch;
- `c_nf`;
- the diode at three currents, (V_D, I) at 1 µA, 10 µA and 100 µA, which gives the fixture's own I_s, n;
- τ from a scope step capture;
- the `instrument` models used.

No serial numbers, site names or addresses (rule 7). A rebuilt or repaired board gets `dut_golden_v2`;
earlier fixtures are history, like schema fixtures.

### Open points for the human
- Board form (perfboard / PCB / breakout box) and connector type, which sets how R_P is fitted.
- Whether leg 1's output should also feed the QDAC through a second sense path, instead of the SMU, so
  that the SMU stays free for leg 2 without re-cabling.
- Diode part choice: any small-signal silicon switching diode. The fixture characterizes the actual part.
- Whether a fourth leg is wanted for `WaveformSense` on an OPX input (needs a buffer: the OPX inputs are
  50 Ω and would load leg 3).

## Reports
Every `-m hardware` run writes `bench/reports/YYYY-MM-DD-<step>.md` and is committed. The repo must always
show when hardware was last proven.
