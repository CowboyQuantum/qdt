"""Keysight InfiniiVision oscilloscope (DSOX/MSOX 1000-6000 X, HD3 series) as a `WaveformSense`, over SCPI.

The commands follow the InfiniiVision programmer's guide; confirmed on an HD304MSO (bench, 2026-10-14).

`arm` configures only what the declared grid fixes: the timebase (`:TIMebase:REFerence LEFT`,
`:TIMebase:RANGe`, `:TIMebase:POSition`) so one capture covers the declared time axis, and the waveform
transfer (signed 16-bit words, LSB first, raw points). Vertical scale, offset, coupling and the trigger
are left exactly as the user set them on the instrument: they belong to the signal, not to the grid.
The one exception (ADR 0063): a scope whose stand entry names `settings["trigger_from"]` (the
sequencer's marker channel wired to its EXT TRIG input) is set at `arm` to trigger on that input, a
rising edge at `settings["trigger_level_v"]` (default `EXT_TRIGGER_LEVEL_V`), NORMal sweep: a record is
the triggered one or the acquisition times out, never a free-run.

Acquisition is `:SINGle`, a wait for `:AER?` (armed), then a poll of `:RSTate?` until the scope
reports STOP, never `:DIGitize`: `:DIGitize` blocks the instrument's parser until it triggers, so an
acquisition left waiting wedged every later session until a device clear (bench, 2026-10-16). With the
trigger sweep AUTO (and no marker line) a trigger is forced after `AUTO_FORCE_S`, so an untriggered
capture free-runs as it did through `:DIGitize`.

With more than one record the scope acquires in **segmented** mode (`:ACQuire:MODE SEGMented`: one
`:SINGle` catches every trigger in hardware), when the instrument accepts it (the HD3 does; the mode is
read back); otherwise one `:SINGle` per record, which costs about half a second each on the HD3
(Probe 05). The segments are read **in one transfer** (`:WAVeform:SEGMented:ALL ON`, then one
`:WAVeform:DATA?` holding every segment in turn) when the scope accepts the command and the block is
exactly `records` segments of the preamble's length; otherwise segment by segment through
`:ACQuire:SEGMented:INDex`, which cost 0.3–0.5 s each on the HD3 (Probe 05). Which way works is
decided on the first segmented readout and kept (`segments_in_one_transfer`). Whether the HD3 takes the one
transfer is `bench/test_scope_segments.py`'s to show; until it has run on the bench, the per-segment
reads are what Probe 05 measured.

A record is converted to volts with the preamble and resampled onto the declared `LinearCoordinate`
(`np.interp`): the producer aligns, never the consumer (ADR 0015). A declared grid reaching more than
one sample interval outside the captured span raises. `settings["acquire_timeout_s"]` (default 600)
bounds a wait for triggers that never come.
"""

import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from qdt_schemas.data import Dataset, DatasetChunk, IndexSlice, LinearCoordinate
from qdt_schemas.stand import ChannelMap, InstrumentConfig

from ...stream.frame import Frame
from ..scpi import ScpiTransport, channel_number, open_visa

TIMEBASE_MARGIN = 0.02
"""Fraction of the declared span added to the timebase range so the last declared point is captured."""
LEFT_REFERENCE_FRACTION = 0.1
"""Where `:TIMebase:REFerence LEFT` sits: one graticule division in from the left edge of the screen."""

MIN_POINTS = 1000
"""Fewest raw points requested per record."""

ACQUIRE_TIMEOUT_S = 600.0
"""Default bound on one acquisition's wait for its trigger(s)."""
POLL_S = 0.02
"""Between `:RSTate?` polls while a single-shot waits for its trigger(s)."""
ARM_TIMEOUT_S = 5.0
"""Bound on the wait for `:AER?` to report the single-shot armed after `:SINGle`."""
AUTO_FORCE_S = 0.5
"""With the trigger sweep AUTO, a trigger is forced this long after the arm when none has come:
`:SINGle` waits for a real trigger even in AUTO (unlike `:DIGitize`, bench 2026-10-16), and AUTO means
"free-run when nothing triggers", as the instrument's RUN does."""

EXT_TRIGGER_LEVEL_V = 1.0
"""Default EXT TRIG level: below half of an LVTTL marker into the input's 1 MΩ (Probe 05 measures the
bench's marker level)."""

_MODEL = re.compile(r"^(DSOX|MSOX|HD3)\d")


