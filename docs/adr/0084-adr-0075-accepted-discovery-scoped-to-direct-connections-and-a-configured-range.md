# 0084 — ADR 0075 accepted as written; discovery (ADR 0077) begins with directly connected instruments and a configured, empty-by-default address range for the network

**Status:** Accepted
**Date:** 2026-10-25
**Step:** 6c (goal 2; closes the step's open decision on ADR 0075; narrows ADR 0077's discovery scope ahead of its acceptance)

## Context
Step 6c gates deliverables 7 and 8 on accepting or amending ADR 0075 (limits, couplings and the held
operating point as versioned stand state on the server; the run queue in the stand server), and
deliverables 9 and 10 on ADR 0077 (instruments discovered, bound by identity, held in a pool). On
2026-10-25 the human gave two directions.

On ADR 0075: "I think it makes sense for the voltage limits and the voltage state of the instruments to
belong to the stand and NOT have that belong to the front end", and, after the ADR's remaining details
were laid out (refuse and never clamp; re-apply the held point after a restart only on a person's
confirmation; the run queue moves into the stand server in the same ADR; a new table set and migration),
"accept 0075".

On ADR 0077: the instruments that matter for discovery hang off a rack switch that has an optical uplink
to the laboratory network, and the measurement computer is hard-wired into that switch. Whether the rack
is its own address range or shares the laboratory's subnet through an untagged uplink is not yet known
(issue #80). The human's direction: "for now with the instrument discovery, let's just design so that we
can discover anything connected to the computer directly and then allow an ip range for future
specification when I understand how we can isolate the rack ips to a vlan or range".

## Decision
1. **ADR 0075 is accepted as written.** `operations.py` gains `ChannelLimit`, `StandState` and
   `QueuedRun`; `StandState` versions are registry records that the stand server writes and the read
   server reads; the stand server enforces the latest version's limits on every level and every compiled
   sweep, refusing and never clamping; the held operating point is re-applied after a restart only when
   a person confirms it in Flight Deck; the run queue lives in the stand server, persisted in its cache,
   ordered, one run at a time, with reorder and remove while queued and abort while running. Flight
   Deck's Levels, Virtual gates and queue widgets become views of the server's state and change it
   through commands, which need the command token off loopback (ADR 0082).
2. **Discovery starts with what is connected directly to the measurement computer**: enumeration through
   the Virtual Instrument Software Architecture (VISA) library of USB, GPIB and serial instruments, and
   the vendor discoverers for instruments that are configured by host (the OPX's configured hosts on its
   API port). **The network probe exists as a setting and is off until the human fills it in**: the stand
   server takes a configured address range (`discovery.probe_range`, empty by default); with no range,
   no address on the network is probed and no multicast query is sent. When the rack's isolation is
   understood — its own range behind the computer's rack-facing interface, or a Virtual Local Area
   Network (VLAN) from the IT department — the range is specified and the probe is bounded by it. The
   rest of ADR 0077 (inventory separate from binding, binding by identity, drivers declare ports, the
   instrument pool, the Instruments widget) is unchanged by this ADR and still awaits acceptance.

## Consequences
- Easier: deliverables 7 and 8 can start without further decisions; the first version of discovery needs
  no network knowledge and cannot touch anything beyond the computer's own ports; plan §9 row 9 (the
  probe question to IT) becomes informational until a range is wanted.
- Harder: on the bench today the scope, the QDAC and the SMU are reached over the network on link-local
  addresses, so until a range is configured they are declared, not discovered; the configured-hosts path
  (as for the OPX) is how a network instrument enters the inventory in the meantime. Multicast Domain
  Name System (mDNS) discovery, which ADR 0077 lists for LAN eXtensions for Instrumentation (LXI)
  instruments, is deferred with the probe: it is per interface and could be enabled with the range.
- Must now: issues #78 and #79 close when deliverables 7 and 8 land with their L0 rows; ADR 0077's
  acceptance ADR carries the probe-range setting and, if the rack turns out to be isolated behind one
  interface, discovery per interface with the range derived from the interface and capped (issue #80).

## Alternatives considered
- Amend ADR 0075 to keep the queue in the browser and move only limits and the held point — not chosen:
  the human accepted the ADR as written after the queue half was pointed out; goal 2's unattended task
  list needs the queue where the stand is.
- Probe the laboratory subnet now with mDNS only — rejected for now: the rack's relation to the
  laboratory network is unknown, and the human asked that nothing on the network be searched until a
  range is understood.
- Scope the probe to a network interface rather than a range — kept open: it is the likely shape once the
  rack is known to be behind one interface (issue #80); a range setting is the minimum that lets a
  future interface-derived range plug in without changing the stand file's shape.
