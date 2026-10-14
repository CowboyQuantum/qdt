"""QDevil QDAC-II driver: 24 DC voltage channels with per-channel current readout, over SCPI.

`QDac2` is a `LevelSource` on its voltage terminals and a `LevelSense` on its current-readout
terminals (ADR 0016). A `ChannelMap` declares which: a 'voltage' id is a source terminal, a 'current'
id a readout terminal, and one physical channel may appear under both (e.g. 'ch03' voltage and
'ch03_i' current). Undeclared ids are voltage for `set`/`get` and current for `sense`. The channel
number is the digits of the id, 1..24.

SCPI commands used (from the QDAC-II manual; confirm on the first bench run):

    *IDN?                       identity; must contain 'QDAC-II'
    sour{n}:dc:volt:mode fix    put channel n in fixed DC mode (sent once, before its first set)
    sour{n}:volt {v}            apply v volts to channel n
    sour{n}:volt?               read back channel n's setpoint (volts)
    sens{n}:aper {s}            current-sensor aperture in seconds (sent once, if declared)
    read? (@{n})                measure channel n's current (amperes)

The transport is `ScpiTransport`; pyvisa is imported lazily by `open_visa`, so this module imports
without the extra.
"""

from qdt_schemas.stand import ChannelMap, InstrumentConfig

from ..scpi import ScpiTransport, channel_number, open_visa

CHANNELS = (1, 24)
USB_BAUD_RATE = 921600  # the rear USB port's virtual serial speed (manual 4.3.2)
MAX_VOLTS = 10.0


class QDac2:
    """QDAC-II as `LevelSource` (voltage terminals) and `LevelSense` (current readout)."""

    def __init__(self, transport: ScpiTransport, channels: tuple[ChannelMap, ...] = ()) -> None:
        self._t = transport
        idn = transport.query("*IDN?")
        if "QDAC-II" not in idn:
            raise ValueError(f"not a QDAC-II: {idn!r}")
        self._quantity = {c.channel: c.quantity for c in channels}
        self._integration = {c.channel: c.integration_s for c in channels if c.integration_s}
        self._fixed: set[int] = set()
        self._aperture: dict[int, float] = {}

    @classmethod
    def from_config(cls, instrument: InstrumentConfig, channels: tuple[ChannelMap, ...]) -> "QDac2":
        """`BackendFactory` (ADR 0021): opens `settings['address']` (a VISA resource string). A serial
        address (`ASRL...`, the rear USB port) runs at the instrument's fixed 921600 baud unless
        `settings['baud_rate']` says otherwise."""
        address = instrument.settings.get("address")
        if not address:
            raise ValueError(f"instrument {instrument.id!r} has no settings['address']")
        baud = instrument.settings.get("baud_rate", USB_BAUD_RATE)
        return cls(open_visa(str(address), baud_rate=int(baud)), channels)

    def _number(self, channel: str, quantity: str, default: str) -> int:
        declared = self._quantity.get(channel, default)
        if declared != quantity:
            raise ValueError(f"channel {channel!r} is a {declared} terminal, not {quantity}")
        return channel_number(channel, *CHANNELS)

    def set(self, channel: str, value: float) -> None:
        n = self._number(channel, "voltage", "voltage")
        if not abs(value) <= MAX_VOLTS:
            raise ValueError(f"{value} V on {channel!r} is outside +/-{MAX_VOLTS} V")
        if n not in self._fixed:
            self._t.write(f"sour{n}:dc:volt:mode fix")
            self._fixed.add(n)
        self._t.write(f"sour{n}:volt {value:.9g}")

    def get(self, channel: str) -> float:
        n = self._number(channel, "voltage", "voltage")
        return float(self._t.query(f"sour{n}:volt?"))

    def sense(self, channel: str) -> float:
        n = self._number(channel, "current", "current")
        aperture = self._integration.get(channel)
        if aperture is not None and self._aperture.get(n) != aperture:
            self._t.write(f"sens{n}:aper {aperture:.9g}")
            self._aperture[n] = aperture
        return float(self._t.query(f"read? (@{n})"))

    def close(self) -> None:
        self._t.close()
