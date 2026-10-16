"""Real instrument drivers (Step 5), one module per instrument, each behind an extra (ADR 0006).

    qdevil/qdac2.py           QDAC-II              LevelSource, LevelSense (current), TriggeredLevelSource  extra [qdac]
    keithley/k2400.py         Keithley 2400-series LevelSource, LevelSense               extra [smu]
    keysight/infiniivision.py InfiniiVision X      WaveformSense                         extra [keysight]
    qm/opx1000.py             OPX1000 (LF-FEM)     WaveformSource, WaveformSense, Sequencer (+ marker lines)  extra [opx]

Each driver is built by its `from_config(instrument, channels)` (ADR 0021); the address is
`instrument.settings["address"]`, supplied at run time and never committed (rule 7). Vendor libraries
are imported inside functions, so importing this package needs no extra.

`FACTORIES` maps `InstrumentConfig.backend` to the driver's factory, for
`qdt_lab.experiment.build_backends(stand, FACTORIES)`.
"""

from .keithley.k2400 import Keithley2400
from .keysight.infiniivision import InfiniiVisionX
from .qdevil.qdac2 import QDac2
from .qm.opx1000 import Opx1000

FACTORIES = {
    "qdac2": QDac2.from_config,
    "keithley2400": Keithley2400.from_config,
    "infiniivision": InfiniiVisionX.from_config,
    "qua": Opx1000.from_config,
}
"""Backend key → `BackendFactory` (ADR 0021) for every real driver."""

__all__ = ["FACTORIES", "InfiniiVisionX", "Keithley2400", "Opx1000", "QDac2"]
