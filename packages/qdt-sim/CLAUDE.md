# qdt-sim — package rules

Physics models exposed behind the `qdt-lab` capability protocols (ADR 0020). `SimulatedDevice` is the L0
device-in-the-loop: one object implementing `LevelSource`, `LevelSense` and `Sequencer` for backend
`simulated`. It never touches a database (rule 4) and never imports a driver.

## Layout
```
qdt_sim/
  dot.py        # DoubleDotModel: constant-interaction electrostatics + biased sensor SET (ADR 0031); pure functions; ground_state/transition_map/diamond_edges are the truth
  noise.py      # NoiseModel protocol: WhiteNoise, TelegraphNoise, OneOverFNoise, Composite; seeded, clocked
  device.py     # SimulatedDevice (+ DeviceNoise); interprets the SimulatedEmitter body against the model
  scenarios.py  # default_* / stability / diamonds sweeps; SCENARIOS + resolve(ScenarioRef) → (definition, stand, device)
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
  voltage) adds likewise and starts at the model's `sensor_bias_v`. Durations advance the clock; the
  charge state is quasi-static at each `measure`.
- A named scenario is a `SCENARIOS` entry; `resolve` routes `ScenarioRef.parameters` by name (device
  options, scalar model fields, `<axis>_start`/`_stop` ranges, sweep arguments). A test that needs the
  truth gets it from the model via the ref, never from a hand-written expectation.
- Regenerate fixtures only when the model or a scenario changes: `uv run python scripts/make_sim_fixtures.py`.
