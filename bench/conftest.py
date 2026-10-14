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


def _instrument(id: str, backend: str, capabilities: tuple[str, ...], var: str) -> InstrumentConfig:
    return InstrumentConfig(
        id=id, backend=backend, capabilities=capabilities, settings={"address": _address(var)}
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
def scope(closing):
    """The InfiniiVision as a `WaveformSense` on inputs 1..4, from `QDT_SCOPE_ADDRESS`."""
    from qdt_lab.drivers.keysight.infiniivision import InfiniiVisionX

    inst = _instrument("scope0", "infiniivision", ("waveform_sense",), "QDT_SCOPE_ADDRESS")
    channels = tuple(
        ChannelMap(logical=f"ch{n}", instrument="scope0", channel=str(n), quantity="voltage")
        for n in (1, 2, 3, 4)
    )
    backend = InfiniiVisionX.from_config(inst, channels)
    closing.append(backend)
    return backend


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
    ) -> None:
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

    yield apply
    for r in sessions:
        r.close()
