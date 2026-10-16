"""OPX1000 (LF-FEM) driver: `WaveformSource`, `WaveformSense` and `Sequencer` over qm-qua (extra [opx]).

Patterned on what Probe 01 proved on this hardware (qm-qua 1.4.1, QOP 3.7.1; docs/probes/01-*): a
program is compiled once (`qm.compile`), queued (`add_to_queue`, waiting for "Running" before any
push), and given its integer parameters through an int input stream. Fixed-typed input streams do not
compile on that QOP, so every fractional parameter travels as a scaled int (the emitter's scheme,
ADR 0015/0018) and is turned back into a level inside the program.

Channels (vendor ids, `ChannelMap.channel`): `ao<p>` / `fem<f>/ao<p>` analog outputs, `ai<p>` /
`fem<f>/ai<p>` analog inputs and `do<p>` / `fem<f>/do<p>` digital outputs of an LF-FEM (default FEM
from settings["fem"], else 1). Outputs are `voltage` channels; inputs read volts. A digital output is
a marker line (ADR 0063, 0064): the stand wires it to another instrument's trigger input and names it
in that instrument's `settings["trigger_from"]`; the sequence plays a `MARKER_NS` pulse on it at a
shot capture (the scope's trigger) and at the top of a triggered axis (the DAC's list advance).

Sequencer programs (backend "qua"):
- an emitted stage (`QuaEmitter`): body = the PulseSequence JSON + symbol → parameter map + reductions.
  Steps and ramps play on *sticky* elements so a level holds until the next op on that channel, as the
  sequence vocabulary means (ADR 0018); ops are serialised in time with `align()`; every channel returns
  to 0 at the end of a shot. `measure` integrates its input over the op's duration; `difference` and
  `mean`/`sum` reductions are applied to the per-shot values as they are fetched (ADR 0037's per-shot
  semantics). `drive` is not supported on an LF-FEM (ValueError at compile). A `capture` plays the
  scope's marker (if the body names a line for it; otherwise the scope triggers itself, ADR 0063)
  and the shot waits out the window. A triggered axis (body `triggered`) is the outermost loop: a
  marker on each of its lines, a wait of the settle, then the inner loops.
- the conformance program (`{"kind": "flat_index"}`): Probe 01's flat loop index.

Calibration constants, measured on the bench (Probe 02, docs/probes/02-opx-input-calibration.md,
2026-10-14; ADR 0044): `INTEGRATION_TO_VOLTS` (integrated value → mean volts per ns of window),
`RAW_ADC_TO_VOLTS` (raw ADC sample → volts) and `TIME_OF_FLIGHT_NS`. They live here, once.
"""

import json
import math
import re
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from qdt_schemas.activity import SequencerProgram
from qdt_schemas.data import Dataset, DatasetChunk, IndexSlice, LinearCoordinate
from qdt_schemas.pulse import Affine, PulseSequence, Symbol
from qdt_schemas.stand import ChannelMap, InstrumentConfig

from ...stream.frame import Frame

CONTROLLER = "con1"
CLOCK_NS = 4
MIN_PULSE_NS = 16
MARKER_NS = 400
"""Length of the marker pulse on a digital output: 3.27 V into 1 MΩ, 1.93 V into 50 Ω, 401 ns on the
bench (Probe 05, 2026-10-16); it plays on its own element, so the analog timeline is not delayed by
it unless a capture window is shorter than it."""
MARKER_TO_ANALOG_NS = 85
"""A marker's rising edge leads the analog edge played in the same shot by this much at the
connectors (Probe 05: 5 of 5 repeats). Recorded, not applied (ADR 0065): a shot capture's record
starts at the marker; the op's analog effect lands this much later."""
SAMPLE_RATE = 1e9  # LF-FEM native rate assumed for arbitrary waveforms and raw ADC traces
TIME_OF_FLIGHT_NS = 180
"""Readout latency, so a record starts on the edge of a pulse played at the same time (Probe 02: the
edge lands at 147 ns with 28 configured, at 4 ns with 176; a multiple of 4, and QOP 3.7 rejects < 28)."""
RAW_ADC_TO_VOLTS = -2.820e-4
"""volts = raw ADC sample * this. Measured, Probe 02 (ao1 -> ai1 loopback against a scope-verified
pulse, five amplitudes, fit residual < 0.3 mV): the LF-FEM input reads inverted relative to its output,
and the scale is 1.155 x 2**-12, not the 2**-12 assumed before the bench."""
INTEGRATION_TO_VOLTS = -4731.0
"""mean volts = integrated value * this / window_ns (constant unit weights). Measured, Probe 02, on the
same shots as RAW_ADC_TO_VOLTS; the two agree to 0.5 %. Input offset at 0 V in: -1.7 mV (not applied)."""
OUTPUT_RANGE_V = {"direct": 0.5, "amplified": 2.5}
_PORT = re.compile(r"^(?:fem(\d+)[/_:])?(ao|ai|do)(\d+)$")


