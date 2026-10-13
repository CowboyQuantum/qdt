# 0030 — The charge sensor is a biased SET: source–drain bias in `qdt-sim`, Coulomb diamonds as a sweep and a method

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
linear-response peak current at the new default bias `sensor_bias_v` (50 µV).
`DoubleDotModel.diamond_edges(k)` gives the two edge lines through the k-th degeneracy point
(`V_sd = ±2α_s(φ_s − φ_k)`); their meeting point is the apex at `V_sd = E_c/e`. That is the injection
truth for diamonds, as `charge_lattice` is for transitions (ADR 0029).

`SimulatedDevice` gains the channel role `bias`: its DC level starts at `sensor_bias_v`, pulse channels
add to it (bias-tee semantics as for gates), and every `read` passes the summed bias to the model. The
default stand declares `bias` and `bias_pulse`. `qdt_sim.scenarios.diamonds` steps the sensor gate and
the bias by their DC lines and senses the sensor: a DC-only sweep with a `SensedLevel`.
`default_device(model=...)` takes a replaced model, so a diamond characterisation names its colder sensor
(`dataclasses.replace(default_model(), sensor_width_v=0.01)`, kT_s ≈ 20 µeV).

`qdt_analysis.transitions.detect_segments` is the detection stage of ADR 0029's method, now a public
function (same thresholds, non-maximum suppression, families, runs). `qdt_analysis.diamonds.
detect_diamonds` reuses it for the edges and adds the estimation stage: zero-bias crossings clustered
into degeneracy points, the period, median slopes per family, the apexes, `E_c = e·V_apex`, lever arm
`E_c / period`, reported as `Estimate`s. Edges, degeneracy points and complete diamonds are annotations;
fewer than two degeneracy points or no complete diamond is `status="failed"`.

The committed stability fixture (`stability_24x32.npy`) is regenerated: the model changed (the
finite-bias current at 50 µV differs from the sech² train by about one percent).

## Consequences
- Easier: diamonds run end to end on simulated data with the truth in the model, so the diamond
  estimator has an injection–recovery test in CI that checks E_c, period, lever arm and slopes against
  the model, not only edge positions. Every Step 2–4 sweep behaves as before to about one percent, and
  the lattice estimate of ADR 0029 is unaffected (the honeycomb's periodicity does not depend on bias).
- Harder: the sensor is warm by construction. Keeping `sensor_width_v` = 40 mV as its thermal width at
  `α_s` = 4 meV/V means `kT_s` ≈ 80 µeV (≈ 0.9 K), far above the dots' 0.15 K, so blockade is soft near
  the apex and diamond edges are about `kT_s/α_s` = 20 mV wide in φ_s. A colder sensor is a smaller
  `sensor_width_v`, which also shortens the monotonic flank the stability diagrams rely on (ADR 0020);
  that trade-off is a per-scenario parameter choice, not a model change.
- Harder: the diamond estimator is only as good as the edges. At the stability default width the thermal
  tails of neighbouring edges overlap into gradient blobs around and beyond every apex, blob fits take
  wrong slopes, and E_c comes out about 30 % low on a 64×64 map. The test and the intended use therefore
  run a cold sensor; a detector that survives warm edges (fitting the current model directly) is a later
  method version.
- Harder: symmetric leads only (`μ_S = −μ_D = eV_sd/2`): diamonds are symmetric, both slopes equal in
  magnitude, and E_c is read from either apex. Asymmetric lever arms are a parameter to add when a
  scenario needs tilted diamonds.
- Must now: a bias role channel is a `voltage`; a device without one reads at the model's default bias.
  Transport through the double dot (bias triangles) stays a Step 6 ADR. Edge-based methods share
  `detect_segments`; a change to it bumps both methods' `VERSION`.

## Alternatives considered
- Bias across the double dot (series transport, bias triangles) — rejected for now: it needs tunnel
  coupling and interdot rates the model does not have (ADR 0020), and the step asks for diamonds.
- Keep the zero-bias sech² formula when the bias channel is unset and use the finite-bias formula only
  when it is driven — rejected: two formulas for one sensor, and a quantity that depends on wiring.
- A separate sensor temperature parameter with the dots' 0.15 K — rejected: it sharpens the sensor's
  peaks to ~6 mV, which puts sensor stripes into every stability diagram and changes Step 2–4 physics
  more than the fixture regeneration does.
- A second detector for diamond edges — rejected: ADR 0029's detection stage already finds straight
  ridges in two direction families; sharing it keeps one tuned threshold and one NMS.
- Defer diamonds to Step 6 — rejected by the human.
