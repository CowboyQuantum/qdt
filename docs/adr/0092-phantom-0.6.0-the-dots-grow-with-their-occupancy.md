# 0092 — Adopt Phantom 0.6.0: the dots grow with their occupancy; the lattice truth is the slope of Phantom's charge; a virtual gate's companion moves from the held operating point

**Status:** Accepted
**Date:** 2026-11-01
**Step:** 6c (the human's request; not a step deliverable)

## Context
On 2026-10-31 the human found, on Phantom 0.4.0, that the honeycomb turned into one merged dot at a
place that did not move with the middle barrier `B_M`, that the change was nearly instant along the
plungers, and that the two dots never fully merged however far `B_M` opened. qdt filed Phantom #69 and
#70. Phantom answered with two releases on 2026-11-01. `v0.5.0` (`cf9e1b2`, Phantom ADR 0034) gives the
barrier between the dots one transmission that the tunnel coupling, the interdot rate and the conductance
share, screens every gate's action on that barrier so a plunger moves it a quarter as much as `B_M`, and
lets `B_M` keep acting past the point where the dots merge. `v0.6.0` (`9b1c059`, Phantom ADR 0035, issue
#72) makes each dot a classical puddle whose radius grows as the cube root of its electron number, so the
addition energy falls and the honeycomb's cells shrink towards high occupancy, and the superdot front
moves across occupancy with `B_M`. The human asked for qdt to move to `v0.6.0`. ADR 0087 says a pin moves
in a pull request of its own that regenerates the fixtures.

What Phantom 0.6.0 changes for qdt, measured on the committed devices at the stand's starting point (the
programmed plungers, `SG` at `SENSOR_SET_V`, ADR 0090):

- **The device files.** The device-file format is now 7, and files compiled by 0.4.0 do not load. Both
  recipes recompile unchanged, the files grow from 62 kB to 81 kB, and the sensor's starting levels do not
  move, because the operating point itself is bit for bit what it was.
- **The stand starts with two separate dots.** On 0.4.0 about 40 % of the default stability window, 0.15 V
  either side of the start on both plungers, was one merged dot. On 0.6.0 it is 1 % on both devices,
  the merged dot just entering the upper-right corner. The dots hold 23 and 28 electrons on device a (20
  and 25 on device b), the tunnel coupling is 57 µeV, the triple-point splitting 0.16, and the addition
  energies 9.9 and 8.9 meV, running from 5.9 to 10.8 meV across the window.
- **`B_M` acts across the whole window, and over a wider range.** The merged share of the window is 0 at
  `B_M` 0.14 V, 20 % (15 % on device b) at 0.24 V, 75 % (67 %) at 0.30 V and 100 % from 0.40 V, where it
  stays however far `B_M` opens: with `B_M` at 1 V every plunger setting in the window is one dot holding
  34 to 47 electrons. Along the plunger diagonal at the programmed `B_M`, the splitting rises from 0.2 to
  0.9 over 106 mV (it was 15 mV on 0.4.0), and the crossing moves from +128 mV at `B_M` 0.20 V to −44 mV
  at 0.30 V. The transition starts at the window's upper right, where the dots are largest, and moves
  down and left as `B_M` opens.
- **Phantom's truth lattice is the compiled matrix, which the device no longer shows.** With the puddles
  the gate-induced charge is the compiled one times the square root of its ratio to the compiled
  occupancy, so its slope along a plunger at the operating point is exactly 3/2 of the compiled row, and
  it runs from 1.38 to 1.61 times the compiled row across the window. `Device.truth().charge_lattice_e_per_v`
  still returns the compiled rows: 20.34, 2.44, 1.71 and 26.28 electrons per volt on device a, where the
  slope of `runtime_ci().induced_charge` at the start is 30.51, 3.56, 2.65 and 39.45. The window's mean
  slope is within 0.1 % of the slope at the start. qdt's analysis reads 30.15, 3.58, 2.62 and 38.73 from a
  noise-free map, so the analysis is right and the truth is stale. Filed as Phantom #75.
- **A virtual gate's companion moved from 0 V (#176).** The `virtual-lattice` node couples `P2`'s DC line
  to the `P1` axis by `c_21`. ADR 0049 moves a companion from its level in the sweep's `levels` or from 0,
  and ADR 0053 listed coupled channels among those the stand server does not give the held operating
  point to, so `P2` ran from −0.20 to +0.12 V while the `charge-lattice` node before it had swept `P2`
  from 0.45 to 0.75 V. On 0.4.0 the lattice did not depend on the occupancy, so the node still found the
  right lattice from a sensor far off its peak and nobody noticed. On 0.6.0 the node read dot 2 at about
  12 electrons: `l_22` 25.8 against 38.7 in the first node, and a residual cross ratio of +0.049 against
  the rule's 0.05. The stand server and `run_tuneup`, which the tests call directly, both had it.
- **The spectral lattice estimate reads an uneven honeycomb low.** Because the cells shrink by about 15 %
  from the window's lower left to its upper right, the estimate lands 1 to 2 % below the slope at the
  start on the diagonal (the quiet charge lattice at −1.2 % and −1.8 %), and in the virtual gates, whose
  window sits `c_21` times the plungers' level from the first node's, up to 4 % low (`l_22` −3.6 % on
  device a, `l_11` −4.0 % on device b). The cross terms land within 0.004 and the virtual residuals
  within 0.006 of zero.
- **The noise.** Over noise seeds 0 to 9 the noisy two-node tune-up is accepted for 8 seeds: seed 5's
  virtual lattice is rejected at a residual of 0.081, and seed 7's charge lattice is rejected with a
  negative cross ratio. The committed seed 1 lands 0.5 % low on `l_11`, 0.13 e/V high on `l_12`, 0.005 off
  on `m_12`, and its virtual lattice has residuals of −0.004 and 0.000. The analysis test's 64 × 64 noisy
  map lands within 1.5 % on `l_11` for eight seeds and within 2.3 % on `l_22` for all ten; seeds 6 and 7
  misread `l_11` by 35 and 40 % (#177).
- **Cost.** A 48 × 48 stability sweep takes 3.7 s (2.7 s on 0.4.0) and 26 s with charge dynamics on
  (unchanged). Phantom #64, a dot that must lose two or more electrons at once keeping one too many with
  dynamics on, is still open.

## Decision
Pin Phantom `v0.6.0` and recompile both devices from their unchanged recipes. Keep ADR 0090's starting
point. Make `qdt_sim.scenarios.lattice_truth` the slope of Phantom's gate-induced charge at the start, by
a central difference of 0.1 mV on each lattice gate, until Phantom's truth carries it (Phantom #75). A
virtual gate's coupled companion moves from the level the stand holds it at: the stand server's merge of
the held point into a sweep keeps the held level for a companion, and a companion that nothing holds
takes the live setpoint of the server's standing instrument (ADR 0057), merged into the sweep's `levels`
before it compiles so the record carries the origin; `run_node` and `run_tuneup` take the operating
point to inherit, which the tune-up tests set to the stand's starting point. Restore the noisy virtual-lattice scenario, and set every bound to what the
measurements need.

## Consequences
- **Easier:** the first stability diagram on a fresh stand is a honeycomb of two separate dots across the
  window, and opening `B_M` in **Levels** merges it from the upper right down, over a quarter of a volt;
  closing it by 0.06 V separates the dots everywhere. The guide's `B_M` section says how, and its
  troubleshooting rows explain the merged corner and the uneven cells. This closes #175's guide part; the
  simulated stand still accepts any voltage, as it has no limits of its own.
- **Easier:** the virtual-lattice node measures the window it claims to, on the server and in the tests,
  and its residuals fall from 0.049 to 0.005. The noisy virtual-lattice fixture is back.
- **Easier:** the tune-up bounds that 0.4.0's merged corner had widened come back in: the straightening
  test's bound goes from 0.015 to 0.01 (0.0046), the tutorial's ratio bound from 0.06 to 0.03 (0.005).
- **Harder:** `qdt_sim` computes one number, the slope of Phantom's charge, against its rule of renaming
  only. The function says why and names Phantom #75, which would let it go back to a rename. The source
  grows from 337 to 347 lines, and the cap in `test_device.py` from 340 to 350.
- **Harder:** the diagonal bounds widen where the uneven honeycomb needs it: the tune-up's `l_22` from
  1.5 % to 5 % (−3.6 %), the analysis test's dot 2 from 2 % to 3 % (seed 2 at −2.25 %). `l_11` keeps its 6 %
  (−4.0 % on device b in the virtual gates). Each bound quotes the value that needed it.
- **Harder:** ADR 0049 rejected moving a companion "from where it was" because a definition would then
  depend on the device's state. The origin now comes from the server's state, held or live, but it is
  written into the definition before it compiles, as the held point already was (ADR 0053), so the
  record is explicit and reproducible; the template is not, which was already true of every held level.
  On the server the held point holds only what a person or a node set, so without the live setpoint the
  API tune-up's virtual lattice still read a residual of 0.050.
- **Harder:** a companion's origin is that level, and ADR 0049's rule that the companion follows the
  axis value, not its offset, still holds. So a virtual sweep's companion sits at `held + c × value`: in
  the virtual-lattice node `P2`'s DC line runs about 40 mV below the first node's, one electron on dot 2.
  Changing the rule to `held + c × (value − held)` would change what every virtual sweep means and is
  left for a decision of its own.
- **Must now:** `run_tuneup` and `run_node` callers that want a sweep to inherit an operating point pass
  it as `held`; the server's `TuneUpManager` already runs through the `RunManager`, which merges its own.
- **Must now:** the guide's dynamics row keeps the Phantom #64 warning.

## Alternatives considered
- **Keep Phantom's truth and multiply it by 3/2** — rejected: a hand-written expectation, and wrong away
  from the operating point, where the factor runs from 1.38 to 1.61.
- **Wait for Phantom to fix its truth before adopting 0.6.0** — rejected: it would hold the human's request
  on an issue filed the same evening; the slope is Phantom's own quantity at Phantom's own point.
- **Take the window's mean slope as the truth** — rejected: more computation in `qdt_sim` for a number
  within 0.1 % of the slope at the start; the uneven honeycomb is the analysis's business (#101, #102).
- **Fix the companion in the executor, moving it from the channel's current level** — rejected: ADR 0049
  rejected that for reproducibility; the held operating point is recorded state (ADR 0053), so it is the
  explicit origin.
- **Keep the noisy virtual-lattice scenario out** — rejected: 8 of 10 seeds are accepted now, seed 1 among
  them, so the chain can be pinned end to end again.
- **Drop the analysis test's bad seeds silently** — rejected: the test keeps seeds 1 and 2 as before, and
  #177 records seeds 6 and 7.
