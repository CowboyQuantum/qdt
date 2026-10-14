"""Keithley 2400-series SourceMeter: one source/measure terminal over SCPI (extra [smu]).

The instrument is a `LevelSource` and a `LevelSense` on the same terminal. Every channel id names that
one terminal; the channel's declared `ChannelMap.quantity` says what a call means there:

    set/get on a 'voltage' channel  source voltage (with the current compliance)
    set/get on a 'current' channel  source current (with the voltage compliance)
    sense on a 'current' channel    measure current
    sense on a 'voltage' channel    measure voltage

Undeclared channel ids are voltage for `set`/`get` and current for `sense`. A sense channel's
`integration_s` becomes NPLC = integration_s * line frequency, clamped to 0.01..10.

Two command dialects, picked from `*IDN?`:

    legacy SCPI   2400, 2401, 2410, 2420, 2425, 2430, 2440
    new SCPI      2450, 2460, 2461, 2470 (touchscreen models)

Commands follow the Keithley reference manuals of both families and must be confirmed on the first
bench run. Function, compliance, format and NPLC commands are sent only when they change; the output
is turned on at the first `set` (or at the first `sense`, sourcing 0 V, when nothing was set).

Bench, 2026-10-14 (a 2450, firmware 1.7.16a): the new-dialect commands above pass the conformance suite.
The 2450 accepts one raw-socket (port 5025) connection at a time and resets any second one, so `close`
this driver before opening another to the same instrument.
pyvisa is needed only by `from_config` (through `open_visa`); importing this module needs no extra.
"""

import re

from qdt_schemas.stand import ChannelMap, InstrumentConfig

from ..scpi import ScpiTransport, open_visa

LEGACY_MODELS = frozenset({"2400", "2401", "2410", "2420", "2425", "2430", "2440"})
NEW_MODELS = frozenset({"2450", "2460", "2461", "2470"})

NPLC_MIN, NPLC_MAX = 0.01, 10.0
DEFAULT_LINE_FREQUENCY = 50.0

_FUNC = {"voltage": "VOLT", "current": "CURR"}


def parse_model(idn: str) -> str:
    """The model number in a `*IDN?` response ('KEITHLEY INSTRUMENTS INC.,MODEL 2400,...');
    ValueError unless it is a supported 2400-series model."""
    fields = idn.split(",")
    match = re.search(r"(\d{4})", fields[1] if len(fields) > 1 else idn)
    model = match.group(1) if match else ""
    if model not in LEGACY_MODELS | NEW_MODELS:
        raise ValueError(f"unsupported Keithley model in *IDN? response {idn!r}")
    return model


def _num(value: float) -> str:
    return f"{value:.9g}"


