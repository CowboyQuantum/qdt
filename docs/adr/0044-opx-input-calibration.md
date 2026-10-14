# 0044 — OPX1000 LF-FEM input constants are measured values: inverted, 1.155 × 2⁻¹², 180 ns of flight

**Status:** Accepted
**Date:** 2026-10-14
**Step:** 5

## Context
The OPX driver (ADR 0041) turns what the LF-FEM records into volts with two constants, `RAW_ADC_TO_VOLTS`
for raw ADC traces (`WaveformSense`) and `INTEGRATION_TO_VOLTS` for integrated measures (`Sequencer`),
and places the start of a record with `TIME_OF_FLIGHT_NS`. All three were assumptions at the driver's
first write (2⁻¹², 2¹², 24 ns), marked "confirm on bench". They set the numbers in every Dataset the OPX
produces, so the simulator-first steps never saw them and the control path cannot be trusted on real
hardware until they are measured.

The L1 pulse row (BENCH.md) had verified the output side with the scope: a 0.25 V setpoint on LF-FEM
analog output 1 arrives as 253.9 mV into 50 Ω. Moving that cable to the LF-FEM's analog input 1 puts a
known voltage on the input.

## Decision
Probe 02 (`docs/probes/02-opx-input-calibration.md`, `bench/probes/probe02/`) measured them, and the
driver now carries the measured values with their provenance in the docstrings:

| Constant | Was | Is | How |
|---|---|---|---|
| `RAW_ADC_TO_VOLTS` | 2⁻¹² = +2.441e-4 | **−2.820e-4** | slope of true volts vs raw plateau mean, five amplitudes ±0.25 V, 20 shots each, residual < 0.3 mV |
| `INTEGRATION_TO_VOLTS` | 2¹² = +4096 | **−4731** | slope of true volts vs the 1 µs constant-weight integral on the same shots, × window; agrees with the raw path to 0.5 % |
| `TIME_OF_FLIGHT_NS` | 24 | **180** | QOP 3.7 rejects < 28 and non-multiples of 4; with 28 the pulse edge lands 147 ns into an aligned readout, with 176 at 4 ns |

- **The sign is the instrument's.** The LF-FEM input reads inverted relative to its output. The driver
  keeps the measured negative constants rather than a separate sign flip, so one number per path says
  everything, and a future FEM or firmware that reads upright changes one number.
- **The input offset is not applied.** 0 V in reads −1.7 mV; the config's `analog_inputs.offset` stays
  0.0. Revisit if a method needs better than a few millivolts of absolute accuracy.
- **Two runs, both kept** (`bench/fixtures/probe02/`, compressed): the constants reproduce to 0.1 %.

## Consequences
- Every OPX-produced value changes scale and sign relative to what the driver would have reported before
  the bench; nothing recorded on hardware predates this, so no stored record is affected.
- `TIME_OF_FLIGHT_NS = 24` would have failed on this QOP, which the conformance suite never caught: the
  scope is its only hardware `WaveformSense`, and the Sequencer test uses no input. A hardware
  `WaveformSense` row for the OPX input belongs in the suite (not added here: the suite's grid oracle
  needs a signal source on the input, which is a bench loopback, not a conformance fixture).
- The offline OPX tests use the constant symbolically and pass unchanged; the emulator-less OPX path is
  still validated offline only.
- Probe 02 is the pattern for any instrument whose readout scale is a datasheet claim: a loopback from
  a verified source, a fit over several levels, the fixture committed.
