"""L2-6: two OPX lines in one shot, recorded together by the scope (`docs/BENCH.md` § L2-6; ADR 0070).

Wiring: LF-FEM ao1 (`P2_pulse`) → scope ch1 and ao2 (`P1_pulse`) → scope ch3, both DC **50 Ω** (direct
mode gives the programmed level into 50 Ω, Probe 02; into 1 MΩ it would double and clip at 0.1 V/div).
No marker line: the scope triggers itself on ch1's rising edge, so t = 0 is that edge and ch3's edge
sits one step later. The shot: `step(P2_pulse, 0.25 V, 1 µs); step(P1_pulse, 0.25 V, 16 ns);
capture(scope1, 4 µs); capture(scope3, 4 µs); wait(50 ms)`, three shots: one segmented acquisition
serves both channels per shot (ADR 0070), each record its channel's.

This row owns its stand: the OPX and the scope from the addresses (`QDT_OPX_ADDRESS`,
`QDT_SCOPE_ADDRESS`), the scope without a trigger line, and `compile_sweep` + `Executor` in-process, as
the L1 rows run (no server, so stop `qdt-server --stand` first).

Oracle: both plateaus at 0.25 V within the scope's accuracy at 0.1 V/div plus the 50 Ω input's 1.5 %
(L1's OPX row); ch3's half-amplitude crossing 1000 ns after ch1's within two grid steps plus one OPX
clock, on every shot. The skew between the two ports is what the row measures; its value goes in
BENCH.md. No site tolerance is written here (rule 7).
"""

import os

import numpy as np
from conftest import _instrument, _retry
from scope_accuracy import ScopeChannel, dc_measurement_tolerance

from qdt_lab.experiment import Executor, QuaEmitter, compile_sweep
from qdt_lab.stream import assemble
from qdt_schemas.activity import SequencerStage, SweepDefinition
from qdt_schemas.pulse import Capture, PulseSequence, Step, Wait
from qdt_schemas.stand import ChannelMap, StandConfig

LEVEL_V = 0.25
FIRST_NS = 1000
"""The first line holds this long before the second steps: the programmed skew."""
WINDOW_NS, POINTS = 4000, 400
SHOTS = 3
SHOT_WAIT_NS = 50_000_000
TRIGGER_LEVEL_V = 0.1
VOLTS_PER_DIV = 0.1
GRID_NS = WINDOW_NS / (POINTS - 1)
SKEW_TOLERANCE_NS = 2 * GRID_NS + 4
PLATEAU_TOLERANCE_V = dc_measurement_tolerance(
    ScopeChannel(number=1, volts_per_div=VOLTS_PER_DIV)
) + (0.015 * LEVEL_V)


def two_line_stand() -> tuple[StandConfig, dict]:
    """The OPX and the scope from the addresses; skips without them. Returns the stand and the backends."""
    from qdt_lab.drivers.keysight.infiniivision import InfiniiVisionX
    from qdt_lab.drivers.qm.opx1000 import Opx1000

    opx = _instrument(
        "opx",
        "qua",
        ("waveform_source", "waveform_sense", "sequencer"),
        "QDT_OPX_ADDRESS",
        fem=int(os.environ.get("QDT_OPX_FEM", "1")),
        output_mode="direct",
    )
    scope = _instrument("scope0", "infiniivision", ("waveform_sense",), "QDT_SCOPE_ADDRESS")
    stand = StandConfig(
        stand_id="two-lines",
        instruments=(opx, scope),
        channels=(
            ChannelMap(logical="P2_pulse", instrument="opx", channel="ao1", quantity="voltage"),
            ChannelMap(logical="P1_pulse", instrument="opx", channel="ao2", quantity="voltage"),
            ChannelMap(logical="scope1", instrument="scope0", channel="1", quantity="voltage"),
            ChannelMap(logical="scope3", instrument="scope0", channel="3", quantity="voltage"),
        ),
    )
    backends = {
        "opx": Opx1000.from_config(opx, stand.instrument_channels("opx")),
        "scope0": _retry(
            lambda: InfiniiVisionX.from_config(scope, stand.instrument_channels("scope0"))
        ),
    }
    return stand, backends


