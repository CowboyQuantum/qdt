# qdt-sim — package rules

Physics models exposed behind the `qdt-lab` capability protocols (ADR 0020). `SimulatedDevice` is the L0
device-in-the-loop: one object implementing `LevelSource`, `LevelSense` and `Sequencer` for backend
`simulated`. It never touches a database (rule 4) and never imports a driver.

## Layout
```
qdt_sim/
  dot.py        # DoubleDotModel: constant-interaction electrostatics + periodic charge sensor; pure functions
  noise.py      # NoiseModel protocol: WhiteNoise, TelegraphNoise, OneOverFNoise, Composite; seeded, clocked
  device.py     # SimulatedDevice (+ DeviceNoise); interprets the SimulatedEmitter body against the model
  scenarios.py  # default_model / default_noise / default_device / default_stand / stability(...) sweeps
  __main__.py   # `python -m qdt_sim`: stream a stability diagram live for Flight Deck
```

## Rules
- The model is a pure function of (gate voltages, temperature, noise offsets). Time lives in the device
  clock only; noise processes are sampled on it. Keep it that way: no hidden state in `dot.py`.
- Every random draw comes from a seeded `numpy` Generator. A scenario with a seed reproduces bit-for-bit
  on one platform and within `rtol=1e-9` across platforms; the committed fixture test enforces it.
- Physics additions (tunnel coupling, spin, valley, Pauli blockade) are ADR-level: say what the new
  parameter means and which sweep first needs it.
- Pulses add to the DC level of the same gate (bias-tee semantics). Durations advance the clock; the
  charge state is quasi-static at each `measure`.
- Regenerate fixtures only when the model or a scenario changes: `uv run python scripts/make_sim_fixtures.py`.