class Keithley2400:
    """Keithley 2400-series SourceMeter as `LevelSource` + `LevelSense` on its single terminal."""

    single_terminal = (
        True  # every channel id is the one terminal (the conformance suite reads this)
    )

    def __init__(
        self,
        transport: ScpiTransport,
        channels: tuple[ChannelMap, ...] = (),
        current_limit_a: float = 1e-3,
        voltage_limit_v: float = 10.0,
    ) -> None:
        self._t = transport
        self._channels: dict[str, ChannelMap] = {}
        for c in channels:
            prior = self._channels.get(c.channel)
            if prior is not None and prior.quantity != c.quantity:
                raise ValueError(
                    f"channel {c.channel!r} declared as both {prior.quantity} and {c.quantity}"
                )
            if c.quantity not in _FUNC:
                raise ValueError(f"channel {c.channel!r}: quantity {c.quantity!r} is not served")
            self._channels[c.channel] = c
        self._limits = {"VOLT": current_limit_a, "CURR": voltage_limit_v}
        self.model = parse_model(self._t.query("*IDN?"))
        self.dialect = "legacy" if self.model in LEGACY_MODELS else "new"
        try:
            self.line_frequency = float(self._t.query(":SYST:LFR?"))
        except Exception:  # noqa: BLE001 - any transport error (VisaIOError) or bad reply
            self.line_frequency = DEFAULT_LINE_FREQUENCY
        # Cached instrument state; None means unknown, so the first use always sends.
        self._source_func: str | None = None
        self._compliance: dict[str, float] = {}
        self._sense_func: str | None = None
        self._form_elem: str | None = None
        self._nplc: dict[str, float] = {}
        self._output_on = False
        self._closed = False

    @classmethod
    def from_config(
        cls, instrument: InstrumentConfig, channels: tuple[ChannelMap, ...]
    ) -> "Keithley2400":
        """`BackendFactory` (ADR 0021): opens `settings['address']` over VISA; optional settings
        'current_limit_a' and 'voltage_limit_v' set the compliance limits."""
        address = instrument.settings.get("address")
        if not address:
            raise ValueError(f"instrument {instrument.id!r} has no settings['address']")
        kwargs = {
            key: float(instrument.settings[key])
            for key in ("current_limit_a", "voltage_limit_v")
            if key in instrument.settings
        }
        return cls(open_visa(str(address)), channels, **kwargs)

    # -- channel declarations -------------------------------------------------------------------

    def _quantity(self, channel: str, default: str) -> str:
        c = self._channels.get(channel)
        return c.quantity if c is not None else default

    # -- LevelSource ----------------------------------------------------------------------------

    def set(self, channel: str, value: float) -> None:
        self._source(_FUNC[self._quantity(channel, "voltage")], float(value))

    def get(self, channel: str) -> float:
        func = _FUNC[self._quantity(channel, "voltage")]
        query = f":SOUR:{func}:LEV?" if self.dialect == "legacy" else f":SOUR:{func}?"
        return float(self._t.query(query))

    # -- LevelSense -----------------------------------------------------------------------------

    def sense(self, channel: str) -> float:
        if not self._output_on:
            self._source("VOLT", 0.0)
        func = _FUNC[self._quantity(channel, "current")]
        if self._sense_func != func:
            self._t.write(f':SENS:FUNC "{func}"')
            self._sense_func = func
        if self.dialect == "legacy" and self._form_elem != func:
            self._t.write(f":FORM:ELEM {func}")
            self._form_elem = func
        c = self._channels.get(channel)
        if c is not None and c.integration_s:
            nplc = min(max(c.integration_s * self.line_frequency, NPLC_MIN), NPLC_MAX)
            if self._nplc.get(func) != nplc:
                self._t.write(f":SENS:{func}:NPLC {_num(nplc)}")
                self._nplc[func] = nplc
        return float(self._t.query(":READ?").split(",")[0])

    # -- lifecycle ------------------------------------------------------------------------------

    def close(self) -> None:
        """Turn the output off and release the transport; idempotent."""
        if self._closed:
            return
        try:
            self._t.write(":OUTP OFF")
            self._output_on = False
        finally:
            self._closed = True
            self._t.close()

    # -- internals ------------------------------------------------------------------------------

    def _source(self, func: str, value: float) -> None:
        """Source `value` of `func` ('VOLT' | 'CURR'), with the compliance on the other quantity."""
        if self._source_func != func:
            self._t.write(f":SOUR:FUNC {func}")
            if self.dialect == "legacy":
                self._t.write(f":SOUR:{func}:MODE FIX")
            self._source_func = func
        limit = self._limits[func]
        if self._compliance.get(func) != limit:
            if self.dialect == "legacy":
                other = "CURR" if func == "VOLT" else "VOLT"
                self._t.write(f":SENS:{other}:PROT {_num(limit)}")
            else:
                self._t.write(f":SOUR:{func}:{'ILIM' if func == 'VOLT' else 'VLIM'} {_num(limit)}")
            self._compliance[func] = limit
        if self.dialect == "legacy":
            self._t.write(f":SOUR:{func}:LEV {_num(value)}")
        else:
            self._t.write(f":SOUR:{func} {_num(value)}")
        if not self._output_on:
            self._t.write(":OUTP ON")
            self._output_on = True