def crossing_ns(t_ns: np.ndarray, trace: np.ndarray, level: float) -> float:
    """Time of the first upward crossing of `level`, interpolated between the samples around it."""
    above = np.flatnonzero(trace >= level)
    if above.size == 0 or above[0] == 0:
        raise AssertionError(f"no upward crossing of {level:.3f} V inside the window")
    k = above[0]
    frac = (level - trace[k - 1]) / (trace[k] - trace[k - 1])
    return float(t_ns[k - 1] + frac * (t_ns[k] - t_ns[k - 1]))


def test_l2_6_two_lines_in_one_shot_are_recorded_together_and_step_a_microsecond_apart(
    closing, scope_front_panel
):
    stand, backends = two_line_stand()
    closing.extend(backends.values())
    scope_front_panel(
        1, VOLTS_PER_DIV, 0.0, "DC", "FIFTy", trigger_level_v=TRIGGER_LEVEL_V, sweep="NORMal"
    )
    scope_front_panel(3, VOLTS_PER_DIV, 0.0, "DC", "FIFTy")
    definition = SweepDefinition(
        name="l2-6 two lines",
        stage=SequencerStage(
            instrument="opx",
            sequence=PulseSequence(
                name="two lines",
                body=(
                    Step(channel="P2_pulse", level=LEVEL_V, duration=FIRST_NS),
                    Step(channel="P1_pulse", level=LEVEL_V, duration=16),
                    Capture(channel="scope1", duration=WINDOW_NS, num=POINTS, result="ch1"),
                    Capture(channel="scope3", duration=WINDOW_NS, num=POINTS, result="ch3"),
                    Wait(duration=SHOT_WAIT_NS),
                ),
            ),
            shots=SHOTS,
        ),
    )
    plan = compile_sweep(definition, stand, {"qua": QuaEmitter()})
    assert [(v.name, v.dims) for v in plan.dataset.data_vars] == [
        ("ch1", ("shot", "time")),
        ("ch3", ("shot", "time")),
    ]
    out = assemble(plan.dataset, Executor(plan, backends).run().frames())
    t_ns = np.linspace(0.0, WINDOW_NS, POINTS)
    ch1, ch3 = out["ch1"].values, out["ch3"].values
    assert (
        ch1.shape == ch3.shape == (SHOTS, POINTS)
        and np.isfinite(ch1).all()
        and np.isfinite(ch3).all()
    )
    late = t_ns > FIRST_NS + 1000  # after both edges
    for name, trace in (("ch1", ch1), ("ch3", ch3)):
        plateau = trace[:, late].mean(axis=1)
        assert np.all(np.abs(plateau - LEVEL_V) <= PLATEAU_TOLERANCE_V), (
            f"{name} plateau {plateau} V vs {LEVEL_V} V (±{PLATEAU_TOLERANCE_V * 1e3:.0f} mV)"
        )
    skews = np.array(
        [
            crossing_ns(t_ns, ch3[k], LEVEL_V / 2) - crossing_ns(t_ns, ch1[k], LEVEL_V / 2)
            for k in range(SHOTS)
        ]
    )
    print(
        f"skew ao2 − ao1 (programmed {FIRST_NS} ns): {skews.mean():.1f} ± {skews.std():.1f} ns over "
        f"{SHOTS} shots; grid {GRID_NS:.1f} ns"
    )
    assert np.all(np.abs(skews - FIRST_NS) <= SKEW_TOLERANCE_NS), (
        f"skew {skews} ns vs {FIRST_NS} ns (±{SKEW_TOLERANCE_NS:.0f} ns)"
    )
