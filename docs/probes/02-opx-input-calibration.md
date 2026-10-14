# Probe 02 — OPX1000 LF-FEM input calibration

**Status:** DONE 2026-10-14 (findings below; ADR 0044). Script: `bench/probes/probe02/opx_calibration.py`.
**Gates:** the two constants in `qdt_lab.drivers.qm.opx1000` that turn what the OPX records into volts
(`RAW_ADC_TO_VOLTS`, `INTEGRATION_TO_VOLTS`), assumed at the driver's first write and marked "confirm on
bench". They set the values of every Dataset the OPX produces, so changing them is an ADR.

## What this is
The L1 pulse row (BENCH.md) proved the output side with the scope: a 0.25 V setpoint on LF-FEM analog
output 1 arrives as 253.9 mV into 50 Ω. Moving that cable from the scope to the LF-FEM's analog input 1
puts a known voltage on the input. One QUA program plays the pulse and, in the same shot, reads the input
as a raw ADC trace and as an integrated value over a window on the plateau, at five amplitudes including
zero. Linear fits of true volts against the two readings give the two constants; the zero point gives
the input offset; an aligned readout gives the pulse edge position, which checks the time of flight.

## What you need
- OPX1000 with an LF-FEM; `QDT_OPX_ADDRESS`; the `[opx]` extra.
- A BNC from LF-FEM ao1 to LF-FEM ai1 (both 50 Ω).
- The scope factor from the L1 pulse row (`--scope-gain`, measured over set amplitude; 1.0156 that day).

## Procedure
```
uv run python bench/probes/probe02/opx_calibration.py --host <qm-host> --fem 1 --out bench/fixtures/probe02
```
The program per amplitude: 20 shots of [play a 3 µs pulse on `ao` | on `ai`, wait 1 µs, then a 1 µs
measurement saving the raw trace and the constant-weight integral]. Then one 3 µs readout aligned with
the play, for the edge. Everything lands in `--out` as `.npz` (raw) and `.json` (findings).

## Findings
Run 2026-10-14, qm-qua 1.4.1, QOP 3.7, OPX1000 with one LF-FEM, ao1 → ai1 by BNC, `--scope-gain 1.0156`
(L1 pulse row). Two runs with different configured time of flight; fixtures in `bench/fixtures/probe02/`.

| Item | tof 28 | tof 176 |
|---|---|---|
| raw plateau mean at +0.25 / 0 / −0.25 V in | -907.0 / -5.4 / 894.7 | -907.2 / -5.6 / 893.9 |
| `RAW_ADC_TO_VOLTS` (fit slope, V per raw unit) | -2.8190e-04 | -2.8201e-04 |
| `INTEGRATION_TO_VOLTS` (fit slope × 1000 ns window) | -4729.5 | -4731.3 |
| fit residual, max, raw / integral | 0.20 / 0.20 mV | 0.25 / 0.25 mV |
| shot-to-shot std of the plateau mean | ≈ 0.3–0.4 raw (≈ 0.1 mV) | same |
| input offset (0 V in) | -1.62 mV | -1.72 mV |
| pulse edge index in the aligned readout | 147 ns | 4 ns |
| assumed before the bench | 2⁻¹² = 2.441e-4, 2¹² = 4096, tof 24 | |

Three findings:
1. **The input reads inverted**: a positive voltage in gives a negative raw value and a negative integral.
2. **The scale is 1.155 × 2⁻¹²** on both paths, and the two paths agree to 0.5 %. Linear to < 0.3 mV
   over ±0.25 V.
3. **Time of flight is 180 ns**, not 24: QOP 3.7 rejects anything below 28 or not a multiple of 4, and
   with 28 configured the edge sits 147 ns into the record; 176 leaves 4 ns.

## What the findings decide
- `RAW_ADC_TO_VOLTS` and `INTEGRATION_TO_VOLTS` in the driver, by ADR.
- Whether the LF-FEM input offset needs a per-channel `offset` in the config (the driver writes 0.0).
- Whether `TIME_OF_FLIGHT_NS = 24` places the record start on the pulse edge.
