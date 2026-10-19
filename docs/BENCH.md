# BENCH — hardware-in-the-loop fixture

**Status:** SKELETON — human-authored before Step 1 driver work.
**Purpose:** the single description of the bench that `bench/` tests assume. If the bench changes, this file changes first.
Keep it generic: roles and models, not site names (rule 7).

## Instruments
Drivers: `qdt_lab.drivers` (ADR 0041). The address of each instrument is **not** recorded here (rule 7). For
the conformance suite it goes in the environment variable below; for `qdt-server --stand` it goes in a
local `*.stand.json` (gitignored; shape in `docs/examples/example_stand/bench.stand.example.json`).
**Every instrument in the stand file must answer**: `qdt-server --stand` builds all its backends together and
an unreachable one (the SMU on 2026-10-19, "connection reset by peer") fails the build on every request, which
opens and closes the others again each time (the QDAC's serial port included); take it out of the file for the
session. The OPX has come up at a self-assigned 169.254 address after a reboot (2026-10-19) as well as at its
static 10.20 one: find it by its mDNS name (`qm-<id>.local`) and give the laptop's dock port an address on the
same range (the agent's bench notes have the procedure).

| Role (protocol) | Instrument | Backend key | Address variable | Notes |
|---|---|---|---|---|
| `LevelSource` (+ `LevelSense` current readout, + `TriggeredLevelSource` list mode) | QDAC-II, Ethernet or its rear USB port | `qdac2` | `QDT_QDAC2_ADDRESS` | `TCPIP::<host>::5025::SOCKET`, or `ASRL/dev/cu.usbserial-NNNN::INSTR` (921600 baud, set by the driver; ADR 0043). The LAN address is set over USB: `syst:comm:lan:dhcp 0`, `:ipad "<ip>"`, `:smask`, `:gat`, `:upd`, then a power cycle with the cable in. A loaded list advances on `settings["trigger_in"]` (`ext1`..`ext4`, a rear trigger *input* BNC from the OPX's `do2`; ADR 0064; confirmed by Probe 05, 2026-10-16: `dc:init:cont on` re-arms per trigger, `volt?` reports the point, a trigger past the end restarts the list, latency under 0.2 ms; ADR 0065). Channels used: ch01 (`P1`), ch02 (`P2`) |
| `Sequencer`, `WaveformSource`, `WaveformSense` | OPX1000 (LF-FEM) | `qua` | `QDT_OPX_ADDRESS` | FEM slot and output mode in settings. Conformance on hardware 18/18 (2026-10-15): the suite's waveform is 0.1 V (direct mode is ±0.5 V) and its record grid starts at the trigger (the input opens its readout window there; pre-trigger samples are a scope's ability, not the protocol's). **Marker lines (ADR 0063, 0064):** `do1` → the scope's AUX TRIG IN (`scope_trigger`), `do2` → the QDAC-II's ext1 input (`dac_trigger`), `do3` → scope ch3 for Probe 05; a 400 ns marker (`MARKER_NS`) plays at a shot capture and at the top of a triggered axis. Probe 05 (2026-10-16): 3.27 V into 1 MΩ, 1.93 V into 50 Ω, 401 ns; the marker leads the analog edge by 85 ns (`MARKER_TO_ANALOG_NS`, recorded, not applied). **The FEM's digital I/O adapter must be screwed on**: without it the config is accepted and the simulator shows the markers, but nothing reaches the connectors. **Row streaming (#67) proven 2026-10-19:** a 6 × 5 pulse map with 40 ms shots delivered its rows 0.2 s apart as the program ran (`bench/test_opx_streaming.py`) |
| `WaveformSense` | Keysight InfiniiVision (X or HD3 series; an HD304MSO on the bench) | `infiniivision` | `QDT_SCOPE_ADDRESS` | `TCPIP::<host>::5025::SOCKET` (the VXI-11 `::INSTR` form refuses connections intermittently on the HD3; the socket form never did); it self-assigns a 169.254 address without DHCP. Trigger sweep must be AUTO, vertical scale set on the front panel. `:TIMebase:REFerence LEFT` is one division in from the left edge; the driver accounts for it. With `settings["trigger_from"]` (the OPX's `do1` on its AUX TRIG IN) the driver sets EXT, rising edge at `trigger_level_v` (default 1.0 V), NORMal at `arm` (ADR 0063); a shot capture that triggers itself needs NORMal on the front panel. **Acquisition is `:SINGle`, a wait for `:AER?`, a poll of `:RSTate?` (the HD3 has no `:OPERegister`), never `:DIGitize`**; with the sweep AUTO a trigger is forced after half a second (`:SINGle` waits for a real trigger even in AUTO, unlike `:DIGitize`); segmented memory for several records (ADR 0065, Probe 05). A `:DIGitize` left waiting wedges the parser until a device clear, which only HiSLIP can send (`TCPIP::<host>::hislip0::INSTR`, pyvisa `clear()`). Segments are read by index, 0.30 s each over the socket: `:WAVeform:SEGMented:ALL` on the HD304MSO (firmware 10.16) raises no error and returns a block of the right length holding the selected segment repeated, in every point mode (bench, 2026-10-19), so the driver checks the block against segments 1 and N read by index and falls back (`bench/test_scope_segments.py`) |
| `LevelSource` + `LevelSense` on one terminal | Keithley 2400-series | `keithley2400` | `QDT_SMU_ADDRESS` | legacy or 2450-style SCPI picked from `*IDN?` |

**QDAC-II quirks seen on the bench (firmware 14-1.70):**
- After a power cycle or a LAN change the analog outputs can stay at 0 V while the firmware reports every
  setpoint applied (DAC code programmed, `LAST?` equal to `VOLT?`, no error). A `*RST` brought them back
  (seen again 2026-10-16 after the power cycle that followed the ch02 finding; ch01 then worked).
  Verify one channel with a meter or the scope at the start of a bench session; the driver never resets
  on its own, because a reset zeroes every channel.
- **Settling after `set` (Probe 04, 2026-10-15):** the output edge follows `set()`'s return by less than
  4.5 ms (USB serial; steady to ±0.2 ms) and settles to 1 % in 3 µs, to 0.1 % in under 1 ms, for any
  step up to 1 V. `settle_s = 0.01` for a channel driving a high-impedance input directly; `0.05` through
  the combiner's DC side. The output filter setting (DC/MED/HIGH) made no difference to the step on this
  unit (firmware 14-1.70); the driver never sets it, and nothing here relies on it. Verify with QDevil
  before assuming a low-noise DC filter on a held gate.
- The current readout in the default (HIGH) sense range carries a common-mode error of the order of
  0.1–0.3 mA per volt of output (manual § accuracy), so a 1 MΩ load is invisible there. To use the
  current as a load check, switch `SENS<n>:RANG LOW` (nA) with the channel at 0 V.
- **The LOW current-sense range measures nothing on this unit (2026-10-15; again 2026-10-19: ±0.6 nA on ch01 and ch02 whatever flows, 1 µA into the scope's 1 MΩ included, while HIGH reads its usual tens of µA of common-mode error):** `SENS<n>:RANG LOW` reads
  back LOW and `read? (@n)` returns ≈ 2.0 nA at 0 V, 2.1 nA with 1 µA flowing (1 V into the scope's
  1 MΩ) and 2.1 nA with 1 mA flowing (0.1 V set into 50 Ω). The HIGH range works: 1 mA reads 2–3 % low
  after its ≈ +73 µA zero is taken out. With the output filter finding (Probe 04) and ch02 dying, every
  relay-switched setting of the output stage looks stuck; one report to QDevil for the three.
- **The output impedance is 50 Ω:** into the scope's 50 Ω input half the setpoint arrives. A 1 MΩ load
  sees the full setpoint (L2-1, L2-2 SMU-style loads are fine); a 50 Ω load halves it.
- **A channel went dead and stayed dead (ch02, 2026-10-15, after Probe 04 had switched its output filter
  DC → MED → HIGH → DC → HIGH):** 0 V at the scope for every setpoint, in both sense ranges, with `VOLT?`
  and `LAST?` reporting the setpoint, no error, and a HIGH-range current readout of −143 µA at 1 V set;
  `*RST` did not bring it back (unlike the outputs-at-0-V case above). ch01 kept working. **The power cycle
  revived it** (re-tested 2026-10-19: ±1 V on the scope within 2 %, filter reading HIGH), so a channel can go
  dead after filter switching until a power cycle; it goes in the QDevil report as context, with the LOW range
  and the filter as the questions.

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
                    ├─ bias tee ── out ──► OPX analog in   (stage `measure`)        [as first written]
OPX AO ─── RF port ─┘                 └──► scope ch (DC, 1 MΩ)   (capture)          [restated 2026-10-15]
```
- **Sink (human decision, 2026-10-15): the scope.** The combiner board that stands in for the bias tee
  has ≈ 25 kΩ of output impedance (Probe 03) and cannot drive the OPX's 50 Ω input, so L2-1 is restated:
  the QDAC steps the DC level, the OPX plays the pulse, and the scope's 1 MΩ input reads the sum. The
  OPX's `measure` path stays proven by the loopback runs of session 11.
- **Sweep (restated):** a capture sweep (ADR 0047): the outer axis steps the QDAC DC level (with
  `settle_s ≥ 0.05` on that channel, the board's 20 Hz low-pass), and at every point the scope captures
  one record of the pulse train the OPX plays beside the sweep (`WaveformSource.play`, as Probe 03 did).
  The record's Dataset is (V_DC, time): a heatmap in Flight Deck, rows the DC level, columns time; the
  pulse plateau's level against V_DC and the pulse amplitude is the plane.
  - As first written (buffer into the OPX input): a stage sweep of the same shape as the simulator's
    stability diagram, outer axis the QDAC level, inner axis the OPX pulse amplitude swept in the stage,
    `measure` on the OPX input. Kept here for a bench that has the buffer.
- **Oracle:** a plane, V = c_DC·V_DC + c_P·V_pulse + offset.
  - c_P ≈ 1 minus the bias tee's insertion loss (matched 50 Ω RF path).
  - c_DC = R_in / (R_in + R_DC), where R_DC is the bias tee's DC-port series resistance and R_in is the
    sink's input impedance.
- **Fit:** a plane (a curated `qdt-analysis` method, new in Step 5). The overlays are iso-voltage lines,
  slope −c_DC/c_P, the analogue of a charge transition.
- **Pass:** c_DC and c_P within the combined specification. The record is listed in the registry, and
  the overlay is drawn live in Flight Deck.
- **Pulse length:** ≤ 1 % of the bias tee's low-frequency time constant, so the droop stays below 1 %.

**Run 2026-10-15 (session 15, scope as sink):** all three L2 rows pass through the control path
(`bench/test_l2_capture.py`, against a running `qdt-server --stand` that owns the QDAC and the scope;
the OPX pulse train is played beside the sweep). L2-1 DC: plane `slope_row` 0.385–0.386 V/V against
1/2.589; with the pulse on, unchanged, and the plateau gain 0.595 against 0.61 from Probe 03's record.
L2-3: τ 2.0 µs against 1.86 µs by the same fit on Probe 03's record. Trigger convention: the scope
triggers on its own input, rising edge, **AC-coupled** (so a pulse on a stepped DC level keeps
triggering), at 40 % of the pulse's expected height; a level at the pulse's height triggers marginally
and the AUTO sweep free-runs. A sweep leaves its last level on the QDAC (ADR 0038 holds levels, never
zeroes them): a capture that wants 0 V on the DC input holds it through `levels`.

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
- **Run 2026-10-15 (`bench/test_l2_current_readout.py`):** SMU row passes: −1.9989, −0.9995, +0.9994,
  +1.9988 µA at ±2 and ±1 V (R = 1.0006 MΩ). The 2450's current measure range is held at 10 µA: left to
  autorange it drops to 10 nA at 0 V, and a source behind a 10 nA measure range charges the cable at
  10 nA, so the next level arrives late (the scope still read the previous level 0.1 s after the set).
  QDAC row passes **into the 50 Ω input in the HIGH range** (±1 mA at ±0.1 V set; the QDAC's 50 Ω
  output impedance halves the level at the scope, confirmed): slope against V_scope / 50 Ω within the
  budget, zero ≈ +73 µA. The row as specified (1 MΩ, LOW sense range) could not run on this unit: see
  the QDAC-II quirks (the LOW range reads ≈ 2 nA for any current).

### L2-3: the bias tee's droop, a real exponential
- **Setup:** an OPX step (a long pulse) into the RF port, with the bias tee output on the scope (DC, high
  Z, or terminated per the bias tee's datasheet). Through the server (ADR 0047): a capture sweep with no
  axis, `captured = [{channel: scope1, start_s, stop_s, num, records}]`, the OPX pulse train played
  beside it; the scope's trigger is set on the instrument (level, edge, source), not by the sweep. The
  stand file lists the scope with `waveform_sense` and a voltage channel on its input. The measurement's
  honest shape is one shot, `step(rf, …); capture(scope1, …)` (ADR 0060); since ADR 0063 the OPX runs
  it: `bench/test_l2_paced.py` posts the one-shot form (`step(P2_pulse, 0.25 V, 16 ns); capture(scope1,
  29 µs); wait(50 ms)`), the scope triggering itself on the analog edge (AC, NORMal sweep) when its stand
  entry has no `trigger_from`, on the OPX's marker when it has. The per-point form above stays as the reference it is compared against. **Run
  2026-10-19 (session 23), both ways, passes:** the scope triggering itself on the analog edge gives τ 1.82 µs
  (amplitude 0.055 V, plateau 0.142 V, r² 0.998); triggered by the OPX's marker on `do1`, τ 1.81 µs (amplitude
  0.060 V, r² 0.995); Probe 03's record gives 1.86 µs by the same fit. The record's amplitude is the pulse-side
  handover (0.81 − 0.59 of 0.25 V) and its plateau the DC gain (0.59 × 0.25 V), as Probe 03 measured.
- **Oracle:** V(t) = A·e^(−t/τ) after the edge. τ is the bias tee's low-frequency time constant,
  1/(2π f_low) from its datasheet.
- **Fit:** a single exponential (`qdt_analysis.exponential.fit_exponential`, ADR 0046) → `tau`, `amplitude`,
  `offset` with standard errors; `span` keeps the pulse's falling edge out of the window.
- **Pass:** τ within the bias tee's specification. This also exercises `WaveformSense` on a real
  waveform.

### L2-4: a triggered staircase (the sequencer paces the DAC; ADR 0064, 0065)
```
OPX do2 ──► QDAC-II ext1 (input)      OPX do1 ──► scope AUX TRIG IN
QDAC ch01 ──► scope ch2 (DC, 1 MΩ; no board)
```
- **Sweep:** a triggered axis `V` on `P1`, −1 … +1 V in 5 points, with a stage on the OPX whose shot
  is `capture(scope<n>, 2 ms, 200); wait(50 ms)`. The QDAC is loaded once (`QDac2.load`), the OPX's
  outer loop plays a marker on `do2` per point and waits the channel's settle, the shot's marker on
  `do1` triggers one segment of the scope's segmented acquisition (ADR 0065).
- **Oracle:** the plane fit over the (V, time) map has `slope_row` 1 (the level arrives as is into
  1 MΩ) within the scope's gain accuracy, and the fit sees every row (no missed trigger).
- **Run 2026-10-16 (session 21, `bench/reports/2026-10-16-step6.md`): passes** through
  `qdt-server --stand` after Probe 05 and ADR 0065: five records at −1, −0.5, 0, 0.5, 1 V (means
  −1.016, −0.509, −0.003, +0.500, +1.005 V direct on the executor), the sweep in 4 s with a 50 ms shot,
  the DAC holding its last point. `QDT_L2_STAIRCASE=1 QDT_L2_STAIRCASE_SCOPE_CHANNEL=2` with QDAC ch01 on
  scope ch2. The first attempt, through one `:DIGitize` per record, missed every second marker.
- **Run 2026-10-19 from the UI (session 23): passes.** The Sweep widget's capture kind, outer P1 (−1 … 1 V, 5
  points), scope2 read in the shot, pacing auto: the plan box says "P1: triggered on dac_trigger"; the plane fit
  on the record gives `slope_row` 1.010 V/V, offset −4 mV, r² 1.000; the DAC holds +1.0 V afterwards (readback
  and scope agree). The first attempt left the DAC at −0.5 V: the SMU in the stand file was unreachable, every
  Levels poll rebuilt and closed the backends, a serial query failed, and the replies on the QDAC's serial
  port shifted by one, so `release` read P2's setpoint as P1's. The VISA transport now discards pending input
  before every query. The SMU answered again later that afternoon (a stale session had held its socket); its
  conformance rows pass (the day's report, 16:42 UTC) and it is back in the stand file.

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