class InfiniiVisionX:
    """`WaveformSense` on analog inputs 1..4 of an InfiniiVision X-series scope.

    `channels` are this instrument's `ChannelMap`s (ADR 0021); each must be a 'voltage' channel on an
    analog input. `arm` takes a vendor channel id ('1', 'CHAN2', 'ch3') or the logical name of one of
    `channels`. An unbounded record dimension yields `max_records` records.
    """

    def __init__(
        self,
        transport: ScpiTransport,
        channels: tuple[ChannelMap, ...] = (),
        max_records: int = 8,
        external_trigger_level_v: float | None = None,
        acquire_timeout_s: float = ACQUIRE_TIMEOUT_S,
    ) -> None:
        idn = transport.query("*IDN?")
        fields = [f.strip() for f in idn.split(",")]
        vendor = fields[0].upper()
        model = fields[1].upper().replace("-", "").replace(" ", "") if len(fields) > 1 else ""
        if not vendor.startswith(("KEYSIGHT", "AGILENT")):
            raise ValueError(f"not a Keysight/Agilent instrument: {vendor!r}, {model!r}")
        if not _MODEL.match(model):
            raise ValueError(f"not an InfiniiVision scope (DSOX/MSOX/HD3): {vendor!r}, {model!r}")
        if max_records < 1:
            raise ValueError(f"max_records must be >= 1, got {max_records}")
        self._t = transport
        self.idn = idn
        self.max_records = max_records
        self.external_trigger_level_v = external_trigger_level_v
        self.acquire_timeout_s = acquire_timeout_s
        self.segments_in_one_transfer: bool | None = None
        """Whether segments are read in one transfer: None until the first segmented readout tries."""
        self._logical: dict[str, int] = {}
        for ch in channels:
            if ch.quantity != "voltage":
                raise ValueError(
                    f"channel {ch.logical!r}: InfiniiVision X senses voltage only, not {ch.quantity!r}"
                )
            self._logical[ch.logical] = channel_number(ch.channel, 1, 4)

    @classmethod
    def from_config(
        cls, instrument: InstrumentConfig, channels: tuple[ChannelMap, ...]
    ) -> "InfiniiVisionX":
        """`BackendFactory` (ADR 0021): opens `instrument.settings['address']` over VISA. With
        `settings['trigger_from']` the scope triggers on its EXT TRIG input at `arm` (ADR 0063), at
        `settings['trigger_level_v']` volts (default `EXT_TRIGGER_LEVEL_V`)."""
        address = instrument.settings.get("address")
        if not address:
            raise ValueError(f"instrument {instrument.id!r} has no settings['address']")
        kw = {}
        if "max_records" in instrument.settings:
            kw["max_records"] = int(instrument.settings["max_records"])
        if instrument.settings.get("trigger_from"):
            kw["external_trigger_level_v"] = float(
                instrument.settings.get("trigger_level_v", EXT_TRIGGER_LEVEL_V)
            )
        if "acquire_timeout_s" in instrument.settings:
            kw["acquire_timeout_s"] = float(instrument.settings["acquire_timeout_s"])
        return cls(open_visa(str(address)), channels, **kw)

    def _channel(self, channel: str) -> int:
        if channel in self._logical:
            return self._logical[channel]
        return channel_number(channel, 1, 4)

    def arm(self, channel: str, dataset: Dataset, variable: str) -> "_ScopeRecordSource":
        v = next((v for v in dataset.data_vars if v.name == variable), None)
        if v is None:
            raise ValueError(f"dataset has no data variable {variable!r}")
        if len(v.dims) != 2:
            raise ValueError(f"variable {variable!r} must be (record, time); has dims {v.dims}")
        record_dim, time_dim = v.dims
        axis = [c for c in dataset.coords if c.dim == time_dim and isinstance(c, LinearCoordinate)]
        if len(axis) != 1:
            raise ValueError(
                f"variable {variable!r} needs exactly one declared LinearCoordinate on {time_dim!r} "
                "(ADR 0015: records land on the declared grid)"
            )
        n = self._channel(channel)
        n_records = next(d.size for d in dataset.dims if d.name == record_dim) or self.max_records
        start, stop, num = axis[0].start, axis[0].stop, axis[0].num
        span = stop - start
        if not span > 0:
            raise ValueError(
                f"variable {variable!r}: a scope capture needs stop > start on {time_dim!r}, "
                f"got start={start}, stop={stop}"
            )
        t = self._t
        t.write(
            ":STOP"
        )  # an acquisition left waiting by an earlier arm must not catch this one's trigger
        # LEFT puts the reference one division (10 % of the range) in from the screen's left edge, so
        # the capture starts at position - range/10 (bench, HD304MSO, 2026-10-14). Place it at `start`.
        rng = span * (1 + TIMEBASE_MARGIN)
        if self.external_trigger_level_v is not None:  # ADR 0063: the sequencer's marker triggers
            t.write(":TRIGger:MODE EDGE")
            t.write(":TRIGger:EDGE:SOURce EXTernal")
            t.write(":TRIGger:EDGE:SLOPe POSitive")
            t.write(f":TRIGger:EDGE:LEVel {self.external_trigger_level_v:.6g}")
            t.write(":TRIGger:SWEep NORMal")
        t.write(":TIMebase:REFerence LEFT")
        t.write(f":TIMebase:RANGe {rng:.12g}")
        t.write(f":TIMebase:POSition {start + rng * LEFT_REFERENCE_FRACTION:.12g}")
        t.write(f":WAVeform:SOURce CHANnel{n}")
        t.write(":WAVeform:FORMat WORD")
        t.write(":WAVeform:BYTeorder LSBFirst")
        t.write(":WAVeform:UNSigned 0")
        t.write(":WAVeform:POINts:MODE RAW")
        t.write(f":WAVeform:POINts {max(num, MIN_POINTS)}")
        auto = self.external_trigger_level_v is None and (
            t.query(":TRIGger:SWEep?").strip().upper().startswith("AUTO")
        )
        segmented = False
        if n_records > 1:  # catch every trigger in hardware, if the instrument can (ADR 0063)
            t.write(":ACQuire:MODE SEGMented")
            t.write(f":ACQuire:SEGMented:COUNt {n_records}")
            segmented = t.query(":ACQuire:MODE?").strip().upper().startswith("SEGM")
        if not segmented:
            t.write(":ACQuire:MODE RTIMe")
        times = np.linspace(start, stop, num)
        return _ScopeRecordSource(
            self,
            n,
            dataset,
            v.name,
            v.dtype,
            record_dim,
            time_dim,
            n_records,
            times,
            segmented=segmented,
            timeout_s=self.acquire_timeout_s,
            auto=auto,
        )

    def close(self) -> None:
        """Close the transport; idempotent."""
        self._t.close()


