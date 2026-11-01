# qdt-lab — package rules

Instrument capability protocols, vendor drivers, simulated backends, the `Dataset` stream server (Step 1), the experiment compiler/executor (Step 2), and real drivers (Step 5). This package never touches a database (rule 4).

## Layout (target; grows with the steps)
```
qdt_lab/
  protocols/         # LevelSource, LevelSense, WaveformSource, WaveformSense, Sequencer — typing.Protocol classes (ADR 0016); TriggeredLevelSource (ADR 0064) and BatchedLevelSense (ADR 0093) beside them
  simulated/         # one Simulated* per protocol; the L0 backends; instrument.py: SimulatedInstrument, the sequencer interpreter over a SimulatedPhysics (ADR 0087)
  drivers/<vendor>/  # real drivers + their SCPI emulators; vendor SDK imported lazily (ADR 0041)
  drivers/scpi.py    # the shared SCPI transport; drivers/__init__.FACTORIES maps backend keys to factories
  conformance/       # ONE suite, parametrized over backends; the spec for any driver
  stream/            # Dataset stream server + synthetic/replay sources (Step 1)
  experiment/        # compile_sweep, Executor, Emitter protocol + SimulatedEmitter (ADR 0018/0019)
```

## Adding a driver (`/add-driver`)
- It implements every existing protocol its instrument honours (an SMU is `LevelSource` + `LevelSense`). A new protocol is an ADR-level decision; names follow the `<Level|Waveform><Source|Sense>` grid plus `Sequencer` (ADR 0016).
- The physical quantity (voltage, current), settle time and integration time are declared on the channel in `ChannelMap`, never in a method name. `LevelSource.get` is the setpoint; `LevelSense.sense` is the measurement.
- Construction is the `BackendFactory` convention (ADR 0021): `factory(instrument: InstrumentConfig, channels: tuple[ChannelMap, ...])`, usually a `from_config` classmethod. The driver keeps each channel's quantity and integration time from there and honours them on every call; it raises ValueError for a channel or quantity it cannot serve. `build_backends(stand, {backend: factory})` wires a stand.
- The five protocols are frozen (ADR 0021). A signature change is a superseding ADR, not an edit. `BatchedLevelSense` (ADR 0093) is optional: the executor reads a DC sweep's inner axis in one `sense_along` call when the inner channel, its companions and the sensed channel are one such backend, else point by point; the simulated instrument also reads each line of a staged sweep in one batch when its physics has `sense_many` and nothing is captured.
- Anything that produces arrays (`WaveformSense.arm`, `Sequencer.run`) is handed the `Dataset` to fill and returns a stream `Source` for it (ADR 0017). The backend puts data on the declared grid; the consumer never aligns.
- Vendor SDK goes in `pyproject.toml` under `[project.optional-dependencies]` as an extra — never core. Check its pins against `qdt-schemas` first; report conflicts rather than downgrading schemas (ADR 0006).
- Do not write new tests. Register the backend in `tests/conftest.py` parametrization twice: on its emulator (CI) and on the instrument under `hardware` (address from a `QDT_*_ADDRESS` variable, skipped when unset). The suite must pass unchanged on `Simulated*`, the emulator and the instrument. A SCPI driver ships an emulator that rejects unknown commands (ADR 0041).
- Add the loopback row to `docs/BENCH.md` and the bench test in `bench/` with a numeric oracle and tolerance.

## Conformance suite is the spec
Test names describe required behavior ("set_level_then_get_returns_within_tolerance"). If a driver needs behavior the suite does not test, the suite is incomplete — extend it, then implement.

## The simulated instrument (ADR 0087)
`simulated/instrument.py` is the sequencer interpreter every simulated stand runs: channels and roles, the bias tee's sum, triggered lists, captures, shot reduction and frames. What it is connected to is a `SimulatedPhysics` (inputs, one output, default levels, a clock it owns, `hold` and `sense`); `qdt-sim` supplies the real one, and `LinearPhysics` is the test double the conformance suites use. Physics never lives here, and the module keeps to general words (ADR 0079). A change in how the interpreter advances the clock or sums levels changes every simulator fixture: prove it bit-identical, or regenerate them in the same commit.
