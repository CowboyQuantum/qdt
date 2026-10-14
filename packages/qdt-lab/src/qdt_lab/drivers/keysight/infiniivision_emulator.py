"""An in-process `ScpiTransport` emulating the InfiniiVision X subset `InfiniiVisionX` uses.

It answers exactly the commands the driver sends and raises ValueError on anything else, so the
conformance suite exercises the real driver code without hardware. Every command is recorded in `log`.
"""

import re
from collections.abc import Callable

import numpy as np

from qdt_schemas.stand import ChannelMap

from .infiniivision import InfiniiVisionX

Signal = Callable[[np.ndarray, int], np.ndarray]
"""signal(t, k): volts at absolute times `t` (s, trigger at 0) for record `k`."""


def ring_down(t: np.ndarray, k: int, noise: float = 0.01, seed: int = 0) -> np.ndarray:
    """The default signal: a damped ring-down starting at the trigger plus seeded Gaussian noise,
    deterministic in (seed, k, len(t))."""
    tp = np.clip(t, 0.0, None)
    clean = np.where(t >= 0, np.exp(-tp / 250e-9) * np.cos(2 * np.pi * 8e6 * tp), 0.0)
    return clean + np.random.default_rng([seed, k]).normal(0.0, noise, t.size)


_NUM = r"([-+0-9.eE]+)"
_SETTINGS = {
    ":WAVeform:FORMat": "WORD",
    ":WAVeform:BYTeorder": "LSBFirst",
    ":WAVeform:UNSigned": "0",
    ":WAVeform:POINts:MODE": "RAW",
}


class InfiniiVisionEmulator:
    """Tracks the timebase and waveform settings; each `:DIGitize CHANnel<n>` captures record k =
    `signal(t, k)` on t = position + i*range/points (xreference 0), quantized to int16 codes of
    `yincrement` volts (yorigin 0, yreference 0). `points` caps the raw points; fewer are captured when
    `:WAVeform:POINts` asks for fewer."""

    def __init__(
        self, signal: Signal | None = None, points: int = 2000, yincrement: float = 1e-4
    ) -> None:
        self.signal: Signal = signal or ring_down
        self.points, self.yincrement = points, yincrement
        self.log: list[str] = []
        self.range: float = 1e-3
        self.position: float = 0.0
        self.reference: str = "CENTer"
        self.source: int = 1
        self.requested_points: int = points
        self.settings: dict[str, str] = {}
        self.records = 0
        self._capture: tuple[int, float, float, np.ndarray] | None = None
        self.closed = False

    def write(self, command: str) -> None:
        self._check_open()
        self.log.append(command)
        head, _, arg = command.partition(" ")
        if head in _SETTINGS:
            if arg != _SETTINGS[head]:
                raise ValueError(f"emulator supports only {head} {_SETTINGS[head]}, got {arg!r}")
            self.settings[head] = arg
        elif head == ":TIMebase:REFerence":
            if arg != "LEFT":
                raise ValueError(f"emulator supports only :TIMebase:REFerence LEFT, got {arg!r}")
            self.reference = arg
        elif head == ":TIMebase:RANGe" and re.fullmatch(_NUM, arg):
            if not float(arg) > 0:
                raise ValueError(f"timebase range must be positive, got {arg}")
            self.range = float(arg)
        elif head == ":TIMebase:POSition" and re.fullmatch(_NUM, arg):
            self.position = float(arg)
        elif head == ":WAVeform:SOURce" and (m := re.fullmatch(r"CHANnel([1-4])", arg)):
            self.source = int(m.group(1))
        elif head == ":WAVeform:POINts" and arg.isdigit():
            self.requested_points = int(arg)
        elif head == ":DIGitize" and (m := re.fullmatch(r"CHANnel([1-4])", arg)):
            self._digitize(int(m.group(1)))
        else:
            raise ValueError(f"emulator does not understand {command!r}")

    def _digitize(self, channel: int) -> None:
        if self.reference != "LEFT":
            raise ValueError("emulator captures only with :TIMebase:REFerence LEFT")
        n = min(self.points, self.requested_points)
        xinc = self.range / n
        t = self.position + np.arange(n) * xinc
        volts = np.asarray(self.signal(t, self.records), dtype=np.float64)
        codes = np.clip(np.round(volts / self.yincrement), -32768, 32767).astype(np.int16)
        self._capture = (channel, xinc, self.position, codes)
        self.records += 1

    def query(self, command: str) -> str:
        self._check_open()
        self.log.append(command)
        if command == "*IDN?":
            return "KEYSIGHT TECHNOLOGIES,DSOX3024T,0,0.0"
        if command == "*OPC?":
            return "1"
        if command == ":WAVeform:PREamble?":
            _, xinc, xorig, codes = self._served()
            return f"1,0,{codes.size},1,{xinc:.12e},{xorig:.12e},0,{self.yincrement:.12e},0.0,0"
        raise ValueError(f"emulator does not understand query {command!r}")

    def query_block(self, command: str, dtype: str) -> np.ndarray:
        self._check_open()
        self.log.append(command)
        if command != ":WAVeform:DATA?":
            raise ValueError(f"emulator does not understand block query {command!r}")
        if np.dtype(dtype) != np.dtype("<i2"):
            raise ValueError(f"emulator serves WORD data as '<i2', not {dtype!r}")
        missing = set(_SETTINGS) - set(self.settings)
        if missing:
            raise ValueError(f"waveform transfer not configured: {sorted(missing)}")
        return self._served()[3].copy()

    def _served(self) -> tuple[int, float, float, np.ndarray]:
        if self._capture is None or self._capture[0] != self.source:
            raise ValueError(f"no capture on :WAVeform:SOURce CHANnel{self.source}")
        return self._capture

    def close(self) -> None:
        self.closed = True

    def _check_open(self) -> None:
        if self.closed:
            raise ValueError("transport is closed")


def emulated(
    channels: tuple[ChannelMap, ...] | None = None, max_records: int = 8, **kw
) -> InfiniiVisionX:
    """An `InfiniiVisionX` on an `InfiniiVisionEmulator(**kw)`. By default the logical channel 'ch00'
    (the conformance suite's channel) maps to analog input 1."""
    if channels is None:
        channels = (
            ChannelMap(logical="ch00", instrument="scope0", channel="1", quantity="voltage"),
        )
    return InfiniiVisionX(InfiniiVisionEmulator(**kw), channels, max_records=max_records)
