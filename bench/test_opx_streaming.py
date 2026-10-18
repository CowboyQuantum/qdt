"""The OPX streams a run's results row by row (ADR 0015's chunking; the live view ADR 0066 needs).

A two-axis pulse map entirely inside the OPX (two stage axes: the amplitudes on ao1 and ao2, a measure on
ai1), each shot slowed by a wait, so the run lasts seconds. Through the executor, the frames must arrive one
slab of the first axis at a time, spread over the run, and not all at its end. Nothing need be cabled: the
values are whatever ai1 reads; the oracle is the chunking and its timing. `QDT_OPX_ADDRESS` (and
`QDT_OPX_FEM`, default 1).
"""

import os
import time

import pytest

from qdt_lab.experiment import Executor, QuaEmitter, compile_sweep
from qdt_schemas.activity import SequencerStage, SweepAxis, SweepDefinition, SymbolBinding
from qdt_schemas.pulse import Measure, PulseSequence, Step, Symbol, Wait
from qdt_schemas.stand import ChannelMap, InstrumentConfig, StandConfig

ROWS, POINTS = 6, 5
WAIT_NS = 40_000_000
"""Per shot: a row is POINTS shots, so about 0.2 s, and the run about 1.2 s plus its overheads."""


@pytest.fixture
def stand_and_opx(closing):
    address = os.environ.get("QDT_OPX_ADDRESS")
    if not address:
        pytest.skip("QDT_OPX_ADDRESS not set")
    from qdt_lab.drivers.qm.opx1000 import Opx1000

    stand = StandConfig(
        stand_id="opx-only",
        instruments=(
            InstrumentConfig(
                id="opx",
                backend="qua",
                capabilities=("sequencer",),
                settings={
                    "address": address,
                    "fem": int(os.environ.get("QDT_OPX_FEM", "1")),
                    "output_mode": "direct",
                },
            ),
        ),
        channels=(
            ChannelMap(logical="A_pulse", instrument="opx", channel="ao1", quantity="voltage"),
            ChannelMap(logical="B_pulse", instrument="opx", channel="ao2", quantity="voltage"),
            ChannelMap(logical="sensor", instrument="opx", channel="ai1", quantity="voltage"),
        ),
    )
    opx = Opx1000.from_config(stand.instrument("opx"), stand.instrument_channels("opx"))
    closing.append(opx)
    return stand, opx


def test_a_two_axis_run_streams_its_rows_while_it_runs(stand_and_opx):
    stand, opx = stand_and_opx
    a, b = Symbol(name="v_A", unit="V"), Symbol(name="v_B", unit="V")
    definition = SweepDefinition(
        name="opx streams rows",
        axes=(
            SweepAxis(name="A", channel="A_pulse", start=0.0, stop=0.05, num=ROWS),
            SweepAxis(name="B", channel="B_pulse", start=0.0, stop=0.05, num=POINTS),
        ),
        stage=SequencerStage(
            instrument="opx",
            axes=("A", "B"),
            sequence=PulseSequence(
                name="slow pixel",
                body=(
                    Step(channel="A_pulse", level=a, duration=200),
                    Step(channel="B_pulse", level=b, duration=200),
                    Measure(channel="sensor", duration=1000, result="I"),
                    Wait(duration=WAIT_NS),
                ),
            ),
            bindings=(SymbolBinding(symbol="v_A", axis="A"), SymbolBinding(symbol="v_B", axis="B")),
        ),
    )
    plan = compile_sweep(definition, stand, {"qua": QuaEmitter()})
    arrived = []
    t0 = time.perf_counter()
    for f in Executor(plan, {"opx": opx}).run().frames():
        arrived.append((time.perf_counter() - t0, f))
    assert len(arrived) == ROWS, "one frame per row of the first axis"
    first_axis = [f.chunk.region[0] for _, f in arrived]
    assert [(s.dim, s.start, s.stop) for s in first_axis] == [("A", r, r + 1) for r in range(ROWS)]
    assert arrived[-1][1].chunk.final and not any(f.chunk.final for _, f in arrived[:-1])
    first, last = arrived[0][0], arrived[-1][0]
    row_s = POINTS * WAIT_NS * 1e-9
    # all at the end would put them within one poll of each other; streamed, they span the rows' time
    assert last - first > 0.5 * (ROWS - 1) * row_s, (
        f"rows arrived over {last - first:.2f} s; streaming should spread them over ~{(ROWS - 1) * row_s:.1f} s"
    )
