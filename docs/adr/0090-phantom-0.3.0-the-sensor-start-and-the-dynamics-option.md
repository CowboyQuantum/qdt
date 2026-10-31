# 0090 — Adopt Phantom 0.3.0: a committed starting sensor level, the lattice read from a peak's tail, and a `dynamics` run option

**Status:** Accepted
**Date:** 2026-10-31
**Step:** 6c (the human's request, issue #169; not a step deliverable)

## Context
On 2026-10-30 the human asked for "better charge dynamics to be simulated for the charge sensor as well as
gates to modulate those dynamics, meaning the tunnel barriers into the charge sensor dot, as well as the
baths that the sensor dot couples to." Phantom built that and released it as `v0.3.0` (`6920f19`) on
2026-10-31, closing Phantom #47, #53 and #54. The human then asked for the changes needed to test it in
Flight Deck. ADR 0087 says a pin moves in a pull request of its own that regenerates the fixtures.

Phantom 0.3.0 changes the device a great deal for qdt:
- **Four more gates.** The layout gains the sensor barriers `SB_L` and `SB_R` and the sensor bath gates
  `SR_L` and `SR_R`, so a device has twelve gates and every programmed point needs them. Phantom's gallery
  sets `SB_L` 0.4 V, `SB_R` 0.3 V and both baths 0.7 V for seed 2.
- **The sensor is a dot with leads.** Its peaks are about 35 mV apart on `SG`, against about 1 V on 0.2.0,
  and its charging energy is about 9 meV, against 1 meV. Its tunnel rates follow its barrier gates and the
  sensor gate itself, so the sensor turns on steeply as `SG` rises. Near Phantom's set point the rates are
  about 10¹¹ Hz, and the peak a period higher is broadened by tunnelling to a lifetime width of about
  5 mV, while the thermal width is 0.1 mV.
- **The programmed sensor gate sits between peaks.** At the programmed 0.6 V the sensor reads about
  10⁻¹⁷ A. Phantom's compiler places a set point on a peak's flank in the device's carried voltages, but
  the set point is not in `Knowable`. Recompiling with `SG` at the set point moves the set point another
  10 to 24 mV up, because the compiled peaks follow the compile point (Phantom #65). So no recipe makes
  the programmed point the set point.
- **One electron moves the sensor by more than a peak's width.** Each dot electron kicks the sensor by
  about 1.4 mV in `SG` terms, and the plungers pull it by about ±2 mV across a lattice window. On the sharp
  peak at Phantom's set point, a stability diagram shows current only along one diagonal stripe, and the
  lattice comes out at 7 electrons per volt against a truth of 20. On the wing of a broadened peak the
  window carries the sensor over its top, and the lattice's cross ratios come out about 40 % high. On that
  peak's tail, 8 to 11 mV below the wing, the sensor stays on one slope and the lattice comes back within
  about 1 %.
- **Seed 5 forms a dead sensor at the gallery's point.** Its source barrier is fully open and its drain
  nearly closed (Phantom #49 reports the same on other seeds). With `SB_L` 0.375 V and `SB_R` 0.425 V it
  forms a sensor as good as seed 2's.
- **The noise moves the sensor visibly.** Phantom's gate 1/f noise now shows on the sharper sensor
  (Phantom #50 says its amplitude is about ten times typical). The noisy lattice estimates scatter by
  about 1 % on the diagonal and about 0.01 to 0.02 on the cross ratios, from seed to seed.
- **Charge dynamics are now worth having.** With 0.3.0 the dots' rates follow the barrier gates, and the
  sensor's own charge evolves in time. A 48 × 48 sweep costs about 3 s with dynamics on, against 0.3 s off.
  But a dot that must lose two or more electrons at once keeps one too many with dynamics on (Phantom #64).

## Decision
Pin Phantom `v0.3.0`. Recompile both devices with the four new gates, keeping seed 2 at Phantom's
reference point and giving seed 5 its own sensor barriers. Have a fresh simulated stand hold each gate at
its programmed level except `SG`. `SG` starts at a committed level per device, `SENSOR_SET_V`, which sits
`SENSOR_TAIL_V` (−10 mV) from the wing of the first broadened peak a period above Phantom's set point. The
charge-lattice and virtual-lattice nodes read the sensor at that same offset from the wing the sensor-wing
node finds. Add a run option `dynamics`, off by default, that turns Phantom's charge dynamics on.

## Consequences
- **Easier:** a fresh simulated stand reads a stability diagram at once, as it did on 0.2.0. Flight Deck's
  Device widget draws the twelve gates with no code change. The Sweep and Tune-up widgets' default options
  show `"dynamics": false`, so a person can find the option and turn it on.
- **Easier:** the tune-up chain, all four nodes, is accepted on both devices. The quiet scenarios recover
  the lattice within 0.8 % on the diagonal and within 0.003 on the virtual-gate terms.
- **Harder:** `SENSOR_SET_V` is a number derived from Phantom's truth (`optimum(device).sensor` and the
  next peak's `SensorTruth.wing_v`). `scripts/make_sim_devices.py` prints it for every device and `--check`
  fails when it drifts, so a pin change recomputes it like the hashes. It is never served: the server
  serves levels, never truth.
- **Harder:** the noisy tune-up bounds widen. The lattice diagonal is held to 1.5 % rather than 1 %, the
  cross terms to 0.3 e/V rather than 0.2, and the virtual-gate and compensation terms to 0.015 rather than
  0.01. The analysis test's cross ratios are held to 0.025 rather than 0.02. Each widened bound quotes the
  value that needed it, and the quiet scenarios stay inside the old bounds.
- **Harder:** after a tune-up the server holds `SG` at the wing, because the sensor-wing node `holds` it
  there, while the lattice nodes read 10 mV lower. A person who sweeps a stability diagram after a tune-up
  sets `SG` lower first, and the guide says so.
- **Harder:** with `dynamics` on, a stability diagram on Phantom 0.3.0 is wrong over much of the map,
  because each row starts with a downward step of several electrons (Phantom #64). The option stays off by
  default, and the guide says to try it on short windows and parked readings until a Phantom release
  fixes it.
- **Must now:** the sensor node takes a bias window, `bias_v`, which the simulated stand sets to ±12 mV so
  the diamonds reach their tips. The sensor-wing node's span is 4 mV with 201 points. The lattice nodes take
  `sensor_offset_v`, applied to the binding from the sensor-wing node (`qdt_tuning.nodes.held_sensor`). A
  stand without a sensor gate binds nothing, as before.
- **Must now:** a test that compares a fitted peak width with Phantom's truth uses the width of the sech²
  with the broadened peak's wing, `(wing_v − peak_v) / WING_WIDTHS`, which is how Phantom places its set
  point. `SensorTruth.width_v` is the thermal width alone.
- **Must now:** the `qdt-sim` source cap rises from 320 to 340 lines (337 used), for `start`, the two new
  constants and the `dynamics` and `levels` arguments.

## Alternatives considered
- **Program the set point in the recipe** — rejected because Phantom's compiler moves the set point again
  wherever `SG` is programmed (Phantom #65), and the sensor weakens with each recompile.
- **Start at the programmed point and let the tune-up find the sensor** — rejected because a fresh stand's
  stability diagram, the guide's first step, would read nothing, and the human asked for a stand to test
  in Flight Deck.
- **Start at Phantom's set point, the steepest point of the sharp peak** — rejected because one electron
  takes the sensor off that peak, and the lattice comes out 60 % wrong.
- **Read the lattice at the broadened peak's wing, where the sensor-wing node parks** — rejected because
  the window carries the sensor over the peak's top, and the cross ratios come out about 40 % high.
- **A tail of −8 mV or −11 mV** — −8 mV was best for the noisy default but left device b's quiet virtual
  lattice 1.5 % off, and −11 mV left a noisy seed with no overlaid segments. −10 mV keeps both quiet chains
  exact.
- **Change seed 5 for another seed** — rejected because every other seed but 2 also needs its own sensor
  barriers at the gallery's point, and keeping the seed keeps device b the same disorder draw.
- **Keep the sensor tolerances of 0.2.0** — rejected because they were sized for a 0.16 V peak and a 1 V
  period, a hundred times the new ones.
