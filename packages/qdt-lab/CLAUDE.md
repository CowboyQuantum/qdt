# qdt-lab — package rules

Instrument capability protocols, vendor drivers, simulated backends, the `Dataset` stream server (Step 1), the experiment compiler/executor (Step 2), and real drivers (Step 5). This package never touches a database (rule 4).

## Layout (target; grows with the steps)
```
qdt_lab/
  protocols/         # LevelSource, LevelSense, WaveformSource, WaveformSense, Sequencer — typing.Protocol classes (ADR 0016)
  simulated/         # one Simulated* per protocol; the L0 backends
  drivers/<vendor>/  # real drivers; vendor SDK imported lazily inside functions
  conformance/       # ONE suite, parametrized over backends; the spec for any driver
  stream/            # Dataset stream server + synthetic/replay sources (Step 1)
  experiment/        # compile_sweep, Executor, Emitter protocol + SimulatedEmitter (ADR 0018/0019)
```

## Adding a driver (`/add-driver`)
- It implements every existing protocol its instrument honours (an SMU is `LevelSource` + `LevelSense`). A new protocol is an ADR-level decision; names follow the `<Level|Waveform><Source|Sense>` grid plus `Sequencer` (ADR 0016).
- The physical quantity (voltage, current), settle time and integration time are declared on the channel in `ChannelMap`, never in a method name. `LevelSource.get` is the setpoint; `LevelSense.sense` is the measurement.
- Construction is the `BackendFactory` convention (ADR 0021): `factory(instrument: InstrumentConfig, channels: tuple[ChannelMap, ...])`, usually a `from_config` classmethod. The driver keeps each channel's quantity and integration time from there and honours them on every call; it raises ValueError for a channel or quantity it cannot serve. `build_backends(stand, {backend: factory})` wires a stand.
- The five protocols are frozen (ADR 0021). A signature change is a superseding ADR, not an edit.
- Anything that produces arrays (`WaveformSense.arm`, `Sequencer.run`) is handed the `Dataset` to fill and returns a stream `Source` for it (ADR 0017). The backend puts data on the declared grid; the consumer never aligns.
- Vendor SDK goes in `pyproject.toml` under `[project.optional-dependencies]` as an extra — never core. Check its pins against `qdt-schemas` first; report conflicts rather than downgrading schemas (ADR 0006).
- Do not write new tests. Register the backend in `tests/conftest.py` parametrization. The suite must pass unchanged on `Simulated*` and, under `-m hardware`, on the real instrument.
- Add the loopback row to `docs/BENCH.md` and the bench test in `bench/` with a numeric oracle and tolerance.

## Conformance suite is the spec
Test names describe required behavior ("set_level_then_get_returns_within_tolerance"). If a driver needs behavior the suite does not test, the suite is incomplete — extend it, then implement.