def _element(channel: str) -> str:
    return "el_" + re.sub(r"\W", "_", channel)


def _wave_element(channel: str) -> str:
    """The non-sticky twin of `_element(channel)`, for looped waveform playback."""
    return _element(channel) + "_wave"


def _trigger_element(channel: str) -> str:
    """The digital-only element of a marker line (a `do<p>` port)."""
    return "trig_" + re.sub(r"\W", "_", channel)


@dataclass(frozen=True)
class _Port:
    fem: int
    kind: str  # "ao" | "ai" | "do"
    port: int


@dataclass
class CompiledQuaProgram:
    """`Sequencer.compile`'s handle: the program, its compiled id, and what fetching needs."""

    program: SequencerProgram
    program_id: object
    epoch: int
    plan: dict = field(default_factory=dict)


class Opx1000:
    """One OPX1000 (LF-FEM ports) behind WaveformSource, WaveformSense and Sequencer."""

    def __init__(self, qmm, channels: tuple[ChannelMap, ...] = (), settings: Mapping | None = None):
        self._qmm = qmm
        self._settings = dict(settings or {})
        self._fem = int(self._settings.get("fem", 1))
        self._mode = str(self._settings.get("output_mode", "direct"))
        if self._mode not in OUTPUT_RANGE_V:
            raise ValueError(f"output_mode must be one of {sorted(OUTPUT_RANGE_V)}")
        self._ports: dict[str, _Port] = {}
        self._logical: dict[str, str] = {}  # a channel's logical name -> its vendor id
        for c in channels:
            p = self._port(c.channel)
            if c.quantity != "voltage":
                raise ValueError(f"OPX channel {c.channel!r} carries volts, not {c.quantity}")
            self._ports[c.channel] = p
            self._logical[c.logical] = c.channel
        self._readout_lengths: set[int] = set()
        self._arbitrary: dict[str, list[float]] = {}
        self._qm = None
        self._epoch = 0
        self._jobs: dict[str, object] = {}

    @classmethod
    def from_config(
        cls, instrument: InstrumentConfig, channels: tuple[ChannelMap, ...]
    ) -> "Opx1000":
        """`BackendFactory` (ADR 0021): settings["address"] is the QM host; optional "port",
        "cluster_name", "fem", "output_mode" ('direct' | 'amplified')."""
        s = instrument.settings
        if not s.get("address"):
            raise ValueError(f"instrument {instrument.id!r} has no settings['address']")
        from qm import QuantumMachinesManager

        kw = {"host": str(s["address"])}
        if s.get("port"):
            kw["port"] = int(s["port"])
        if s.get("cluster_name"):
            kw["cluster_name"] = str(s["cluster_name"])
        return cls(QuantumMachinesManager(**kw), channels, s)

    # --- ports and config ----------------------------------------------------------------------

    def _port(self, channel: str) -> _Port:
        m = _PORT.match(channel.lower())
        if not m:
            raise ValueError(
                f"OPX channel {channel!r} is not 'ao<p>', 'ai<p>', 'do<p>' or 'fem<f>/ao<p>'"
            )
        fem, kind, port = m.groups()
        p = _Port(int(fem) if fem else self._fem, kind, int(port))
        if not 1 <= p.port <= (2 if kind == "ai" else 8):
            raise ValueError(f"OPX channel {channel!r}: LF-FEM has ao1..8, ai1..2 and do1..8")
        return p

    def _vendor(self, channel: str) -> str:
        """The vendor id for `channel`, which may be a declared logical name (the compiler hands the
        driver sequences in the stand's logical names) or already a vendor id."""
        return self._logical.get(channel, channel)

    def _known(self, channel: str, kind: str) -> _Port:
        channel = self._vendor(channel)
        p = self._ports.get(channel) or self._port(channel)
        if p.kind != kind:
            raise ValueError(f"OPX channel {channel!r} is an {p.kind}, not an {kind}")
        self._ports.setdefault(channel, p)
        return p

    @property
    def amplitude_ref(self) -> float:
        """Amplitude of the constant pulse that `amp()` scales: half the output range."""
        return OUTPUT_RANGE_V[self._mode] / 2

    def config(self) -> dict:
        """The QM configuration for the channels in use (rebuilt when readout lengths or arbitrary
        waveforms are added)."""
        outputs = {p for p in self._ports.values() if p.kind == "ao"}
        inputs = {p for p in self._ports.values() if p.kind == "ai"}
        markers = {p for p in self._ports.values() if p.kind == "do"}
        drive = (
            min(outputs, key=lambda p: (p.fem, p.port)) if outputs else _Port(self._fem, "ao", 1)
        )
        fems: dict[int, dict] = {}

        def fem(f: int) -> dict:
            return fems.setdefault(
                f,
                {"type": "LF", "analog_outputs": {}, "analog_inputs": {}, "digital_outputs": {}},
            )

        for p in outputs | {drive}:
            fem(p.fem)["analog_outputs"][p.port] = {"offset": 0.0, "output_mode": self._mode}
        for p in inputs:
            fem(p.fem)["analog_inputs"][p.port] = {"offset": 0.0}
        for p in markers:
            fem(p.fem)["digital_outputs"][p.port] = {}
        a = self.amplitude_ref
        elements, pulses = {}, {}
        waveforms = {
            "const_wf": {"type": "constant", "sample": a},
            "zero_wf": {"type": "constant", "sample": 0.0},
        }
        weights = {}
        pulses["const"] = {
            "operation": "control",
            "length": MIN_PULSE_NS,
            "waveforms": {"single": "const_wf"},
        }
        if markers:  # ADR 0063/0064: a digital-only pulse on a digital-only element per line
            pulses["marker"] = {"operation": "control", "length": MARKER_NS, "digital_marker": "ON"}
        for ch, p in self._ports.items():
            if p.kind == "do":
                elements[_trigger_element(ch)] = {
                    "digitalInputs": {
                        "marker": {"port": (CONTROLLER, p.fem, p.port), "delay": 0, "buffer": 0}
                    },
                    "operations": {"marker": "marker"},
                }
            if p.kind != "ao":
                continue
            ops = {"const": "const"}
            if ch in self._arbitrary:
                wf, pulse = f"arb_wf_{_element(ch)}", f"arb_{_element(ch)}"
                waveforms[wf] = {"type": "arbitrary", "samples": self._arbitrary[ch]}
                pulses[pulse] = {
                    "operation": "control",
                    "length": len(self._arbitrary[ch]),
                    "waveforms": {"single": wf},
                }
                ops["arb"] = pulse
            elements[_element(ch)] = {
                "singleInput": {"port": (CONTROLLER, p.fem, p.port)},
                "intermediate_frequency": 0,
                "operations": ops,
                "sticky": {"analog": True, "digital": False, "duration": CLOCK_NS},
            }
            # `play` loops a waveform on a non-sticky twin of the element: a sticky element adds each
            # repetition onto the level it holds, so a loop whose last sample is not 0 walks to the
            # rail (bench, 2026-10-14: a 20 kHz sine railed within a second)
            elements[_wave_element(ch)] = {
                "singleInput": {"port": (CONTROLLER, p.fem, p.port)},
                "intermediate_frequency": 0,
                "operations": ops,
            }
        for ch, p in self._ports.items():
            if p.kind != "ai":
                continue
            ops = {}
            for n in sorted(self._readout_lengths):
                pulses[f"readout_{n}"] = {
                    "operation": "measurement",
                    "length": n,
                    "waveforms": {"single": "zero_wf"},
                    "integration_weights": {"const": f"w_{n}"},
                    "digital_marker": "ON",
                }
                weights[f"w_{n}"] = {"cosine": [(1.0, n)], "sine": [(0.0, n)]}
                ops[f"readout_{n}"] = f"readout_{n}"
            elements[_element(ch)] = {
                "singleInput": {"port": (CONTROLLER, drive.fem, drive.port)},
                "intermediate_frequency": 0,
                "operations": ops,
                "outputs": {"out1": (CONTROLLER, p.fem, p.port)},
                "time_of_flight": TIME_OF_FLIGHT_NS,
                "smearing": 0,
            }
        return {
            "version": 1,
            "controllers": {CONTROLLER: {"type": "opx1000", "fems": fems}},
            "elements": elements,
            "pulses": pulses,
            "waveforms": waveforms,
            "digital_waveforms": {"ON": {"samples": [(1, 0)]}},
            "integration_weights": weights,
        }

    def _open(self):
        """Open (or reopen, after the config grew) the quantum machine; bumps the compile epoch."""
        self._qm = self._qmm.open_qm(self.config(), close_other_machines=True)
        self._epoch += 1
        return self._qm

    def _ensure(self, readout_lengths: set[int] = frozenset(), arbitrary: dict | None = None):
        grew = not set(readout_lengths) <= self._readout_lengths or bool(arbitrary)
        self._readout_lengths |= set(readout_lengths)
        if arbitrary:
            self._arbitrary.update(arbitrary)
        if self._qm is None or grew:
            self._open()
        return self._qm

    def close(self) -> None:
        for job in self._jobs.values():
            _halt(job)
        self._jobs.clear()
        if self._qm is not None:
            self._qm.close()
            self._qm = None

    # --- WaveformSource ------------------------------------------------------------------------

    def play(self, channel: str, samples: np.ndarray, sample_rate: float) -> None:
        """Play `samples` (volts) repeatedly on an analog output until `stop`. Resampled to the
        LF-FEM rate; padded to whole clock cycles."""
        a = np.asarray(samples, dtype=np.float64)
        if a.ndim != 1 or a.size == 0:
            raise ValueError(f"waveform must be a non-empty 1-D array, got shape {a.shape}")
        if not sample_rate > 0:
            raise ValueError(f"sample_rate must be positive, got {sample_rate}")
        limit = OUTPUT_RANGE_V[self._mode]
        if np.max(np.abs(a)) > limit:
            raise ValueError(f"waveform exceeds the ±{limit} V output range ({self._mode} mode)")
        channel = self._vendor(channel)
        self._known(channel, "ao")
        n = max(MIN_PULSE_NS, math.ceil(a.size * SAMPLE_RATE / sample_rate / CLOCK_NS) * CLOCK_NS)
        t_out = np.arange(n) / SAMPLE_RATE
        t_in = np.arange(a.size) / sample_rate
        resampled = np.interp(t_out, t_in, a, right=a[-1])
        self.stop(channel)
        qm = self._ensure(arbitrary={channel: [float(x) for x in resampled]})
        from qm import qua

        el = _wave_element(channel)
        with qua.program() as prog, qua.infinite_loop_():
            qua.play("arb", el)
        self._jobs[channel] = qm.execute(prog)

    def stop(self, channel: str) -> None:
        job = self._jobs.pop(self._vendor(channel), None)
        if job is not None:
            _halt(job)

    # --- WaveformSense -------------------------------------------------------------------------

    def arm(self, channel: str, dataset: Dataset, variable: str) -> "_RecordSource":
        """Raw ADC records on an analog input, resampled onto the declared time grid (ADR 0015).
        The record starts when the readout window opens (after the time of flight)."""
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
        times = np.linspace(axis[0].start, axis[0].stop, axis[0].num)
        if times[0] < 0:
            raise ValueError(
                "the declared time axis starts before the readout window opens (t < 0)"
            )
        n_records = next(d.size for d in dataset.dims if d.name == record_dim) or int(
            self._settings.get("max_records", 8)
        )
        channel = self._vendor(channel)
        self._known(channel, "ai")
        window = max(MIN_PULSE_NS, math.ceil((times[-1] * SAMPLE_RATE + 1) / CLOCK_NS) * CLOCK_NS)
        return _RecordSource(
            self, channel, dataset, v.name, v.dtype, record_dim, time_dim, n_records, times, window
        )

    # --- Sequencer -----------------------------------------------------------------------------

    def compile(self, program: SequencerProgram) -> CompiledQuaProgram:
        if program.backend != "qua":
            raise ValueError(f"the OPX runs backend 'qua' programs, not {program.backend!r}")
        body = json.loads(program.body) if program.body.lstrip().startswith("{") else {}
        if body.get("kind") == "flat_index":
            qm = self._ensure()
            prog, plan = flat_index_program(program)
        elif "sequence" in body:
            sequence = PulseSequence.model_validate(
                _vendor_channels(body["sequence"], self._logical)
            )
            scopes = {op.channel for op in sequence.expand() if op.op == "capture"}
            for ch in sequence.channels():
                if ch in scopes:  # the scope is another instrument's; its marker line is ours
                    continue
                self._known(
                    ch,
                    "ai"
                    if any(op.op == "measure" and op.channel == ch for op in sequence.expand())
                    else "ao",
                )
            body = dict(body)
            body["lines"] = {
                scope: self._vendor(line) for scope, line in body.get("lines", {}).items()
            }
            for line in body["lines"].values():
                self._known(line, "do")
            if body.get("triggered"):
                body["triggered"] = dict(body["triggered"])
                body["triggered"]["lines"] = [
                    self._vendor(line) for line in body["triggered"].get("lines", [])
                ]
                for line in body["triggered"]["lines"]:
                    self._known(line, "do")
            lengths = {
                _cycles_ns(op.duration, "measure") for op in sequence.expand() if op.op == "measure"
            }
            qm = self._ensure(lengths)
            prog, plan = sequence_program(program, sequence, body, self.amplitude_ref)
        else:
            raise ValueError('a \'qua\' program body is an emitted stage or {"kind": "flat_index"}')
        return CompiledQuaProgram(program, qm.compile(prog), self._epoch, plan | {"qua": prog})

    def run(
        self, compiled: CompiledQuaProgram, parameters: Mapping[str, int], dataset: Dataset
    ) -> "_RunSource":
        compiled.program.check_run(parameters, dataset)
        if (
            compiled.epoch != self._epoch
        ):  # the machine was reopened with a larger config: recompile
            compiled.program_id, compiled.epoch = (
                self._qm.compile(compiled.plan["qua"]),
                self._epoch,
            )
        return _RunSource(self, compiled, dict(parameters), dataset)

    def _submit(self, compiled: CompiledQuaProgram, values: list[int]):
        qm = self._qm
        if hasattr(qm, "add_to_queue"):  # API v2: pushes must wait for "Running" (Probe 01)
            job = qm.add_to_queue(compiled.program_id)
            job.wait_until("Running", timeout=30)
        else:
            job = qm.queue.add_compiled(compiled.program_id).wait_for_execution()
        if values:
            job.push_to_input_stream("params", values)
        return job


