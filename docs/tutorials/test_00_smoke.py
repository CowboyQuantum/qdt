"""Tutorial 00 — the smallest possible qdt program: talk to a simulated level source.

Every tutorial in this folder is also a test. Read it top to bottom.
"""
from qdt_lab.simulated import SimulatedLevelSource

# A backend is anything that satisfies a capability protocol. The simulated one is always available.
gates = SimulatedLevelSource()

# Protocols describe what an instrument can do, not what it is: hold a level on a terminal, read the
# setpoint back. Which quantity the level is (volts here) is declared on the channel, not in the verb.
gates.set("gate_L", 0.250)
readback = gates.get("gate_L")

assert abs(readback - 0.250) < 1e-6