@dataclass(frozen=True)
class _Preamble:
    """The fields of `:WAVeform:PREamble?` a record needs."""

    points: int
    xinc: float
    xorig: float
    xref: float
    yinc: float
    yorig: float
    yref: float


def _error_code(reply: str) -> int:
    """The number of a `:SYSTem:ERRor?` reply ('+0,"No error"', '-113,"Undefined header"')."""
    return int(reply.split(",", 1)[0])


class _ScopeRecordSource:
    """The `Source` an `InfiniiVisionX.arm` returns: one `:SINGle` for every record (segmented) or
    per record, each waited for by polling the run state, never by a blocking `:DIGitize`; segments
    read in one transfer when the scope can."""

    def __init__(
        self,
        scope: InfiniiVisionX,
        channel: int,
        dataset: Dataset,
        variable: str,
        dtype: str,
        record_dim: str,
        time_dim: str,
        n_records: int,
        times: np.ndarray,
        *,
        segmented: bool = False,
        timeout_s: float = ACQUIRE_TIMEOUT_S,
        auto: bool = False,
    ) -> None:
        self._scope, self._t, self._n = scope, scope._t, channel
        self.dataset, self._variable, self._dtype = dataset, variable, dtype
        self._record_dim, self._time_dim, self._n_records = record_dim, time_dim, n_records
        self._times = times
        self._segmented, self._timeout_s, self._auto = segmented, timeout_s, auto

    def acquire(self) -> None:
        """`:SINGle`, then wait until the scope reports STOP (every segment caught, or the one
        record), polling `:RSTate?` (the HD3 has no `:OPERegister`, bench 2026-10-16); raises
        TimeoutError when the trigger(s) never come, after `:STOP`."""
        t = self._t
        t.query(":AER?")  # clear a stale arm event, so the next 1 is this acquisition's
        t.write(":SINGle")
        armed_by = time.monotonic() + ARM_TIMEOUT_S
        while int(float(t.query(":AER?"))) != 1:  # `:RSTate?` still reads the old state until then
            if time.monotonic() > armed_by:
                t.write(":STOP")
                raise TimeoutError(f"the scope did not arm within {ARM_TIMEOUT_S:g} s")
            time.sleep(POLL_S)
        deadline = time.monotonic() + self._timeout_s
        force_at = time.monotonic() + AUTO_FORCE_S
        while t.query(":RSTate?").strip().upper() != "STOP":
            if self._auto and time.monotonic() > force_at:  # AUTO sweep: free-run, as RUN would
                t.write(":TRIGger:FORCe")
                force_at = time.monotonic() + AUTO_FORCE_S
            if time.monotonic() > deadline:
                t.write(":STOP")
                raise TimeoutError(
                    f"the scope did not trigger within {self._timeout_s:g} s "
                    f"({self._n_records} record(s) armed{', segmented' if self._segmented else ''})"
                )
            time.sleep(POLL_S)

    def _preamble(self) -> _Preamble:
        pre = [p.strip() for p in self._t.query(":WAVeform:PREamble?").split(",")]
        if len(pre) != 10:
            raise ValueError(f"preamble has {len(pre)} fields, expected 10: {pre!r}")
        fmt = int(float(pre[0]))
        if fmt != 1:
            raise ValueError(f"preamble format {fmt} is not WORD (1)")
        return _Preamble(
            points=int(float(pre[2])),
            xinc=float(pre[4]),
            xorig=float(pre[5]),
            xref=float(pre[6]),
            yinc=float(pre[7]),
            yorig=float(pre[8]),
            yref=float(pre[9]),
        )

    def _resample(self, codes: np.ndarray, pre: _Preamble) -> np.ndarray:
        """Raw codes of one record → volts on the declared time grid."""
        if codes.size < 2 or not pre.xinc > 0:
            raise ValueError(f"capture too short to resample: {codes.size} points, xinc={pre.xinc}")
        volts = (codes.astype(np.float64) - pre.yref) * pre.yinc + pre.yorig
        captured = (np.arange(codes.size) - pre.xref) * pre.xinc + pre.xorig
        lo, hi = self._times[0], self._times[-1]
        if lo < captured[0] - pre.xinc or hi > captured[-1] + pre.xinc:
            raise ValueError(
                f"declared grid [{lo:.6g}, {hi:.6g}] s is outside the captured span "
                f"[{captured[0]:.6g}, {captured[-1]:.6g}] s; check the timebase on the instrument"
            )
        return np.interp(self._times, captured, volts)

    def record(self, index: int | None = None) -> np.ndarray:
        """Read the acquired record (segment `index`, 1-based, when segmented) in volts on the
        declared time grid."""
        if index is not None:
            self._t.write(f":ACQuire:SEGMented:INDex {index}")
        pre = self._preamble()
        return self._resample(self._t.query_block(":WAVeform:DATA?", "<i2"), pre)

    def segments(self) -> list[np.ndarray] | None:
        """Every segment of the acquisition in one transfer, each in volts on the declared grid; None
        when the scope refuses `:WAVeform:SEGMented:ALL` or the block is not `records` segments of
        the preamble's length, so the caller reads segment by segment. The first try decides for the
        rest of the session (`InfiniiVisionX.segments_in_one_transfer`)."""
        scope, t = self._scope, self._t
        if scope.segments_in_one_transfer is False:
            return None
        pre = self._preamble()  # one segment's: every segment shares its grid
        t.write("*CLS")  # so the next error read is this command's
        t.write(":WAVeform:SEGMented:ALL ON")
        if _error_code(t.query(":SYSTem:ERRor?")) != 0:
            scope.segments_in_one_transfer = False
            return None
        try:
            codes = t.query_block(":WAVeform:DATA?", "<i2")
        finally:
            t.write(":WAVeform:SEGMented:ALL OFF")
        ok = codes.size == self._n_records * pre.points
        if scope.segments_in_one_transfer is None:
            scope.segments_in_one_transfer = ok
        if not ok:
            return None
        return [self._resample(c, pre) for c in codes.reshape(self._n_records, pre.points)]

    def frames(self) -> Iterator[Frame]:
        n = self._times.size
        records = None
        if self._segmented:
            self.acquire()
            records = self.segments()
        for k in range(self._n_records):
            if records is not None:
                values = records[k]
            elif self._segmented:
                values = self.record(k + 1)
            else:
                self.acquire()
                values = self.record()
            yield Frame(
                DatasetChunk(
                    dataset_id=self.dataset.dataset_id,
                    seq=k,
                    region=(
                        IndexSlice(dim=self._record_dim, start=k, stop=k + 1),
                        IndexSlice(dim=self._time_dim, start=0, stop=n),
                    ),
                    variables=(self._variable,),
                    produced_at=datetime.now(UTC),
                    final=k == self._n_records - 1,
                ),
                {self._variable: values[None, :].astype(self._dtype)},
            )