def _halt(job) -> None:
    import contextlib

    with contextlib.suppress(Exception):  # a finished job may refuse; nothing to stop then
        job.halt()


def _flat(a) -> np.ndarray:
    a = np.asarray(a)
    if a.dtype.names:  # structured result in some qm-qua versions
        a = a["value"]
    return a.reshape(-1)


def _cycles_ns(duration, what: str) -> int:
    """A literal duration in ns, validated for the OPX clock (whole cycles, >= 16 ns)."""
    if isinstance(duration, Symbol):
        raise ValueError(f"{what}: a symbol duration is not supported here")  # noqa: TRY004
    d = int(duration)
    if d < MIN_PULSE_NS or d % CLOCK_NS:
        raise ValueError(
            f"{what}: {d} ns must be a multiple of {CLOCK_NS} ns and >= {MIN_PULSE_NS} ns"
        )
    return d


# --- QUA program builders (pure: need qm-qua, not a server) --------------------------------------


def _in_stream(qua, n: int):
    """Probe 01's int input stream, new signature first."""
    extra = {"size": n} if n > 1 else {}
    try:
        return qua.declare_input_stream("client", stream_id="params", dtype=int, **extra)
    except TypeError:
        return qua.declare_input_stream(int, name="params", **extra)


def _param(params, n: int, i: int):
    return params[i] if n > 1 else params


