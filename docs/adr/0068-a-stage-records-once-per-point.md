# 0068 — A stage records once per stepped point without an axis of its own: a one-point program axis, `once`, that the executor strips

**Status:** Accepted
**Date:** 2026-10-16
**Step:** 6 follow-up (extends 0018, 0019, 0066, 0067)

## Context
A stage result is laid over the program's axes: the stage axes (ADR 0018, 0019) and, since ADR 0064, a
triggered axis, plus the shots when they are kept. A stage with no axis of its own and one shot, or with
its shots averaged, has none, and the emitter refused it ("a stage with no axes needs shots > 1 kept").
The deeper cause is the frozen Dataset contract (ADR 0015, 0031): every Dataset, data variable and chunk
has at least one dimension, so the slab the sequencer fills cannot be a scalar.

ADR 0066 made this depend on the stand. Triggered, the program owns the stepped axis and the result has
it; stepped from the host, it has none. So a definition that compiled on a wired stand failed on an
unwired one, and the compiler could only explain why. ADR 0067's DC sweep read in the shot needed its inner
axis triggered for the same reason, and the Sweep widget withheld "software" for it. The human asked for
this slice after the readout choices (2026-10-16).

## Decision
When a stage has no axis of its own and a result would have none, give the program a one-point axis,
`once` (`n_once` = 1), and the sequencer's slab a one-point dimension of that name; the executor strips it
when it lays the value at the stepped point. Refuse only a value with no axis anywhere: no stepped axis, no
stage axis, no kept shots and no repeats.

## Consequences
- Easier: one definition compiles on any stand, triggered or stepped from the host, which completes ADR
  0066's portability. A DC sweep read in the shot (ADR 0067) runs on an unwired stand, one measure per
  point, and the Sweep widget offers "software" for it again.
- Easier: nothing outside the program and the slab changes. The plan's Dataset, the stream, the registry
  and Flight Deck never see `once`, so the frozen contract stands.
- Easier: every sequencer already handles it. On the OPX it is a loop of one iteration; on the simulated
  device and the simulated sequencer it is a one-point shape.
- Harder: stepped from the host, each point is a program run, one OPX job per point (the cost ADR 0066
  described); triggered stays the fast way.
- Harder: `once` is a reserved program axis name. `n_once` appears only when the program has no other axis,
  so it never meets a stage axis or a triggered axis of that name.
- Must now: compile refuses a value with no axis anywhere ("one number with no axis"); repeat the sweep or
  give it an axis.

## Alternatives considered
- Relax the Dataset contract to allow scalar variables and chunks — rejected: it reopens a frozen contract
  for a corner case, and every consumer would need a 0-D path.
- Use the innermost stepped axis as the slab's dimension, with size 1 — rejected: the executor's prefix
  already carries that axis, so the frame would name it twice and the re-keying would rewrite indices
  instead of dropping one.
- Keep refusing and tell the user to keep shots > 1 — rejected: it forces a shot dimension nobody asked
  for, and leaves a definition's validity depending on the stand.
