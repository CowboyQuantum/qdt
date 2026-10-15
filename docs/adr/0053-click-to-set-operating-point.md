# 0053 — Click-to-set: the server holds the stand's operating point (`/levels`), every sweep inherits it, and Flight Deck's map click is the one "up" edge

**Status:** Accepted
**Date:** 2026-10-15
**Step:** 6 (a listed deliverable; extends ADR 0038; resolves the pending "default operating point per device")

## Context
`docs/FINISH_LINE.md` lists gate-voltage navigation / click-to-set as the one place the view emits
something upward: a set-parameter request. Step 6's deliverables name it. Everything else in the stack
flows down: definitions in, Datasets out. ADR 0038 made a sweep carry its operating point (`levels`, set
once and held), which left two things open: where the operating point lives *between* sweeps, and how a
person moves it from the map they are looking at. STATUS carried "a default operating point per device"
as a pending decision since ADR 0038.

Two facts shape the design. The simulated stand builds a fresh device per run, so "setting a level" on
it has no memory unless the server remembers; and a Dataset's coordinates are the sweep's *axis names*,
not channels (rule 8: the view knows no channels or instruments), so a click yields names and values
and someone else must say which are gates.

## Decision
- **The server holds the stand's operating point.** `RunManager` keeps `levels: {channel: value}`;
  `set_levels` validates each channel (on the stand, on a `LevelSource`), applies it on the backends now
  (on a real stand the DC lines move; on the simulated stand the throwaway device is set and forgotten)
  and holds it; `clear_levels` forgets. Every sweep the server compiles or runs is first merged with the
  held levels for every channel the sweep does not touch itself (axes, couplings, sensed, captured, its
  own `levels`), so the plan and the record carry the operating point they ran at (durable through ADR
  0038's `levels`). A tune-up's nodes inherit it the same way, since they run through the `RunManager`.
- **API:** `GET /levels` (the held operating point), `POST /levels` (a list of `FixedLevel`: set and hold,
  merged over the current ones; 400 for an unknown channel or one that is not a `LevelSource`),
  `DELETE /levels` (release; the stand stays where it is). Bodies are schema objects (ADR 0034).
- **Flight Deck:** a click on the heatmap gives the point under it in the two coordinates
  (`view.pointAt`, the inverse of `annotationPath` for one point: names, units, values, nothing else).
  The control panel turns it into a setpoint (`setpointFor`): coordinates whose names are DC channels of
  the stand become levels, the rest are shown as not settable; a button posts them; the held operating
  point is shown with a release button. A pulsed axis named after its gate (`P2` on `P2_pulse`) sets the
  gate's DC line `P2`, which is what moving the operating point there means.

## Consequences
- Easier: gate-voltage navigation exists end to end on the simulator: click, set, and the next sweep's
  plan shows the levels. The stand's state is explicit and queryable, and a record says where every gate
  not swept was held. The pending default-operating-point decision is closed: the server is where it lives.
- Easier: a tune-up can start from a human's click (set the gates, run the nodes), and a node that sets
  its own operating point (`charge-lattice` holding `SG`, ADR 0052) overrides the held value for that
  channel only.
- Harder: the held operating point is server memory, like runs and tune-ups; a restart forgets it, and
  the stand keeps whatever it was at. Records carry it, so history is not lost; a `GET /levels` after a
  restart is empty until someone sets or runs.
- Harder: the click resolves to the *cell* under the pointer, not an interpolated value; and only axis
  names that are stand channels are settable, by convention (`stability_diagram` names its axes `P1`,
  `P2` for that reason). An axis named `V_sd` on channel `bias` is not settable until the panel learns the
  record's definition (axis → channel), a later refinement.
- Must now: a stand file names a gate's DC channel after the gate (`P2`) and its pulse line `P2_pulse`,
  as the simulated and bench stands already do.

## Alternatives considered
- A one-point sweep as the set request (compile and run a sweep with `num=1`) — rejected: it would
  record a measurement nobody asked for, and the simulated stand would still forget the level.
- Levels on the device record (persist the operating point in the registry) — rejected for now: it is
  state, and the registry is append-only; the records already carry it per sweep, which is the durable
  fact. A `stand_state` table is a later additive change if something needs the latest state offline.
- The view resolving axis names to channels itself — rejected: rule 8; the panel knows the stand.
- Interpolating the clicked value between cells — rejected: a set point should be a value the map was
  measured at; the cell's coordinate is that.
