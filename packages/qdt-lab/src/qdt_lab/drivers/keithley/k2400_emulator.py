"""In-process emulator of a Keithley 2400-series SourceMeter behind a resistive load (tests only).

`Keithley2400Emulator` implements `ScpiTransport` for exactly the commands `Keithley2400` sends in the
dialect of the emulated model; anything else, including the other dialect's commands, raises
ValueError so a typo fails the tests. It models one terminal into `load_ohm`: sourcing V measures
I = V / load clamped to the current compliance, sourcing I measures V = I * load clamped to the
voltage compliance. Readings take NPLC / line frequency seconds of wall clock, as a real aperture does,
and exist only while the output is on.
"""

import math
import re
import time
from collections.abc import Callable

import numpy as np

from qdt_schemas.stand import ChannelMap

from .k2400 import LEGACY_MODELS, NEW_MODELS, NPLC_MAX, NPLC_MIN, Keithley2400

_NUM = r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"
_LEGACY_FORM_DEFAULT = ("VOLT", "CURR", "RES", "TIME", "STAT")


class Keithley2400Emulator:
    """A 2400-series SMU into a resistor, speaking the SCPI dialect of `model`."""

    def __init__(
        self,
        model: str = "2400",
        load_ohm: float = 1e6,
        line_frequency: float = 50.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if model not in LEGACY_MODELS | NEW_MODELS:
            raise ValueError(f"unknown model {model!r}")
        self.model, self.load_ohm, self.line_frequency = model, load_ohm, line_frequency
        self.legacy = model in LEGACY_MODELS
        self._sleep = sleep
        self.log: list[str] = []
        self.output = False
        self.source_func = "VOLT"
        self.level = {"VOLT": 0.0, "CURR": 0.0}
        self.current_limit = 1.05e-4
        self.voltage_limit = 21.0
        self.sense_func = "CURR"
        self.form_elem: tuple[str, ...] = _LEGACY_FORM_DEFAULT
        self.nplc = {"VOLT": 1.0, "CURR": 1.0}
        self.closed = False
        self._writes = self._legacy_writes() if self.legacy else self._new_writes()

    # -- command tables ---------------------------------------------------------------------------

    def _common_writes(self) -> list[tuple[str, Callable[..., None]]]:
        return [
            (r":SOUR:FUNC (VOLT|CURR)", self._set_source_func),
            (r':SENS:FUNC "(VOLT|CURR)"', self._set_sense_func),
            (rf":SENS:(VOLT|CURR):NPLC {_NUM}", self._set_nplc),
            (r":OUTP (ON|OFF)", self._set_output),
        ]

    def _legacy_writes(self) -> list[tuple[str, Callable[..., None]]]:
        return self._common_writes() + [
            (r":SOUR:(VOLT|CURR):MODE FIX", lambda f: None),
            (rf":SOUR:(VOLT|CURR):LEV {_NUM}", self._set_level),
            (rf":SENS:CURR:PROT {_NUM}", self._set_current_limit),
            (rf":SENS:VOLT:PROT {_NUM}", self._set_voltage_limit),
            (r":FORM:ELEM (VOLT|CURR)", self._set_form_elem),
        ]

    def _new_writes(self) -> list[tuple[str, Callable[..., None]]]:
        return self._common_writes() + [
            (rf":SOUR:(VOLT|CURR) {_NUM}", self._set_level),
            (rf":SOUR:VOLT:ILIM {_NUM}", self._set_current_limit),
            (rf":SOUR:CURR:VLIM {_NUM}", self._set_voltage_limit),
        ]

    # -- ScpiTransport ----------------------------------------------------------------------------

    def write(self, command: str) -> None:
        self._check_open()
        self.log.append(command)
        for pattern, action in self._writes:
            m = re.fullmatch(pattern, command)
            if m:
                action(*m.groups())
                return
        raise ValueError(f"emulated {self.model}: unknown command {command!r}")

    def query(self, command: str) -> str:
        self._check_open()
        self.log.append(command)
        if command == "*IDN?":
            return f"KEITHLEY INSTRUMENTS INC.,MODEL {self.model},EMULATED,0.0.0"
        if command == ":SYST:LFR?":
            return f"{self.line_frequency:g}"
        if command == ":READ?":
            return self._read()
        level = (
            re.fullmatch(r":SOUR:(VOLT|CURR):LEV\?", command)
            if self.legacy
            else re.fullmatch(r":SOUR:(VOLT|CURR)\?", command)
        )
        if level:
            return f"{self.level[level.group(1)]:.9g}"
        raise ValueError(f"emulated {self.model}: unknown query {command!r}")

    def query_block(self, command: str, dtype: str) -> np.ndarray:
        raise ValueError(f"emulated {self.model}: no block queries ({command!r})")

    def close(self) -> None:
        self.closed = True

    # -- model ------------------------------------------------------------------------------------

    def terminal(self) -> tuple[float, float]:
        """(voltage, current) at the terminal for the present source setting and load."""
        r = self.load_ohm
        if self.source_func == "VOLT":
            v = self.level["VOLT"]
            i = v / r
            if abs(i) > self.current_limit:
                i = math.copysign(self.current_limit, i)
                v = i * r
        else:
            i = self.level["CURR"]
            v = i * r
            if abs(v) > self.voltage_limit:
                v = math.copysign(self.voltage_limit, v)
                i = v / r
        return v, i

    def _read(self) -> str:
        if not self.output:
            raise ValueError(f"emulated {self.model}: :READ? with the output off")
        self._sleep(self.nplc[self.sense_func] / self.line_frequency)
        v, i = self.terminal()
        values = {"VOLT": v, "CURR": i, "RES": v / i if i else 9.91e37, "TIME": 0.0, "STAT": 0.0}
        elems = self.form_elem if self.legacy else (self.sense_func,)
        return ",".join(f"{values[e]:.9e}" for e in elems)

    # -- actions ----------------------------------------------------------------------------------

    def _check_open(self) -> None:
        if self.closed:
            raise ValueError(f"emulated {self.model}: transport is closed")

    def _set_source_func(self, func: str) -> None:
        self.source_func = func

    def _set_sense_func(self, func: str) -> None:
        self.sense_func = func

    def _set_nplc(self, func: str, n: str) -> None:
        value = float(n)
        if not NPLC_MIN <= value <= NPLC_MAX:
            raise ValueError(f"emulated {self.model}: NPLC {value} out of range")
        self.nplc[func] = value

    def _set_output(self, state: str) -> None:
        self.output = state == "ON"

    def _set_level(self, func: str, value: str) -> None:
        self.level[func] = float(value)

    def _set_current_limit(self, value: str) -> None:
        self.current_limit = float(value)

    def _set_voltage_limit(self, value: str) -> None:
        self.voltage_limit = float(value)

    def _set_form_elem(self, elem: str) -> None:
        self.form_elem = (elem,)


def emulated(model: str = "2400", channels: tuple[ChannelMap, ...] = (), **kw) -> Keithley2400:
    """A `Keithley2400` driving a `Keithley2400Emulator(model)`. Keywords `load_ohm`, `line_frequency`
    and `sleep` go to the emulator; the rest (limits) to the driver."""
    emu_keys = ("load_ohm", "line_frequency", "sleep")
    emu = Keithley2400Emulator(model, **{k: kw.pop(k) for k in emu_keys if k in kw})
    return Keithley2400(emu, channels, **kw)
