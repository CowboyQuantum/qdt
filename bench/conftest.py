"""bench/: hardware-in-the-loop fixtures (L1 loopbacks, L2 instrument-on-instrument; `docs/BENCH.md`).

Everything here is `hardware`-marked. Backends are the real drivers, built through their
`from_config` factories (ADR 0021) from the `QDT_*_ADDRESS` variables; a missing variable skips. The
only bench-specific code is this construction and the front-panel settings a loopback needs (vertical
scale, coupling, impedance), which the `WaveformSense` protocol deliberately leaves to the user: they
belong to the signal, not to the grid. Addresses never reach a report (ADR 0042).
"""

import os
from collections.abc import Iterator

import pytest

from qdt_schemas.stand import ChannelMap, InstrumentConfig


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.hardware)


def _address(var: str) -> str:
    value = os.environ.get(var)
    if not value:
        pytest.skip(f"{var} not set")
    return value


def _instrument(
    id: str, backend: str, capabilities: tuple[str, ...], var: str, **settings
) -> InstrumentConfig:
    return InstrumentConfig(
        id=id,
        backend=backend,
        capabilities=capabilities,
        settings={"address": _address(var), **settings},
    )


@pytest.fixture
def closing() -> Iterator[list]:
    """Backends built for a test, closed at teardown (last first)."""
    made: list = []
    yield made
    for backend in reversed(made):
        backend.close()


@pytest.fixture
def qdac(closing):
    """The QDAC-II as a `LevelSource` (and `LevelSense`), from `QDT_QDAC2_ADDRESS`."""
    from qdt_lab.drivers.qdevil.qdac2 import QDac2

    inst = _instrument("dac0", "qdac2", ("level_source", "level_sense"), "QDT_QDAC2_ADDRESS")
    backend = QDac2.from_config(inst, ())
    closing.append(backend)
    return backend


@pytest.fixture
def smu(closing):
    """The Keithley 2400-series as `LevelSource` + `LevelSense` on its one terminal, from
    `QDT_SMU_ADDRESS`; channel `out` sources voltage with 1 mA compliance. The 2450 is routed to its
    front terminals first, over a socket that is closed again before the driver opens its own: the
    instrument accepts one raw-socket connection at a time."""
    import socket

    from qdt_lab.drivers.keithley.k2400 import Keithley2400

    inst = _instrument(
        "smu",
        "keithley2400",
        ("level_source", "level_sense"),
        "QDT_SMU_ADDRESS",
        current_limit_a=1e-3,
    )
    address = str(inst.settings["address"])
    host, port = address.split("::")[1], int(address.split("::")[2])
    with socket.create_connection((host, port), timeout=5) as c:
        c.sendall(b":ROUTe:TERMinals FRONt\n")
    channels = (ChannelMap(logical="out", instrument="smu", channel="out", quantity="voltage"),)
    backend = Keithley2400.from_config(inst, channels)
    closing.append(backend)
    return backend


@pytest.fixture
def opx(closing):
    """The OPX1000 (LF-FEM in `QDT_OPX_FEM`, default 1, direct output mode) as a `WaveformSource` and
    `WaveformSense`, from `QDT_OPX_ADDRESS`."""
    from qdt_lab.drivers.qm.opx1000 import Opx1000

    inst = _instrument(
        "opx",
        "qua",
        ("waveform_source", "waveform_sense", "sequencer"),
        "QDT_OPX_ADDRESS",
        fem=int(os.environ.get("QDT_OPX_FEM", "1")),
        output_mode="direct",
    )
    backend = Opx1000.from_config(inst, ())
    closing.append(backend)
    return backend


@pytest.fixture
def scope(closing):
    """The InfiniiVision as a `WaveformSense` on inputs 1..4, from `QDT_SCOPE_ADDRESS`."""
    from qdt_lab.drivers.keysight.infiniivision import InfiniiVisionX

    inst = _instrument("scope0", "infiniivision", ("waveform_sense",), "QDT_SCOPE_ADDRESS")
    channels = tuple(
        ChannelMap(logical=f"ch{n}", instrument="scope0", channel=str(n), quantity="voltage")
        for n in (1, 2, 3, 4)
    )
    backend = _retry(lambda: InfiniiVisionX.from_config(inst, channels))
    closing.append(backend)
    return backend


def _retry(open_backend, attempts: int = 3, pause_s: float = 2.0):
    """Open a backend, retrying a connect that times out: the HD3's socket server sometimes refuses
    the first connection right after a previous session closed."""
    import time

    for attempt in range(attempts):
        try:
            return open_backend()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(pause_s)
    raise AssertionError("unreachable")


@pytest.fixture
def scope_front_panel():
    """Apply a scope input's vertical settings over a second VISA session (the driver leaves them
    alone on purpose). Returns the function; call it before arming."""
    import pyvisa

    sessions = []

    def apply(
        number: int,
        volts_per_div: float,
        offset_v: float = 0.0,
        coupling: str = "DC",
        impedance: str = "ONEMeg",
        trigger_level_v: float | None = None,
    ) -> None:
        """Vertical settings for input `number`; with `trigger_level_v`, a rising-edge trigger on that
        input at that level (sweep stays AUTO so an absent signal cannot hang a capture)."""
        rm = pyvisa.ResourceManager("@py")
        r = rm.open_resource(_address("QDT_SCOPE_ADDRESS"))
        r.timeout = 5000
        sessions.append(r)
        r.write(f":CHANnel{number}:DISPlay 1")
        r.write(f":CHANnel{number}:COUPling {coupling}")
        r.write(f":CHANnel{number}:IMPedance {impedance}")
        r.write(f":CHANnel{number}:PROBe 1")
        r.write(f":CHANnel{number}:SCALe {volts_per_div:.6g}")
        r.write(f":CHANnel{number}:OFFSet {offset_v:.6g}")
        r.write(":TRIGger:SWEep AUTO")
        if trigger_level_v is not None:
            r.write(":TRIGger:MODE EDGE")
            r.write(f":TRIGger:EDGE:SOURce CHANnel{number}")
            r.write(":TRIGger:EDGE:SLOPe POSitive")
            r.write(f":TRIGger:EDGE:LEVel {trigger_level_v:.6g}")

    yield apply
    for r in sessions:
        r.close()
