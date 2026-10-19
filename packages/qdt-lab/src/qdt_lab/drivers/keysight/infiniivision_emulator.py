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
_TRIGGER = {  # the external trigger a scope with `trigger_from` is set to at arm (ADR 0063)
    ":TRIGger:MODE": "EDGE",
    ":TRIGger:EDGE:SOURce": "EXTernal",
    ":TRIGger:EDGE:SLOPe": "POSitive",
    ":TRIGger:SWEep": "NORMal",
}


class InfiniiVisionEmulator:
    """Tracks the timebase and waveform settings; each `:SINGle` captures record k = `signal(t, k)`
    on t = position - range/10 + i*range/points (LEFT reference: one division in from the left edge,
    as the instrument does; xreference 0), quantized to int16 codes of `yincrement` volts (yorigin 0,
    yreference 0), for the waveform source channel; in segmented mode one `:SINGle` captures
    `:ACQuire:SEGMented:COUNt` records at once and `:ACQuire:SEGMented:INDex k` selects one; with
    `:WAVeform:SEGMented:ALL ON` one `:WAVeform:DATA?` returns every segment in turn while the preamble
    still describes one. `:RSTate?` reads STOP at once (an emulated trigger is instant). `points` caps the
    raw points; fewer are captured when `:WAVeform:POINts` asks for fewer. `segmented=False` emulates an
    instrument without the mode (`:ACQuire:MODE?` stays RTIM); `all_segments=False` one without the
    one-transfer readout, which queues -113 for the command, as an instrument does for an unknown header,
    instead of raising like every other unknown command; `all_segments="repeat"` the HD304MSO (firmware
    10.16, bench 2026-10-19), which accepts the command and returns the selected segment once per
    segment."""

    def __init__(
        self,
        signal: Signal | None = None,
        points: int = 2000,
        yincrement: float = 1e-4,
        segmented: bool = True,
        all_segments: bool | str = True,
        signals: dict[int, Signal] | None = None,
        empty_preambles: int = 0,
    ) -> None:
        """`signals` gives a channel its own signal (channel number → `signal(t, k)`); every other
        channel captures `signal`. One `:SINGle` captures all four channels, as the instrument does.
        `empty_preambles` answers that many `:WAVeform:PREamble?` queries after each `:SINGle` with
        every field empty, as the HD304MSO did for a second channel right after an acquisition."""
        self.signal: Signal = signal or ring_down
        self.signals: dict[int, Signal] = dict(signals or {})
        self.empty_preambles = empty_preambles
        self._empty_left = 0
        self.points, self.yincrement = points, yincrement
        self.supports_segmented = segmented
        self.supports_all_segments = all_segments
        self.all_segments = False
        self.errors: list[str] = []
        self.log: list[str] = []
        self.range: float = 1e-3
        self.position: float = 0.0
        self.reference: str = "CENTer"
        self.source: int = 1
        self.requested_points: int = points
        self.settings: dict[str, str] = {}
        self.trigger: dict[str, str] = {}
        self.acquire_mode: str = "RTIM"
        self.segment_count: int = 1
        self.records = 0
        self.singles = 0
        self._captures: dict[int, list[tuple[float, float, np.ndarray]]] = {}
        self._index = 0
        self.closed = False

    def _acquired(self) -> int:
        """Segments held by the last acquisition (the same count on every channel)."""
        return len(self._captures.get(1, []))

    def write(self, command: str) -> None:
        self._check_open()
        self.log.append(command)
        head, _, arg = command.partition(" ")
        if head in _SETTINGS:
            if arg != _SETTINGS[head]:
                raise ValueError(f"emulator supports only {head} {_SETTINGS[head]}, got {arg!r}")
            self.settings[head] = arg
        elif head in _TRIGGER:
            if arg != _TRIGGER[head]:
                raise ValueError(f"emulator supports only {head} {_TRIGGER[head]}, got {arg!r}")
            self.trigger[head] = arg
        elif head == ":TRIGger:EDGE:LEVel" and re.fullmatch(_NUM, arg):
            self.trigger[head] = arg
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
        elif head == ":ACQuire:MODE" and arg in ("SEGMented", "RTIMe"):
            self.acquire_mode = "SEGM" if arg == "SEGMented" and self.supports_segmented else "RTIM"
        elif head == ":ACQuire:SEGMented:COUNt" and arg.isdigit():
            self.segment_count = int(arg)
        elif head == ":ACQuire:SEGMented:INDex" and arg.isdigit():
            k = int(arg)
            if self.acquire_mode != "SEGM" or not 1 <= k <= self._acquired():
                raise ValueError(f"no segment {k} ({self._acquired()} acquired)")
            self._index = k - 1
        elif head == ":WAVeform:SEGMented:ALL" and arg in ("ON", "OFF"):
            if self.supports_all_segments:
                self.all_segments = arg == "ON"
            else:
                self.errors.append('-113,"Undefined header;WAVEFORM:SEGMENTED:ALL"')
        elif command == "*CLS":
            self.errors.clear()
        elif command == ":SINGle":
            self._single()
        elif command in (":STOP", ":TRIGger:FORCe"):
            pass
        else:
            raise ValueError(f"emulator does not understand {command!r}")

    def _single(self) -> None:
        if self.reference != "LEFT":
            raise ValueError("emulator captures only with :TIMebase:REFerence LEFT")
        self.singles += 1
        n = min(self.points, self.requested_points)
        xinc = self.range / n
        left_edge = self.position - self.range * 0.1
        t = left_edge + np.arange(n) * xinc
        count = self.segment_count if self.acquire_mode == "SEGM" else 1
        self._captures = {n: [] for n in (1, 2, 3, 4)}
        for _ in range(count):
            for n, captures in self._captures.items():  # every channel, the same trigger
                volts = np.asarray(
                    self.signals.get(n, self.signal)(t, self.records), dtype=np.float64
                )
                codes = np.clip(np.round(volts / self.yincrement), -32768, 32767).astype(np.int16)
                captures.append((xinc, left_edge, codes))
            self.records += 1
        self._index = 0
        self._empty_left = self.empty_preambles

    def query(self, command: str) -> str:
        self._check_open()
        self.log.append(command)
        if command == "*IDN?":
            return "KEYSIGHT TECHNOLOGIES,DSOX3024T,0,0.0"
        if command == "*OPC?":
            return "1"
        if command == ":AER?":
            return "+1"  # armed at once
        if command == ":RSTate?":
            return "STOP"  # an emulated acquisition completes at once
        if command == ":TRIGger:SWEep?":
            return self.trigger.get(":TRIGger:SWEep", "AUTO")
        if command == ":ACQuire:MODE?":
            return self.acquire_mode
        if command == ":SYSTem:ERRor?":
            return self.errors.pop(0) if self.errors else '+0,"No error"'
        if command == ":WAVeform:PREamble?":
            if self._empty_left > 0:
                self._empty_left -= 1
                return ",,,,,,,,,"
            xinc, xorig, codes = self._served()
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
        if self.all_segments and self.acquire_mode == "SEGM":
            if (
                self.supports_all_segments == "repeat"
            ):  # the HD3's answer: the selected one, N times
                return np.concatenate([self._served()[2]] * self._acquired())
            return np.concatenate([codes for _, _, codes in self._captures[self.source]])
        return self._served()[2].copy()

    def _served(self) -> tuple[float, float, np.ndarray]:
        if not self._acquired():
            raise ValueError("no acquisition: send :SINGle first")
        return self._captures[self.source][self._index]

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
