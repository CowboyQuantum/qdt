# 0043 — The QDAC-II is also reachable over its USB serial port; the transport takes a baud rate

**Status:** Accepted
**Date:** 2026-10-14
**Step:** 5

## Context
ADR 0041 put the QDAC-II on Ethernet. On the bench the instrument could not be found: it ships DHCP-only,
the bench wire has no DHCP server, its firmware has no link-local fallback (a sweep of all of 169.254/16
found nothing), and it was holding a stale lease from an earlier network. The manual's own answer is the
rear USB port: a virtual serial port at 921600 baud, meant for first-time setup and firmware updates, over
which the LAN address is set. With the USB cable in and the Ethernet cable moved elsewhere, the only link
to the instrument today was serial.

pyvisa-py already opens serial resources (`ASRL<device>::INSTR`) when pyserial is installed; it defaults
to 9600 baud, which the QDAC-II does not speak.

## Decision
- **`open_visa` takes `baud_rate`** and applies it when the resource has one (serial). TCP and other
  resources ignore it. The transport protocol is unchanged.
- **`QDac2.from_config` defaults the baud rate to 921600** (`USB_BAUD_RATE`), the port's fixed speed;
  `settings["baud_rate"]` overrides. A serial address in a stand file or in `QDT_QDAC2_ADDRESS` therefore
  just works: `ASRL/dev/cu.usbserial-NNNN::INSTR`.
- **`pyserial` joins the `[qdac]` extra.** It is what pyvisa-py needs for `ASRL`; it is not a core dep.
- **Ethernet stays the bench transport** for sweeps (the manual recommends it, and warns that large
  reads over USB with the pyvisa-py backend can garble). USB serial is for setup, and for proving the
  driver when the wire is not there.

## Consequences
- The QDAC-II's three LevelSource conformance tests pass on hardware over USB (bench report
  2026-10-14). Its LAN now holds a fixed address set over USB, stored in non-volatile memory, to be
  confirmed on Ethernet when the cable returns.
- The procedure for giving the instrument an address is in `docs/BENCH.md`. The set commands take the
  value bare or quoted (`syst:comm:lan:ipad "10.0.0.2"`); readback shows the new value only after
  `:upd` and a restart, so a query right after the set still reports the old address. Whether `SYSTem:REStart` alone brings the LAN up with a fixed address is unknown: the
  instrument was not seen on the wire after it, and was then power-cycled with no cable in.
- `uv.lock` changes (pyserial). The emulator is untouched: it never had a link.
