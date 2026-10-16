"""QDevil QDAC-II driver: 24 DC voltage channels with per-channel current readout, over SCPI.

`QDac2` is a `LevelSource` on its voltage terminals, a `LevelSense` on its current-readout
terminals (ADR 0016), and a `TriggeredLevelSource` (ADR 0064): a channel loaded with a list of levels
advances one point per trigger on the input `settings["trigger_in"]` (`ext1`..`ext4`, a rear BNC the
stand wires from a sequencer's marker line; default `bus`, fired from the host by `*TRG`).

A `ChannelMap` declares which: a 'voltage' id is a source terminal, a 'current' id a readout
terminal, and one physical channel may appear under both (e.g. 'ch03' voltage and 'ch03_i' current). Undeclared ids are voltage for `set`/`get` and current for `sense`. The channel
number is the digits of the id, 1..24.

SCPI commands used (from the QDAC-II manual; confirm on the first bench run):

    *IDN?                       identity; must contain 'QDAC-II'
    sour{n}:dc:volt:mode fix    put channel n in fixed DC mode (sent once, before its first set)
    sour{n}:volt {v}            apply v volts to channel n
    sour{n}:volt?               read back channel n's setpoint (volts)
    sens{n}:aper {s}            current-sensor aperture in seconds (sent once, if declared)
    read? (@{n})                measure channel n's current (amperes)

List mode (`load`; confirmed on the bench by Probe 05, 2026-10-16, firmware 14-1.70):

    sour{n}:dc:volt:mode list   the channel's DC generator plays a list
    sour{n}:list:volt v1,v2,..  the points
    sour{n}:list:tmod step      stepped: one point per trigger (not dwell-timed)
    sour{n}:list:coun 1         one pass; a trigger after the last point starts the list again
    sour{n}:list:dir up         first point first
    sour{n}:dc:trig:sour {t}    the trigger input: ext1..ext4, or bus
    sour{n}:dc:init:cont on     arm, and re-arm after every trigger (`dc:init` alone arms for one
                                trigger: the first point played and nothing after it, Probe 05)
    *TRG                        the bus trigger (`advance`, when trigger_in is bus)
    sour{n}:volt?               in list mode reports the point last played (Probe 05)
    sour{n}:dc:init:cont off, sour{n}:dc:abor   leave the list (`release`), then mode fix and the
                                level the channel is at

The transport is `ScpiTransport`; pyvisa is imported lazily by `open_visa`, so this module imports
without the extra.
"""

from collections.abc import Sequence

from qdt_schemas.stand import ChannelMap, InstrumentConfig

from ..scpi import ScpiTransport, channel_number, open_visa

CHANNELS = (1, 24)
USB_BAUD_RATE = 921600  # the rear USB port's virtual serial speed (manual 4.3.2)
MAX_VOLTS = 10.0
TRIGGER_INPUTS = ("bus", "ext1", "ext2", "ext3", "ext4")
"""`settings["trigger_in"]`: the rear external trigger inputs, or the bus trigger fired by `*TRG`."""