def flat_index_program(program: SequencerProgram):
    """Probe 01's conformance program: result 'data'[i, j] = i * n_points + j."""
    from qm import qua

    names = [p.name for p in program.parameters]
    for need in ("n_lines", "n_points"):
        if need not in names:
            raise ValueError(f"flat_index needs parameter {need!r}")
    n = len(names)
    with qua.program() as prog:
        params = _in_stream(qua, n)
        i, j, v = qua.declare(int), qua.declare(int), qua.declare(int)
        st = qua.declare_output_stream()
        qua.advance_input_stream(params)
        n_lines, n_points = (
            _param(params, n, names.index("n_lines")),
            _param(params, n, names.index("n_points")),
        )
        with qua.for_(i, 0, i < n_lines, i + 1), qua.for_(j, 0, j < n_points, j + 1):
            qua.assign(v, i * n_points + j)
            qua.save(v, st)
        with qua.stream_processing():
            st.save_all("data")
    return prog, {"kind": "flat_index", "streams": {"data": "data"}}


def _vendor_channels(sequence: object, logical: Mapping[str, str]) -> object:
    """The sequence JSON with every `channel` that is a declared logical name replaced by its vendor
    id, so elements and levels are keyed the way `config()` keys them."""
    if isinstance(sequence, dict):
        return {
            k: (
                logical.get(v, v)
                if k == "channel" and isinstance(v, str)
                else _vendor_channels(v, logical)
            )
            for k, v in sequence.items()
        }
    if isinstance(sequence, list):
        return [_vendor_channels(v, logical) for v in sequence]
    return sequence


