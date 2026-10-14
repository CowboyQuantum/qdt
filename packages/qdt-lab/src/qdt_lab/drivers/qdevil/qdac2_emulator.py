"""SCPI emulator of the QDAC-II for tests: understands exactly the commands `QDac2` sends.

Any other command raises ValueError, so a typo in the driver fails the suite. Each channel drives a
resistive load (`load_ohm`, default 1 MΩ): `read? (@n)` returns setpoint / load, after sleeping the
channel's aperture if one was set.
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


class Qdac2Emulator:
    """In-memory QDAC-II implementing `ScpiTransport`."""

    def __init__(self, load_ohm: dict[int, float] | None = None) -> None:
        self.load_ohm: dict[int, float] = dict(load_ohm or {})
        self.volts: dict[int, float] = {}
        self.mode: dict[int, str] = {}
        self.aperture: dict[int, float] = {}
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
        else:
            raise ValueError(f"emulator does not understand {command!r}")

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
