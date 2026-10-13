# 0031 — The charge sensor is a biased SET: source–drain bias in `qdt-sim`, Coulomb diamonds as a scenario

**Status:** Accepted
**Date:** 2026-10-13
**Step:** 4

## Context
Step 4's deliverables include a "Coulomb diamond pipeline (detection/estimation split)". The Step 2 model
(ADR 0020) had no bias axis anywhere: the double dot is sensed, not transported through, and the sensor
was a zero-bias conductance train (`sensor_current(φ_s) = I_bg + I_peak · sech²((φ_s − φ_k)/w)`). Nothing
simulated could show a diamond, so the pipeline had nothing to run on. The human chose on 2026-10-13 to
add a source–drain bias to the model now rather than defer diamonds to Step 6.

Where the bias goes is a modelling choice. In a charge-sensed double-dot device the transport channel
that is routinely characterised with diamonds is the sensor SET itself (its charging energy and lever arm
calibrate the sensing); transport through the double dot gives bias triangles at the triple points, which
is Step 6 physics (tunnel coupling, ADR 0020's gaps).

## Decision
The sensor is a single-electron transistor with charging energy `sensor_charging_ev` (E_c, default
1 meV) and lever arm `α_s = E_c / sensor_period_v` (one period in φ_s adds one electron). Its levels are
`μ_k = E_c·k − α_s·(φ_s − sensor_phase_v)`, and with symmetric leads at bias `V_sd` the current is
sequential tunnelling at the sensor's thermal energy `kT_s`:

    I = I_bg + I_0 · Σ_k [ f((μ_k − eV_sd/2)/kT_s) − f((μ_k + eV_sd/2)/kT_s) ],   f(x) = 1/(1+eˣ).

`kT_s = α_s · sensor_width_v / 2`, so the linear-response limit is exactly the ADR 0020 sech² train
(summed over peaks), and `I_0 = 4 kT_s · sensor_peak_a / (e · sensor_bias_v)` makes `sensor_peak_a` the
linear-response peak current at the new default bias `sensor_bias_v` (50 µV). `DoubleDotModel.
diamond_edges(k)` gives the two edge lines through the k-th degeneracy point (`V_sd = ±2α_s(φ_s − φ_k)`);
their meeting point is the apex at `V_sd = E_c/e`.

`SimulatedDevice` gains the channel role `bias`: its DC level starts at `sensor_bias_v`, pulse channels
add to it (bias-tee semantics as for gates), and every `read` passes the summed bias to the model. The
default stand declares `bias` and `bias_pulse`. `qdt_sim.scenarios.diamonds` steps the sensor gate and
the bias by their DC lines and senses the sensor (a DC-only sweep with a `SensedLevel`); it is a
`SCENARIOS` entry, so a `ScenarioRef` names it.

A `ScenarioRef` may override any scalar field of `DoubleDotModel` by name (`MODEL_PARAMETERS`), so a
diamond characterisation names its colder sensor (`sensor_width_v: 0.01`, kT_s ≈ 20 µeV) in its ref and
the truth regenerates from the ref alone.

`qdt_analysis.diamonds.coulomb_diamonds` reuses `transitions.detect` / `estimate` for the edges (two
slope families) and adds the estimation stage: zero-bias crossings clustered into degeneracy points, the
period, median slopes, the apexes, `E_c = e·V_apex`, lever arm `E_c / period`. Edges, points and complete
diamonds are annotations; the numbers are the summary.

The committed stability fixture (`stability_24x32.npy`) is regenerated: the model changed (the
finite-bias current at 50 µV differs from the sech² train by about one percent).

## Consequences
- Easier: diamonds run end to end on simulated data with the truth in the model, so the diamond
  estimator has an injection–recovery test in CI that checks E_c, period, lever arm and slopes against
  the model, not only edge positions. Every Step 2–4 sweep behaves as before to about one percent.
- Harder: the sensor is warm by construction. Keeping `sensor_width_v` = 40 mV as its thermal width at
  `α_s` = 4 meV/V means `kT_s` ≈ 80 µeV (≈ 0.9 K), far above the dots' 0.15 K, so blockade is soft near
  the apex and diamond edges are about `kT_s/α_s` = 20 mV wide in φ_s. A colder sensor is a smaller
  `sensor_width_v`, which also shortens the monotonic flank the stability diagrams rely on (ADR 0020);
  that trade-off is a parameter choice per scenario, not a model change.
- Harder: the estimator is only as good as the edges. At the stability default (`sensor_width_v` 40 mV)
  the thermal tails of neighbouring edges overlap into gradient blobs around and beyond every apex, the
  blob fits take wrong slopes, and E_c comes out about 30 % low on a 64×64 map. The diamond test and the
  intended use therefore name a cold sensor in the scenario ref; a detector that survives warm edges
  (non-maximum suppression, or fitting the current model directly) is a later improvement.
- Harder: symmetric leads only (`μ_S = −μ_D = eV_sd/2`): diamonds are symmetric, both slopes equal in
  magnitude, and E_c is read from either apex. Asymmetric lever arms are a parameter to add when a
  scenario needs tilted diamonds.
- Must now: a bias role channel is a `voltage`; a device without one reads at the model's default bias.
  Transport through the double dot (bias triangles) stays a Step 6 ADR.

## Alternatives considered
- Bias across the double dot (series transport, bias triangles) — rejected for now: it needs tunnel
  coupling and interdot rates the model does not have (ADR 0020), and the step asks for diamonds.
- Keep the zero-bias sech² formula when the bias channel is unset and use the finite-bias formula only
  when it is driven — rejected: two formulas for one sensor, and a quantity that depends on wiring.
- A separate sensor temperature parameter with the dots' 0.15 K — rejected: it sharpens the sensor's
  peaks to ~6 mV, which puts sensor stripes into every stability diagram and changes Step 2–4 physics
  more than the fixture regeneration does.
- Defer diamonds to Step 6 — rejected by the human.
