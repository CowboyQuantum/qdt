# BENCH — hardware-in-the-loop fixture

**Status:** SKELETON — human-authored before Step 1 driver work.
**Purpose:** the single description of the bench that `bench/` tests assume. If the bench changes, this file changes first.
Keep it generic: roles and models, not site names (rule 7).

## Instruments
Drivers: `qdt_lab.drivers` (ADR 0041). The address of each instrument is **not** recorded here (rule 7). For
the conformance suite it goes in the environment variable below; for `qdt-server --stand` it goes in a
local `*.stand.json` (gitignored; shape in `docs/examples/example_stand/bench.stand.example.json`).

| Role (protocol) | Instrument | Backend key | Address variable | Notes |
|---|---|---|---|---|
| `LevelSource` (+ `LevelSense` current readout) | QDAC-II, Ethernet or its rear USB port | `qdac2` | `QDT_QDAC2_ADDRESS` | `TCPIP::<host>::5025::SOCKET`, or `ASRL/dev/cu.usbserial-NNNN::INSTR` (921600 baud, set by the driver; ADR 0043). The LAN address is set over USB: `syst:comm:lan:dhcp 0`, `:ipad "<ip>"`, `:smask`, `:gat`, `:upd`, then a power cycle with the cable in. Channels used: TODO |
| `Sequencer`, `WaveformSource`, `WaveformSense` | OPX1000 (LF-FEM) | `qua` | `QDT_OPX_ADDRESS` | FEM slot and output mode in settings |
| `WaveformSense` | Keysight InfiniiVision (X or HD3 series; an HD304MSO on the bench) | `infiniivision` | `QDT_SCOPE_ADDRESS` | `TCPIP::<host>::5025::SOCKET` (the VXI-11 `::INSTR` form refuses connections intermittently on the HD3; the socket form never did); it self-assigns a 169.254 address without DHCP. Trigger sweep must be AUTO, vertical scale set on the front panel. `:TIMebase:REFerence LEFT` is one division in from the left edge; the driver accounts for it |
| `LevelSource` + `LevelSense` on one terminal | Keithley 2400-series | `keithley2400` | `QDT_SMU_ADDRESS` | legacy or 2450-style SCPI picked from `*IDN?` |

**QDAC-II quirks seen on the bench (firmware 14-1.70):**
- After a power cycle or a LAN change the analog outputs can stay at 0 V while the firmware reports every
  setpoint applied (DAC code programmed, `LAST?` equal to `VOLT?`, no error). A `*RST` brought them back.
  Verify one channel with a meter or the scope at the start of a bench session; the driver never resets
  on its own, because a reset zeroes every channel.
- The current readout in the default (HIGH) sense range carries a common-mode error of the order of
  0.1–0.3 mA per volt of output (manual § accuracy), so a 1 MΩ load is invisible there. To use the
  current as a load check, switch `SENS<n>:RANG LOW` (nA) with the channel at 0 V.

First bench run: `uv run pytest packages/qdt-lab -m hardware` with the variables exported. It runs the same
conformance suite the emulators pass in CI. The OPX calibration constants
(`INTEGRATION_TO_VOLTS`, `RAW_ADC_TO_VOLTS`, `TIME_OF_FLIGHT_NS` in `opx1000.py`) were measured by Probe 02
(`docs/probes/02-opx-input-calibration.md`, ao1 → ai1 loopback; ADR 0044).

## Loopback map (L1)
One BNC is moved between the sources and one scope input; `QDT_L1_SOURCES` (default `qdac,smu,opx`) names
the sources cabled right now, the rest skip. `bench/test_l1_loopback.py`.

| Source → Sink | Oracle | Tolerance |
|---|---|---|
| QDAC ch01 (`QDT_L1_QDAC_CHANNEL`) → scope ch 1 (`QDT_L1_SCOPE_CHANNEL`), DC 1 MΩ, 0.5 V/div | set V (0, ±0.5, ±1.5), read the mean of one record through `WaveformSense` | scope single-cursor DC accuracy: ±[1.5 % FS + 0.1 div + 1 mV + 1.5 % of offset + 0.08 % FS] = ±114 mV at 0.5 V/div (FS = 8 div, HD3 datasheet); QDAC output error not budgeted (20-bit, calibrated) |
| SMU force terminals (front, banana → BNC) → the same scope input, DC 1 MΩ, 0.5 V/div | set V (0, ±0.5, ±1.5) through `LevelSource`, read the mean of one record through `WaveformSense` | the same scope formula, ±114 mV at 0.5 V/div; 2450 source accuracy ±(0.015 % + 300 µV) on 2 V, ±(0.015 % + 2.4 mV) on 20 V, not budgeted |
| OPX LF-FEM ao1 (`QDT_L1_OPX_CHANNEL`), direct mode → the same scope input, DC **50 Ω**, 0.1 V/div, edge trigger at half amplitude | a repeating 0.25 V, 1 µs pulse (4 µs period) through `WaveformSource.play`; one record through `WaveformSense`; amplitude = plateau mean − baseline, width = time between half-amplitude crossings | amplitude: the scope DC formula at 0.1 V/div (±23 mV) + the 50 Ω input's ±1.5 % of 0.25 V (≈ ±27 mV total); no published LF-FEM DAC accuracy, none budgeted; width: 4 ns clock + 2 grid steps (±6 ns) |

