# 0093 — A simulated sweep reads a line at a time: `BatchedLevelSense` beside the frozen protocols, `sense_many` on the simulated physics, and the sequence interpreter's batched lines

**Status:** Accepted
**Date:** 2026-11-01
**Step:** 6c (the human's request, issue #179; not a step deliverable)

## Context
On the simulated stand a 201 × 201 stability diagram took 69 s, 1.7 ms a point, which the human called
"painfully long" and asked to have addressed. A profile of the same definition put 98 % of the time
inside Phantom's `Session.sense`, which qdt called once per pixel: the hybridised charge states of the
constant-interaction window (17 small matrix solves a point) about 68 %, the geometry at the point
(shape grid, puddles, the interdot barrier) about 17 %, the three noise traces about 15 %, the sensor
3 %. qdt's executor, frames and assembly were 2 %.

Phantom's cost is per call, not per point: its `sense` takes an array of points on one clock. On the
same device and settings one point per call cost 1.5 ms a point, one row of 60 or 201 points per call
64 to 80 µs, the whole 201 × 201 map in one call 60 µs. A map read row by row is bit for bit the map
read in one call; read point by point it differs in the tenth digit, from the order of summation.

qdt read one point at a time in two places. A DC sweep's executor sets the inner axis's level and
calls `LevelSense.sense` per pixel. A staged sweep's simulated sequencer interpreter runs the pulse
sequence per pixel, calling the physics' `sense` at each measure and `hold` at each step. Both were
written for one point at a time because that is what hardware does; the simulator had been fast
enough on earlier Phantom releases.

Four constraints shaped the design. The five capability protocols are frozen (ADR 0021): a batched
read is added beside them, as `TriggeredLevelSource` was (ADR 0064), never edited in. The executor
serves hardware first: the batched path must be a fast path it takes only when it can, with the
point-by-point path unchanged otherwise. The physics owns the clock (ADR 0087): a batched read must
advance it by what the points would have taken. With charge dynamics on, the charge evolves through
every hold and dwell, so that path must stay sequential.

## Decision
- **`BatchedLevelSense(LevelSense)`**, a `runtime_checkable` protocol beside the frozen five:
  `sense_along(channel, points: Mapping[str, Sequence[float]]) -> np.ndarray` reads `channel` once at
  each of N points, setting every channel in `points` to its i-th value before the i-th reading and
  leaving each at its last. It is optional; a backend without it is sensed point by point.
- **The executor's fast path.** For a sweep with sensed levels and no stage or capture, whose innermost
  stepped axis, its coupled companions and every sensed channel resolve to one backend that is a
  `BatchedLevelSense`, the executor reads the inner axis in one `sense_along` call per row: the outer
  axes step as before, the companions' points are `held + coupling × value` as before (ADR 0049,
  0092), the settle every point would have had is slept once for the row, and the frame is the same
  one-row frame the point-by-point path emits. The setpoints end at the row's last point (ADR 0038).
- **`SimulatedPhysics.sense_many(levels, dwell_s, gap_s)`**, optional: one reading per entry, what
  `sense(entry, dwell_s, 1, gap_s)` of each in turn would read, with the clock advanced by the same
  total. `LinearPhysics` has it. `PhantomPhysics` has it from one Phantom call: the session reads the
  points in order, `dwell_s` of clock each, then the shots' overheads pass together in one hold. With
  charge dynamics on `PhantomPhysics` leaves it `None`.
- **The simulated instrument** is a `BatchedLevelSense` (`sense_along` builds each point's levels and
  calls the physics' `sense_many`, or its `sense` point by point when the physics has none). Its
  sequencer interpreter reads each line of a staged sweep in one batch when the physics has
  `sense_many`, nothing is captured (a record per pixel keeps its own clock) and every measure's dwell
  is the same at every pixel: each measure is one batched read over the line's pixels, each step's or
  ramp's hold is taken once for the line at the last pixel's levels, differences are taken per pixel,
  shots are replayed over the line, and a triggered axis's lists are played per pixel as before.
  Otherwise the line is read pixel by pixel, as before.

## Consequences
- **Easier:** the human's 201 × 201 DC stability diagram takes 3.0 s instead of 69 s. The guide's 96 × 96
  staged diagram takes 0.9 s instead of 15 s; a 48 × 48 one 0.2 s instead of 3.7 s. The tune-up's four
  nodes run in a few seconds, and the tune-up fixtures regenerate in 20 s instead of 73 s.
- **Easier:** with noise off, a batched map is the point-by-point map to 12 digits (5 × 10⁻¹³ relative),
  and the clock ends at the same time; the quiet fixtures did not move.
- **Harder:** with noise on, a batched sweep is a different realisation of the same seed. Phantom draws
  each sample's charge and noise in order, so one call for a line consumes the random stream and the
  noise clock differently from a call per point: the gate 1/f noise is evaluated at `dwell_s` per
  point within a line instead of at `dwell + overhead + step`, and the overheads pass at the line's
  end. The committed noisy fixtures (the 24 × 32 stability array, the noisy charge- and
  virtual-lattice tune-ups) were regenerated; every node is accepted and lands where it did (the
  noisy default's `l_11` 0.5 % low, `m_12` 0.005 off). The same seed still reproduces bit for bit on
  one platform, which the fixtures hold.
- **Harder:** the simulated instrument's batched line takes the holds once, at the last pixel's
  levels, rather than between pixels. With dynamics off the levels during a hold change nothing,
  and the clock advances by the same total; with dynamics on the path is sequential and unchanged.
- **Harder:** the executor has two paths for a DC sweep, and `_batched_inner` decides between them at
  the start of a run. A stand with the inner axis on one instrument and the sensor on another, or
  with a capture at every point, is read point by point, as every real stand today is.
- **Harder:** `qdt_sim`'s source grows from 347 to 360 lines; the cap in `test_device.py` rises from
  350 to 370.
- **Must now:** a `SimulatedPhysics` that wants the fast path implements `sense_many`; one whose clock
  must run point by point leaves it unset or `None`. The conformance suite does not yet check
  `sense_along` against `set` and `sense`; the unit tests on `LinearPhysics` and on Phantom do.

## Alternatives considered
- **A batched `sense` in the frozen `LevelSense`** — rejected: ADR 0021 froze it; a new protocol beside
  it costs real drivers nothing.
- **Batch the whole map in one call** — rejected: the stream shows a row at a time, and a row is
  already within a few percent of the whole map's cost per point (64 against 60 µs).
- **Keep the per-point clock inside a batched line by handing Phantom per-point time stamps** —
  rejected for now: Phantom's `sense` has one dwell per call; a per-point clock would be a Phantom
  change for a noise-realisation difference that nothing in qdt depends on.
- **A simulator-only fast path in the executor, keyed on the backend's class** — rejected: the executor
  must not know what a backend is (ADR 0016); a protocol says what it can do.
- **Leave the staged path per pixel and batch only DC sweeps** — rejected: the guide and the tune-up
  use staged sweeps, and the interpreter's loop over pixels was as costly as the executor's.
