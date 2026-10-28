# qdt-sim — package rules

An adapter over a pinned Phantom release behind the `qdt-lab` capability protocols (ADR 0020, 0087,
0088). `SimulatedDevice` is the L0 device-in-the-loop: `qdt_lab.simulated.SimulatedInstrument` (the
sequencer interpreter) over `PhantomPhysics`, one Phantom `Session` per run, implementing `LevelSource`,
`LevelSense`, `Sequencer` and `TriggeredLevelSource` for backend `simulated`. It contains no physics,
never touches a database (rule 4) and never imports a driver.

## Layout
```
qdt_sim/
  device.py      # PhantomPhysics (the SimulatedPhysics over a Phantom session) + SimulatedDevice; roles(device): the stand's channels
  scenarios.py   # DEVICES (file → SHA-256), load_device, programmed, provenance; default_device / default_stand; stability(...) / diamonds(...) about the programmed point; device_for / lattice_truth / sensor_truth for a SimScenario
  recipes.json   # how each device file is compiled: layout, programmed point, disorder seed
  devices/*.json # Phantom's canonical device files, written only by scripts/make_sim_devices.py
```

## Rules
- Phantom is this package's dependency alone, pinned by git tag in the root `pyproject.toml`
  (`uv.lock` carries the commit), and reached only through `phantom.api`; `scripts/check_imports.py`
  enforces both. A pin moves in a pull request of its own (ADR 0087).
- Stay under 300 lines of source (Phantom's Step 8 exit; `test_device.py` pins it). Physics, truth and
  device parameters are Phantom's: rename, never compute. A quantity Phantom does not give is a Phantom
  issue, not code here.
- A device file changes only through `uv run python scripts/make_sim_devices.py`, which compiles every
  recipe and prints the hashes for `DEVICES`; then regenerate the fixtures
  (`scripts/make_sim_fixtures.py`, `scripts/make_tuning_fixtures.py`). `check_all` recompiles the recipes
  (`--check`) and runs `python -m phantom.contract` on every device file.
- Every random draw is Phantom's, seeded: the device's disorder by the file, the run's noise by the noise
  seed (`seed`). A scenario reproduces bit for bit on one platform and within `rtol=1e-9` across
  platforms; the committed fixtures enforce it.
- Voltages are programmed ones; every gate defaults to the device's programmed point, the bias to 50 µV.
  Pulses add to the DC level of the same gate (bias-tee semantics); that summing, and how durations
  advance the clock, is the interpreter's in qdt-lab. Charge dynamics are off: a sample's charge is an
  independent Boltzmann draw (or the mean with `sample_charge=False`).
- Phantom's readout noise is physical: its white floor scales as √(1 ms / dwell). A sweep that must see
  transitions integrates for milliseconds (`MEASURE_NS`, the server's `SIMULATED_NODES`).
- A test that needs the truth gets it from the device (`Device.truth`, through `lattice_truth`,
  `sensor_truth`, or `load_device().truth(...)`), never from a hand-written expectation; the noise-free
  oracle for a reading is `load_device().at(v)`. Truth never leaves through a server route.