## L2: instrument-on-instrument (ADR 0040; closes Open Decision #10)

**The combiner board (Probe 03, 2026-10-14)** is the part on the bench that adds the QDAC level and the
OPX pulse; it stands in for the bias tee below. Measured (`docs/probes/03-combiner-board.md`):
DC-side division 2.525 open circuit, a **20 Hz low-pass** (τ = 7.9 ms: settle ≥ 50 ms per DC step);
pulse-side gain 0.81 above 200 kHz and 0.59 at DC (division ≈ 1.65 open circuit), 2 ns edge, 14 % droop
over 30 µs; **output impedance ≈ 25 kΩ**, so its sink must be high-impedance (the scope's 1 MΩ, or a
unity-gain buffer before the OPX's 50 Ω input); the two inputs add to 3 mV. Ground switches up.

There is no surrogate DUT board. The L2 tests use the bench's instruments reading each other, plus two
off-the-shelf parts: a **bias tee** and the **scope's DC-coupled 1 MΩ input**. Specifications below are
taken from the instruments' and the bias tee's datasheets. The test code computes pass thresholds from
them. No site tolerance is written here (rule 7).

### L2-1: DC + pulse through the bias tee (Step 5 exit run)
```
QDAC ch ── DC port ─┐
                    ├─ bias tee ── out ──► OPX analog in   (stage `measure`)
OPX AO ─── RF port ─┘
```
- **Sweep:** a stage sweep of the same shape as the simulator's stability diagram (`qdt_sim.scenarios`).
  - Outer axis: the QDAC DC level, stepped. Its operating point is set with `SweepDefinition.levels`
    (ADR 0038).
  - Inner axis: the OPX pulse amplitude, swept in the stage.
  - Per pixel: step to the amplitude, wait, `measure` on the OPX input.
- **Oracle:** a plane, V = c_DC·V_DC + c_P·V_pulse + offset.
  - c_P ≈ 1 minus the bias tee's insertion loss (matched 50 Ω RF path).
  - c_DC = R_in / (R_in + R_DC), where R_DC is the bias tee's DC-port series resistance and R_in is the
    sink's input impedance.
- **Fit:** a plane (a curated `qdt-analysis` method, new in Step 5). The overlays are iso-voltage lines,
  slope −c_DC/c_P, the analogue of a charge transition.
- **Pass:** c_DC and c_P within the combined specification. The record is listed in the registry, and
  the overlay is drawn live in Flight Deck.
- **Pulse length:** ≤ 1 % of the bias tee's low-frequency time constant, so the droop stays below 1 %.

### L2-2: current readout into a known load
```
QDAC ch ──► scope ch (DC, 1 MΩ)        SMU F/S ──► scope ch (DC, 1 MΩ)
```
- **Sweep:** a 1-D level sweep, for example −2 … +2 V. The instrument reads its own current (`LevelSense`
  in current), and the scope confirms the voltage.
- **Oracle:** I = V / R_scope, with R_scope = 1 MΩ to the scope's input-impedance specification (1 µA per
  volt). This is also ADR 0016's load-dependent `LevelSense` oracle.
- **Fit:** a line through the origin. Slope 1/R_scope, within the specs of the instrument's current
  range and the scope's input impedance.

### L2-3: the bias tee's droop, a real exponential
- **Setup:** an OPX step (a long pulse) into the RF port, with the bias tee output on the scope (DC, high
  Z, or terminated per the bias tee's datasheet).
- **Oracle:** V(t) = A·e^(−t/τ) after the edge. τ is the bias tee's low-frequency time constant,
  1/(2π f_low) from its datasheet.
- **Fit:** a single exponential (a curated method, new in Step 5) → τ, A.
- **Pass:** τ within the bias tee's specification. This also exercises `WaveformSense` on a real
  waveform.

### To fill in before Step 5 builds the L2 suite (human)
- **Bias tee model:** low-frequency cutoff, DC-port resistance, insertion loss, and maximum DC
  current/voltage. Record the model, not a serial number.
- **The sink for L2-1:** check that V_DC / (R_DC + 50 Ω) stays within the QDAC channel's output-current
  specification and the OPX input range at the planned DC span. If it doesn't, narrow the span or add a
  high-impedance buffer before the OPX input.
- **QDAC current-readout range and resolution at 1 µA/V (L2-2).** If it is too coarse, use a larger span
  or rely on the SMU's current readout for the oracle.
- **Scope input impedance specification** (1 MΩ ± its tolerance), used as the reference in L2-2.
## Reports
Every run that executes a `hardware` test appends a section to `bench/reports/YYYY-MM-DD-step<N>.md`
(`scripts/bench_report.py`, a pytest plugin loaded from `pyproject.toml`; `bench_step` names N). The
section records the commit, the command, per-backend counts and per-test outcomes, with every address
redacted (rule 7). Commit the report: the repo must always show when hardware was last proven.