class QDac2:
    """QDAC-II as `LevelSource` and `TriggeredLevelSource` (voltage terminals) and `LevelSense`
    (current readout)."""

    def __init__(
        self,
        transport: ScpiTransport,
        channels: tuple[ChannelMap, ...] = (),
        trigger_in: str = "bus",
    ) -> None:
        self._t = transport
        idn = transport.query("*IDN?")
        if "QDAC-II" not in idn:
            raise ValueError(f"not a QDAC-II: {', '.join(idn.split(',')[:2])!r}")
        if trigger_in not in TRIGGER_INPUTS:
            raise ValueError(f"trigger_in must be one of {TRIGGER_INPUTS}, not {trigger_in!r}")
        self._trigger = trigger_in
        self._quantity = {c.channel: c.quantity for c in channels}
        self._integration = {c.channel: c.integration_s for c in channels if c.integration_s}
        self._fixed: set[int] = set()
        self._aperture: dict[int, float] = {}
        self._lists: dict[int, tuple[float, ...]] = {}  # armed lists

    @classmethod
    def from_config(cls, instrument: InstrumentConfig, channels: tuple[ChannelMap, ...]) -> "QDac2":
        """`BackendFactory` (ADR 0021): opens `settings['address']` (a VISA resource string). A serial
        address (`ASRL...`, the rear USB port) runs at the instrument's fixed 921600 baud unless
        `settings['baud_rate']` says otherwise. `settings['trigger_in']` names the input a loaded
        list advances on (ADR 0064; default `bus`)."""
        address = instrument.settings.get("address")
        if not address:
            raise ValueError(f"instrument {instrument.id!r} has no settings['address']")
        baud = instrument.settings.get("baud_rate", USB_BAUD_RATE)
        trigger = str(instrument.settings.get("trigger_in", "bus")).lower()
        return cls(open_visa(str(address), baud_rate=int(baud)), channels, trigger_in=trigger)

    def _number(self, channel: str, quantity: str, default: str) -> int:
        declared = self._quantity.get(channel, default)
        if declared != quantity:
            raise ValueError(f"channel {channel!r} is a {declared} terminal, not {quantity}")
        return channel_number(channel, *CHANNELS)

    def set(self, channel: str, value: float) -> None:
        n = self._number(channel, "voltage", "voltage")
        if not abs(value) <= MAX_VOLTS:
            raise ValueError(f"{value} V on {channel!r} is outside +/-{MAX_VOLTS} V")
        if n in self._lists:
            self.release(channel)
        if n not in self._fixed:
            self._t.write(f"sour{n}:dc:volt:mode fix")
            self._fixed.add(n)
        self._t.write(f"sour{n}:volt {value:.9g}")

    def get(self, channel: str) -> float:
        n = self._number(channel, "voltage", "voltage")
        return float(self._t.query(f"sour{n}:volt?"))  # in list mode: the point last played

    # --- TriggeredLevelSource (ADR 0064) -----------------------------------------------------------

    def load(self, channel: str, values: Sequence[float]) -> None:
        n = self._number(channel, "voltage", "voltage")
        points = tuple(float(v) for v in values)
        if not points:
            raise ValueError("a list needs at least one point")
        if any(not abs(v) <= MAX_VOLTS for v in points):
            raise ValueError(f"a list point on {channel!r} is outside +/-{MAX_VOLTS} V")
        w = self._t.write
        if n in self._lists:
            w(f"sour{n}:dc:init:cont off")
            w(f"sour{n}:dc:abor")
        w(f"sour{n}:dc:volt:mode list")
        self._fixed.discard(n)
        w(f"sour{n}:list:volt {','.join(f'{v:.9g}' for v in points)}")
        w(f"sour{n}:list:tmod step")
        w(f"sour{n}:list:coun 1")
        w(f"sour{n}:list:dir up")
        w(f"sour{n}:dc:trig:sour {self._trigger}")
        w(f"sour{n}:dc:init:cont on")
        self._lists[n] = points

    def advance(self, channel: str) -> None:
        n = self._number(channel, "voltage", "voltage")
        if n not in self._lists:
            raise ValueError(f"channel {channel!r} has no list loaded")
        if self._trigger != "bus":
            raise ValueError(
                f"the list on {channel!r} advances on {self._trigger}, which the host cannot fire; "
                "the sequencer's marker line does"
            )
        self._t.write("*TRG")  # reaches every channel armed on bus

    def release(self, channel: str) -> None:
        n = self._number(channel, "voltage", "voltage")
        if n not in self._lists:
            return
        del self._lists[n]
        level = float(self._t.query(f"sour{n}:volt?"))  # the point the channel is at
        self._t.write(f"sour{n}:dc:init:cont off")
        self._t.write(f"sour{n}:dc:abor")
        self._t.write(f"sour{n}:dc:volt:mode fix")
        self._fixed.add(n)
        self._t.write(f"sour{n}:volt {level:.9g}")

    def sense(self, channel: str) -> float:
        n = self._number(channel, "current", "current")
        aperture = self._integration.get(channel)
        if aperture is not None and self._aperture.get(n) != aperture:
            self._t.write(f"sens{n}:aper {aperture:.9g}")
            self._aperture[n] = aperture
        return float(self._t.query(f"read? (@{n})"))

    def close(self) -> None:
        self._t.close()
