"""SCPI emulator of the QDAC-II for tests: understands exactly the commands `QDac2` sends.

Any other command raises ValueError, so a typo in the driver fails the suite. Each channel drives a
resistive load (`load_ohm`, default 1 MΩ): `read? (@n)` returns setpoint / load, after sleeping the
channel's aperture if one was set. A channel in list mode (ADR 0064) advances one point per
`trigger(source)`: `*TRG` fires `bus`; a test fires `ext<k>` the way the OPX's marker line does.
"""

import re
import time

import numpy as np

from qdt_schemas.stand import ChannelMap

from .qdac2 import CHANNELS, QDac2

IDN = "QDevil, QDAC-II, 0, 0-0.0.0"
_NUM = r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"
_MODE = re.compile(r"sour(\d+):dc:volt:mode fix")
_VOLT = re.compile(rf"sour(\d+):volt {_NUM}")
_VOLT_Q = re.compile(r"sour(\d+):volt\?")
_APER = re.compile(rf"sens(\d+):aper {_NUM}")
_READ_Q = re.compile(r"read\? \(@(\d+)\)")
_MODE_LIST = re.compile(r"sour(\d+):dc:volt:mode list")
_LIST_VOLT = re.compile(r"sour(\d+):list:volt ([-+0-9.eE,]+)")
_LIST_TMOD = re.compile(r"sour(\d+):list:tmod step")
_LIST_COUN = re.compile(r"sour(\d+):list:coun 1")
_LIST_DIR = re.compile(r"sour(\d+):list:dir up")
_TRIG_SOUR = re.compile(r"sour(\d+):dc:trig:sour (bus|ext[1-4])")
_INIT_CONT = re.compile(r"sour(\d+):dc:init:cont (on|off)")
_ABOR = re.compile(r"sour(\d+):dc:abor")


class Qdac2Emulator:
    """In-memory QDAC-II implementing `ScpiTransport`."""

    def __init__(self, load_ohm: dict[int, float] | None = None) -> None:
        self.load_ohm: dict[int, float] = dict(load_ohm or {})
        self.volts: dict[int, float] = {}
        self.mode: dict[int, str] = {}
        self.aperture: dict[int, float] = {}
        self.lists: dict[int, list[float]] = {}
        self.trigger_source: dict[int, str] = {}
        self.armed: dict[int, int] = {}  # channel -> index of the point last played (-1: none yet)
        self.triggers: list[str] = []  # every trigger fired, in order
        self.log: list[str] = []
        self.closed = False

    @staticmethod
    def _ch(text: str) -> int:
        n = int(text)
        if not CHANNELS[0] <= n <= CHANNELS[1]:
            raise ValueError(f"no channel {n}")
        return n

    def write(self, command: str) -> None:
        self.log.append(command)
        if m := _MODE.fullmatch(command):
            self.mode[self._ch(m[1])] = "fix"
        elif m := _VOLT.fullmatch(command):
            self.volts[self._ch(m[1])] = float(m[2])
        elif m := _APER.fullmatch(command):
            self.aperture[self._ch(m[1])] = float(m[2])
        elif m := _MODE_LIST.fullmatch(command):
            self.mode[self._ch(m[1])] = "list"
        elif m := _LIST_VOLT.fullmatch(command):
            self.lists[self._ch(m[1])] = [float(v) for v in m[2].split(",")]
        elif (
            _LIST_TMOD.fullmatch(command)
            or _LIST_COUN.fullmatch(command)
            or _LIST_DIR.fullmatch(command)
        ):
            pass
        elif m := _TRIG_SOUR.fullmatch(command):
            self.trigger_source[self._ch(m[1])] = m[2]
        elif m := _INIT_CONT.fullmatch(command):
            n = self._ch(m[1])
            if m[2] == "off":
                self.armed.pop(n, None)
            else:
                if (
                    self.mode.get(n) != "list"
                    or n not in self.lists
                    or n not in self.trigger_source
                ):
                    raise ValueError(
                        f"channel {n}: init needs list mode, a list and a trigger source"
                    )
                self.armed[n] = -1
        elif m := _ABOR.fullmatch(command):
            self.armed.pop(self._ch(m[1]), None)
        elif command == "*TRG":
            self.trigger("bus")
        else:
            raise ValueError(f"emulator does not understand {command!r}")

    def trigger(self, source: str) -> None:
        """A trigger on `source` (`bus`, `ext1`..): every armed channel listening there plays its next
        point; after the last point the next trigger starts the list again (Probe 05)."""
        self.triggers.append(source)
        for n, i in list(self.armed.items()):
            if self.trigger_source.get(n) != source:
                continue
            i = (i + 1) % len(self.lists[n])
            self.armed[n] = i
            self.volts[n] = self.lists[n][i]

    def query(self, command: str) -> str:
        self.log.append(command)
        if command == "*IDN?":
            return IDN
        if m := _VOLT_Q.fullmatch(command):
            return repr(self.volts.get(self._ch(m[1]), 0.0))
        if m := _READ_Q.fullmatch(command):
            n = self._ch(m[1])
            if n in self.aperture:
                time.sleep(self.aperture[n])
            return repr(self.volts.get(n, 0.0) / self.load_ohm.get(n, 1e6))
        raise ValueError(f"emulator does not understand {command!r}")

    def query_block(self, command: str, dtype: str) -> np.ndarray:
        self.log.append(command)
        raise ValueError(f"emulator does not understand {command!r}")

    def close(self) -> None:
        self.closed = True


def emulated(channels: tuple[ChannelMap, ...] = ()) -> QDac2:
    """A `QDac2` driving a fresh `Qdac2Emulator` (reach it as `driver._t`)."""
    return QDac2(Qdac2Emulator(), channels)
