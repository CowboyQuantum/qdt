"""pure-functional analysis: schema objects in, AnalysisResult out (no I/O; rule 5)

Detectors take a `Dataset` and its arrays and return an `AnalysisResult` (ADR 0029). `recovery` scores
a result against the truth its scenario knows. Nothing here opens a file, a socket or a registry.
"""

__version__ = "0.1.0"

from .diamonds import Diamonds, Edge, coulomb_diamonds, estimate_diamonds
from .recovery import Recovery, recovery, score
from .transitions import (
    DEFAULTS,
    MODEL_NAME,
    Detection,
    Segment,
    charge_transitions,
    detect,
    estimate,
)

__all__ = [
    "DEFAULTS",
    "MODEL_NAME",
    "Detection",
    "Diamonds",
    "Edge",
    "Recovery",
    "Segment",
    "__version__",
    "charge_transitions",
    "coulomb_diamonds",
    "detect",
    "estimate",
    "estimate_diamonds",
    "recovery",
    "score",
]
