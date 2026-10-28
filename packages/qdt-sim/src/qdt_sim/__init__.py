"""An adapter over a pinned Phantom release behind qdt-lab's protocols (ADR 0020, 0087); no physics."""

from .device import PhantomPhysics, SimulatedDevice

__version__ = "0.1.0"

__all__ = ["PhantomPhysics", "SimulatedDevice"]
