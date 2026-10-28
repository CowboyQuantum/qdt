# qdt-sim — package rules

Physics models exposed behind the `qdt-lab` capability protocols (ADR 0020). `SimulatedDevice` is the L0
device-in-the-loop: `qdt_lab.simulated.SimulatedInstrument` (the sequencer interpreter, ADR 0087) over
`DoubleDotPhysics`, implementing `LevelSource`, `LevelSense`, `Sequencer` and `TriggeredLevelSource` for
backend `simulated`. It never touches a database (rule 4) and never imports a driver. Step 6d replaces
the physics with an adapter over a pinned Phantom release (ADR 0087; issue #140).

## Layout
```
qdt_sim/
  dot.py        # DoubleDotModel: constant-interaction electrostatics + biased sensor SET (ADR 0030); pure functions; charge_lattice / diamond_edges are the truth
  noise.py      # NoiseModel protocol: WhiteNoise, TelegraphNoise, OneOverFNoise, Composite; seeded, clocked
  device.py     # DoubleDotPhysics (the SimulatedPhysics over the model and DeviceNoise) + SimulatedDevice, the instrument over it
  scenarios.py  # default_model / default_noise / default_device(model=...) / default_stand / stability(...) and diamonds(...) sweeps
  __main__.py   # `python -m qdt_sim`: stream a stability diagram live for Flight Deck
```

## Rules
- The model is a pure function of (gate voltages, temperature, noise offsets). Time lives in the device
  clock only; noise processes are sampled on it. Keep it that way: no hidden state in `dot.py`.
- Every random draw comes from a seeded `numpy` Generator. A scenario with a seed reproduces bit-for-bit
  on one platform and within `rtol=1e-9` across platforms; the committed fixture test enforces it.
- Physics additions (tunnel coupling, spin, valley, Pauli blockade) are ADR-level: say what the new
  parameter means and which sweep first needs it.
- Pulses add to the DC level of the same gate (bias-tee semantics); the `bias` role (sensor source–drain
  voltage) adds likewise and starts at the model's `sensor_bias_v`. That summing, and how durations
  advance the clock, is the interpreter's, in qdt-lab; this package only answers `hold` and `sense`. The
  charge state is quasi-static at each reading.
- A test that needs the truth gets it from the model (`charge_lattice`, `diamond_edges`), never from a
  hand-written expectation. A scenario that needs other model parameters passes
  `default_device(model=dataclasses.replace(default_model(), ...))`.
- Regenerate fixtures only when the model or a scenario changes: `uv run python scripts/make_sim_fixtures.py`.
