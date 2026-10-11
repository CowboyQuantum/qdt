"""Tutorial 00 — the smallest possible qdt program: talk to a simulated DC source.

Every tutorial in this folder is also a test. Read it top to bottom.
"""
from qdt_lab.simulated import SimulatedDCSource

# A backend is anything that satisfies a capability protocol. The simulated one is always available.
dc = SimulatedDCSource()

# Protocols describe what an instrument can do, not what it is: set a voltage, read it back.
dc.set_voltage("gate_L", 0.250)
readback = dc.get_voltage("gate_L")

assert abs(readback - 0.250) < 1e-6