def sequence_program(program: SequencerProgram, sequence: PulseSequence, body: dict, a_ref: float):
    """An emitted stage as one QUA program with its parameters in an int input stream.

    Loops: stage axes (outer → inner), then shots. Per shot: the expanded sequence, every op aligned
    after the previous one; sticky levels tracked per channel so a step plays the change; all channels
    back to 0 at the end of the shot. Each measure saves its raw integrated value per shot to a stream;
    the host converts, differences and reduces (see `_RunSource`)."""
    from qm import qua

    names = [p.name for p in program.parameters]
    scales = {p.name: p.scale for p in program.parameters}
    n = len(names)
    symbols: dict = body["symbols"]
    lines: dict = body.get("lines", {})  # a shot capture's scope channel -> its marker line
    triggered: dict | None = body.get("triggered")  # ADR 0064: the axis the markers advance
    ops = sequence.expand()
    scopes = {o.channel for o in ops if o.op == "capture"}
    outputs = [
        ch
        for ch in sequence.channels()
        if ch not in scopes and not any(o.op == "measure" and o.channel == ch for o in ops)
    ]
    axes = [
        p.name for p in program.parameters if p.name.startswith("n_")
    ]  # n_<axis>, outer → inner
    measures = [o for o in ops if o.op == "measure"]
    if any(o.op == "drive" for o in ops):
        raise ValueError("drive needs an IF element; not supported on the LF-FEM stage")
    with qua.program() as prog:
        params = _in_stream(qua, n)
        qua.advance_input_stream(params)
        p = {name: _param(params, n, k) for k, name in enumerate(names)}
        idx = {a: qua.declare(int) for a in axes}
        shot = qua.declare(int)
        level = {ch: qua.declare(qua.fixed) for ch in outputs}
        target = qua.declare(qua.fixed)
        units = sequence.symbols()
        # level-like symbols live as fixed-point volts; duration symbols (ns) stay ints (fixed tops out at ±8)
        sym = {name: qua.declare(qua.fixed) for name in symbols if units[name] != "ns"}
        integ = {o.result: qua.declare(qua.fixed) for o in measures}
        streams = {o.result: qua.declare_output_stream() for o in measures}

        every = [
            _element(ch) for ch in sequence.channels() if ch not in scopes
        ]  # a wait holds every analog element; marker lines run their own timeline

        def value(v):
            """A QUA expression (or float) for a level-like Value, in volts."""
            if isinstance(v, Symbol):
                return sym[v.name]
            if isinstance(v, Affine):
                return sym[v.symbol.name] * v.scale + v.offset
            return float(v)

        def duration_cycles(d):
            if isinstance(
                d, Symbol
            ):  # ns, unit scale 1: a constant, a stepped value, or swept in the stage
                spec = symbols[d.name]
                if "axis" in spec:
                    return (p[spec["start"]] + idx[spec["axis"]] * p[spec["step"]]) >> 2
                return p[spec["value"]] >> 2
            return _cycles_ns(d, "duration") // CLOCK_NS

        def body_of_shot():
            for op in ops:
                if op.op in ("step", "ramp"):
                    el = _element(op.channel)
                    if op.op == "ramp":
                        # jump to the ramp's start, then ramp to its stop over the duration
                        qua.assign(target, value(op.start))
                        qua.play(
                            "const" * qua.amp((target - level[op.channel]) * (1 / a_ref)),
                            el,
                            duration=MIN_PULSE_NS // CLOCK_NS,
                        )
                        qua.assign(level[op.channel], target)
                        qua.assign(target, value(op.stop))
                        cycles = duration_cycles(op.duration)
                        qua.play(
                            qua.ramp((target - level[op.channel]) / (cycles * CLOCK_NS)),
                            el,
                            duration=cycles,
                        )
                        qua.assign(level[op.channel], target)
                    else:
                        qua.assign(target, value(op.level))
                        qua.play(
                            "const" * qua.amp((target - level[op.channel]) * (1 / a_ref)),
                            el,
                            duration=duration_cycles(op.duration),
                        )
                        qua.assign(level[op.channel], target)
                elif op.op == "wait":
                    qua.wait(duration_cycles(op.duration), *every)
                elif op.op == "capture":
                    # ADR 0063: the marker triggers the scope here; the shot waits out the window
                    # (rounded up to the clock; the window itself is the scope's)
                    line = lines.get(op.channel)
                    if line is not None:
                        qua.play("marker", _trigger_element(line))
                    cycles = max(MIN_PULSE_NS, math.ceil(int(op.duration) / CLOCK_NS) * CLOCK_NS)
                    qua.wait(cycles // CLOCK_NS, *every)
                elif op.op == "measure":
                    d = _cycles_ns(op.duration, "measure")
                    qua.measure(
                        f"readout_{d}",
                        _element(op.channel),
                        None,
                        qua.integration.full("const", integ[op.result]),
                    )
                    qua.save(integ[op.result], streams[op.result])
                qua.align()
            for ch in outputs:
                qua.ramp_to_zero(_element(ch), 1)
                qua.assign(level[ch], 0.0)
            qua.align()

        def symbol_values():
            for name, spec in symbols.items():
                if name not in sym:  # a duration symbol: read where it is used
                    continue
                if "axis" in spec:  # swept in the stage: (start + i * step) in scaled ints
                    raw = p[spec["start"]] + idx[spec["axis"]] * p[spec["step"]]
                    qua.assign(sym[name], qua.Cast.mul_fixed_by_int(scales[spec["start"]], raw))
                else:  # a constant or the stepped axis's value, both scaled ints
                    qua.assign(
                        sym[name],
                        qua.Cast.mul_fixed_by_int(scales[spec["value"]], p[spec["value"]]),
                    )

        def loops(k: int):
            if k == len(axes):
                symbol_values()
                with qua.for_(shot, 0, shot < p["shots"], shot + 1):
                    body_of_shot()
                return
            a = axes[k]
            with qua.for_(idx[a], 0, idx[a] < p[a], idx[a] + 1):
                if triggered is not None and a == f"n_{triggered['axis']}":
                    # ADR 0064: advance the DAC's list, settle, then the inner loops and shots
                    for line in triggered["lines"]:
                        qua.play("marker", _trigger_element(line))
                    settle_cycles = math.ceil(int(triggered.get("settle_ns", 0)) / CLOCK_NS)
                    if settle_cycles > 0:
                        qua.wait(max(settle_cycles, MIN_PULSE_NS // CLOCK_NS), *every)
                    qua.align()
                loops(k + 1)

        for ch in outputs:
            qua.assign(level[ch], 0.0)
        loops(0)
        with qua.stream_processing():
            for r, st in streams.items():
                st.save_all(r)
    plan = {
        "kind": "sequence",
        "measures": {o.result: _cycles_ns(o.duration, "measure") for o in measures},
        "differences": [(o.result, o.a, o.b) for o in ops if o.op == "difference"],
        "reduce": dict(body.get("reduce", {})),
    }
    return prog, plan


# --- sources -------------------------------------------------------------------------------------


class _RunSource:
    """The `Source` an `Opx1000.run` returns: submits on first iteration, fetches when done, one
    frame per result (whole stage at once; the executor runs one stage per stepped point)."""

    def __init__(
        self,
        opx: Opx1000,
        compiled: CompiledQuaProgram,
        parameters: dict[str, int],
        dataset: Dataset,
    ):
        self._opx, self._compiled, self._params, self.dataset = opx, compiled, parameters, dataset

    def results(self, fetched: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Fetched per-shot values → declared result arrays (pure; used by tests with fake fetches)."""
        program, plan = self._compiled.program, self._compiled.plan
        if plan["kind"] == "flat_index":
            shape = program.result_shape("data", self._params)
            return {"data": _flat(fetched["data"]).astype(np.int64).reshape(shape)}
        shots = int(self._params.get("shots", 1))
        per_shot = {
            r: _flat(fetched[r]).astype(np.float64) * INTEGRATION_TO_VOLTS / d
            for r, d in plan["measures"].items()
        }
        for r, a, b in plan["differences"]:
            per_shot[r] = per_shot[a] - per_shot[b]
        out = {}
        for res in program.results:
            dims = [self._params[d] for d in res.dims if d != "shots"]
            values = per_shot[res.name].reshape(*dims, shots)
            how = plan["reduce"].get(res.name, "keep")
            if how == "mean":
                values = values.mean(axis=-1)
            elif how == "sum":
                values = values.sum(axis=-1)
            elif shots == 1:
                values = values[..., 0]
            out[res.name] = values.astype(res.dtype)
        return out

    def frames(self) -> Iterator[Frame]:
        program = self._compiled.program
        values = [int(self._params[p.name]) for p in program.parameters]
        job = self._opx._submit(self._compiled, values)
        handles = job.result_handles
        handles.wait_for_all_values()
        names = (
            ["data"]
            if self._compiled.plan["kind"] == "flat_index"
            else list(self._compiled.plan["measures"])
        )
        fetched = {r: handles.get(r).fetch_all() for r in names}
        arrays = self.results(fetched)
        variables = {v.name: v for v in self.dataset.data_vars}
        results = list(program.results)
        for seq, res in enumerate(results):
            a = arrays[res.name]
            yield Frame(
                DatasetChunk(
                    dataset_id=self.dataset.dataset_id,
                    seq=seq,
                    region=tuple(
                        IndexSlice(dim=d, start=0, stop=s)
                        for d, s in zip(variables[res.name].dims, a.shape, strict=True)
                    ),
                    variables=(res.name,),
                    produced_at=datetime.now(UTC),
                    final=seq == len(results) - 1,
                ),
                {res.name: a},
            )


class _RecordSource:
    """The `Source` an `Opx1000.arm` returns: one raw ADC record per frame, on the declared grid."""

    def __init__(
        self, opx, channel, dataset, variable, dtype, record_dim, time_dim, n_records, times, window
    ):
        self._opx, self._channel, self.dataset = opx, channel, dataset
        self._variable, self._dtype = variable, dtype
        self._record_dim, self._time_dim, self._n_records = record_dim, time_dim, n_records
        self._times, self._window = times, window

    def frames(self) -> Iterator[Frame]:
        from qm import qua

        qm = self._opx._ensure({self._window})
        el = _element(self._channel)
        p = self._opx._ports[self._channel]
        with qua.program() as prog:
            k = qua.declare(int)
            adc = (
                qua.declare_output_stream(adc_trace=True)
                if _takes_adc_flag(qua)
                else qua.declare_stream(adc_trace=True)
            )
            with qua.for_(k, 0, k < self._n_records, k + 1):
                qua.measure(f"readout_{self._window}", el, adc)
                qua.wait(250)
            with qua.stream_processing():
                (adc.input1() if p.port == 1 else adc.input2()).save_all("adc")
        job = qm.execute(prog)
        handle = job.result_handles.get("adc")
        t = np.arange(self._window) / SAMPLE_RATE
        for kk in range(self._n_records):
            handle.wait_for_values(kk + 1)
            raw = np.asarray(handle.fetch(kk))
            record = _flat(raw).astype(np.float64) * RAW_ADC_TO_VOLTS
            values = np.interp(self._times, t[: record.size], record)
            yield Frame(
                DatasetChunk(
                    dataset_id=self.dataset.dataset_id,
                    seq=kk,
                    region=(
                        IndexSlice(dim=self._record_dim, start=kk, stop=kk + 1),
                        IndexSlice(dim=self._time_dim, start=0, stop=self._times.size),
                    ),
                    variables=(self._variable,),
                    produced_at=datetime.now(UTC),
                    final=kk == self._n_records - 1,
                ),
                {self._variable: values[None, :].astype(self._dtype)},
            )


def _takes_adc_flag(qua) -> bool:
    import inspect

    try:
        return "adc_trace" in inspect.signature(qua.declare_output_stream).parameters
    except (TypeError, ValueError):
        return False


def new_run_id() -> str:
    return uuid.uuid4().hex
