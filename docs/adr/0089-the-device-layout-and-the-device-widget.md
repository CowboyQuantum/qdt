# 0089 — The device's gate layout is a schema object the stand server serves and Flight Deck's Device widget draws to scale

**Status:** Accepted
**Date:** 2026-10-29
**Step:** 6c (the human's request, issue #164; not a step deliverable)

## Context
On 2026-10-29 the human asked for "a widget that draws an approximate (but to scale) diagram of the device
that has the voltages on the gates (maybe with a color map)".

Nothing in the repository described a device's geometry. The stand configuration (`StandConfig`) names
channels, and the Levels widget lists them as a table, so a person had to know from elsewhere which gate
sits where.

Phantom `v0.2.0`, the simulator behind the simulated stand (ADR 0087, 0088), already carries the geometry.
Its `Device.knowable()` is the part of a device that a user may be shown. It includes the layout: every
gate as a polygon in nanometres with a role, the conducting channel's rectangle, the sensor's rectangle,
the material, and the layer stack. The default device's eight gates span about 640 nm by 330 nm.

Four constraints shaped the design:
- **Rule 3 and ADR 0034.** Every body the server returns is a schema object, and Flight Deck's client is
  generated from the OpenAPI document. A layout therefore needs a schema type in `qdt-schemas`.
- **ADR 0028 froze the identity family.** A new identity type needs an ADR that defines it.
- **ADR 0079 keeps domain words out of the general layer.** The schema cannot name gate roles in its
  descriptions, so the role is free text that the layout supplies.
- **Rule 7 keeps site geometry out of the repository.** A real device's layout is site-specific, so the
  repository can ship only the simulated device's.

`qdt-sim` must stay a thin adapter, and a test caps its source at 300 lines (Phantom's Step 8 exit, ADR
0087). The code was at 295 lines, and the rename takes 16.

## Decision
Add `GateOutline` and `DeviceLayout` to `qdt_schemas.identity`, built by `qdt_sim.scenarios.layout`
as a pure rename of Phantom's knowable layout. Serve the layout at `GET /device/layout` on the stand
server (404 when the stand has none, which is every real stand for now), and draw it in a new Flight Deck
widget, "Device", coloured by `GET /levels/state`.

The details:
- **`GateOutline`** carries the gate's name, a free-text role, the stand's logical channel that sets it
  (null when none), and its outline in nanometres.
- **`DeviceLayout`** carries the device id, the material, the gates, optional rectangles for the channel
  and the sensor, and a `source` line that says where the layout came from. It is served and never
  stored, so it is not in `migrations.PERSISTED` and has no fixture or migration.
- **Coordinates are sized `tuple[float, ...]`**, not fixed tuples. The TypeScript generator turns a
  fixed tuple's `prefixItems` into `unknown` but keeps the element type of a sized one.
- **The server's `Settings.layout`** defaults to the simulated device's layout. `python -m qdt_server
  --stand` sets it to None.
- **The widget colours** each gate at its sitting level, which is the held level, else the setpoint
  (`sittingLevels`, as the Sweep form uses since #157). The colour range spans the lowest to the highest
  gate, and the colormap is a per-pane setting like the plot's (ADR 0061). Labels are sized in screen
  pixels and written inside a gate only where they fit. A legend always lists every gate's level. The
  widget reads; it never sets a level.
- **The `qdt-sim` source cap rises from 300 lines to 320.** The adapter computes nothing, so the cap's
  purpose, an adapter and not a model, still holds.

## Consequences
- Easier: a person sees where each gate is and what it sits at, at a glance, beside the Levels table.
- Easier: a real stand can get a diagram later without a schema change, by giving the server a layout
  file. The file would hold site geometry, so it stays out of the repository (rule 7).
- Harder: the stand server now holds one more piece of per-stand configuration, which the setup page in
  #165 will have to choose along with the stand.
- Harder: `qdt-sim` has less room under its cap for the next adapter function.
- Must now: a layout's gate channels must name the stand's logical channels, or the widget shows those
  gates unfilled.

## Alternatives considered
- Serve Phantom's layout dictionary as it is — rejected because the server would then pass along a shape
  that Phantom owns, and rule 3 requires a schema object.
- Put the layout on `DeviceRecord` — rejected because the record is stored and synced with every device,
  and a body change under an existing device id is a registry conflict (append-only).
- Compute the layout in `qdt-server` — rejected because the server never imports Phantom (ADR 0088).
- Shorten existing `qdt-sim` code to stay under 300 lines — rejected because squeezing working code to
  meet a line count hides the cost. Raising the cap says it openly.
- Draw on a WebGL canvas like the plot — rejected because a few polygons need no GPU, and SVG gives
  tooltips and scales crisply.
