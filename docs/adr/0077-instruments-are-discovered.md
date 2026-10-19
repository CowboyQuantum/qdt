# 0077 — Instruments are discovered, not declared: an inventory of what is reachable, bindings saved as stand versions, an instrument pool where one offline instrument takes down only its own ports

**Status:** Proposed
**Date:** 2026-10-19
**Step:** 6c (issues #75, #80; plan §12 #12 for ports)

## Context
Issue #75: `qdt-server --stand` builds every instrument in the stand file on each request and closes them
again; one instrument that does not answer makes every request fail, and the rebuild churns the others'
connections. Seen twice on 2026-10-19 (an instrument powered off; a wedged socket). Issue #80: on the lab
network instruments need stable identities, and addresses drift. The human's proposal (2026-10-19):
instruments are not declared in a stand file; a discovery step samples the network and lists what is
connected, with each instrument's source and sense ports; ports are named live in Flight Deck as well as
in a hardware configuration file or script. Workflow: open Flight Deck, press a button that samples the
instrument landscape and pre-initialises ports.

The constraint that shapes the design: a record must say which physical port its logical channel was.
What is reachable changes minute to minute; what a run used must not.

## Decision
**Inventory and binding are separate.**
- The **inventory** is what is reachable now: per instrument, the matched driver, model, identity
  (vendor's model and serial as reported), transport, address, status (`online|offline|unknown`) and its
  ports (name, direction `source|sense`, quantity). It is live state in the stand server, never committed
  and never in a record.
- The **binding** is the logical channel → (instrument identity, port) map: today's `ChannelMap`s. Saving a
  binding — from the Instruments widget or by importing a configuration file — writes a new **stand
  version** to the registry, like `StandState` (ADR 0075): who, when, why. Records keep referring to the
  stand configuration they ran under, so provenance is unchanged. A configuration file is an export/import
  of the same object, so a script and the UI write the same thing.
- Binding is by **identity, not address**: discovery resolves where an identity is today, so an address
  that drifts does not break a stand (#80). DHCP reservations and DNS names remain good practice; they are
  no longer required for correctness.

**Discovery** (`qdt_lab.discovery`): per-transport discoverers return candidates; each candidate is
identified (`*IDN?` for SCPI) and matched to a driver factory.
- VISA enumeration for USB, serial and GPIB.
- LAN: mDNS for LXI (`_lxi._tcp`, `_scpi-raw._tcp`), then an opt-in probe of a **configured, bounded** address
  range on the SCPI and VISA ports. Never the whole network; the range is a stand-server setting.
- Vendor discoverers where SCPI does not apply (the OPX: configured hosts probed on its API port).
**Discovery never changes an output.** Pre-initialising a port means connect and read its state, nothing
more; a driver's discovery path is tested not to write.

**Drivers declare their ports** (name, direction, quantity, range). This is the port half of plan §12 #12's
capability declaration; the rest of #12 stays parked.

**An instrument pool in the stand server** replaces per-request rebuilds (#75). Each instrument has its own
connection, health check and reconnect with back-off. An offline instrument marks its ports unavailable;
a level or a compiled sweep that uses one is refused with the reason; every other instrument keeps
working. Polls read the pool's cached state and never rebuild a backend.

**API and Flight Deck.** `POST /instruments/discover` (a command: needs ADR 0074's token off loopback),
`GET /instruments` (inventory), `GET/PUT /stand` (binding; `PUT` saves a version). An **Instruments widget**
lists instruments with status and ports, and binds or renames ports; the workflow is Discover → review →
Save stand. Simulated instruments appear in the inventory like real ones.

**Schema**, added to Step 6c's slice (`operations.py`): `InstrumentPort`, `InventoryEntry`, and a version
envelope for `StandConfig` (`StandVersion`: stand, version, set_by, set_at, reason).

## Consequences
- Easier: one instrument off takes down only its ports; a stand is set up from the UI; addresses can drift;
  the stand file becomes optional and exportable.
- Harder: per-transport discoverers and per-driver port declarations; a pool with reconnect logic; a LAN probe
  that IT must know about (the IT ask names the instrument range and that probing is opt-in).
- Must now: L0 tests on emulators (ADR 0041) for discovery, identity matching, port declarations, the
  no-write rule, pool isolation (a factory that raises leaves the others usable; polls do not rebuild),
  compile refusal on an offline port, and binding round-trips (UI ↔ file ↔ registry version); an L1 bench row.

## Alternatives considered
- Keep declared stand files and make the build tolerant — fixes #75's symptom, not #80, and keeps setup
  out of the UI.
- Discovery that writes bindings automatically — rejected: a binding is a provenance fact; a person saves it.
- Scan the whole network — rejected: IT exposure and time; a configured range or mDNS is enough.
