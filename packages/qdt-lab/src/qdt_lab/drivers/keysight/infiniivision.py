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

Each frame is one `:DIGitize` of the channel. The capture is converted to volts with the preamble and
resampled onto the declared `LinearCoordinate` (`np.interp`): the producer aligns, never the consumer
(ADR 0015). A declared grid reaching more than one sample interval outside the captured span raises.
"""

import re
from collections.abc import Iterator
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
        times = np.linspace(start, stop, num)
        return _ScopeRecordSource(
            t, n, dataset, v.name, v.dtype, record_dim, time_dim, n_records, times
        )

    def close(self) -> None:
        """Close the transport; idempotent."""
        self._t.close()


class _ScopeRecordSource:
    """The `Source` an `InfiniiVisionX.arm` returns: one `:DIGitize` per record."""

    def __init__(
        self,
        transport: ScpiTransport,
        channel: int,
        dataset: Dataset,
        variable: str,
        dtype: str,
        record_dim: str,
        time_dim: str,
        n_records: int,
        times: np.ndarray,
    ) -> None:
        self._t, self._n = transport, channel
        self.dataset, self._variable, self._dtype = dataset, variable, dtype
        self._record_dim, self._time_dim, self._n_records = record_dim, time_dim, n_records
        self._times = times

    def record(self) -> np.ndarray:
        """Acquire one record and return it in volts on the declared time grid."""
        t = self._t
        t.write(f":DIGitize CHANnel{self._n}")
        t.query("*OPC?")
        pre = [p.strip() for p in t.query(":WAVeform:PREamble?").split(",")]
        if len(pre) != 10:
            raise ValueError(f"preamble has {len(pre)} fields, expected 10: {pre!r}")
        fmt = int(float(pre[0]))
        if fmt != 1:
            raise ValueError(f"preamble format {fmt} is not WORD (1)")
        xinc, xorig, xref = float(pre[4]), float(pre[5]), float(pre[6])
        yinc, yorig, yref = float(pre[7]), float(pre[8]), float(pre[9])
        codes = t.query_block(":WAVeform:DATA?", "<i2")
        if codes.size < 2 or not xinc > 0:
            raise ValueError(f"capture too short to resample: {codes.size} points, xinc={xinc}")
        volts = (codes.astype(np.float64) - yref) * yinc + yorig
        captured = (np.arange(codes.size) - xref) * xinc + xorig
        lo, hi = self._times[0], self._times[-1]
        if lo < captured[0] - xinc or hi > captured[-1] + xinc:
            raise ValueError(
                f"declared grid [{lo:.6g}, {hi:.6g}] s is outside the captured span "
                f"[{captured[0]:.6g}, {captured[-1]:.6g}] s; check the timebase on the instrument"
            )
        return np.interp(self._times, captured, volts)

    def frames(self) -> Iterator[Frame]:
        n = self._times.size
        for k in range(self._n_records):
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
