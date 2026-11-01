"""A sweep inherits the held operating point (ADR 0053), and a virtual gate's coupled companion moves
from its held level, not from 0 V (#176, ADR 0092)."""

import numpy as np

import qdt_sim.device as simulated
from qdt_lab.experiment import Executor, SimulatedEmitter, compile_sweep
from qdt_server.runs import with_operating_point
from qdt_sim.scenarios import DEVICE_ID, default_device, default_stand, start
from qdt_tuning.nodes import stability_diagram

HELD = {"P1": 0.6, "P2": 0.6, "SG": 0.65}


def virtual(c_21: float = -0.07, c_12: float = -0.12):
    """A 2 × 2 virtual-gate stability diagram: P2's DC line follows P1 by `c_21`, the P1 pulse follows
    the P2 pulse by `c_12`."""
    d = stability_diagram(instrument=DEVICE_ID, p1=(0.5, 0.7), p2=(-0.1, 0.1), n_outer=2, n_inner=2, virtual=True)
    data = d.model_dump(mode="json")
    data["axes"][0]["couplings"]["P2"] = c_21
    data["stage"]["sequence"]["body"][0]["level"]["scale"] = c_12
    return type(d).model_validate(data)


def test_a_coupled_companion_keeps_its_held_level_as_the_couplings_origin():
    merged = with_operating_point(virtual(), HELD)
    levels = {lv.channel: lv.value for lv in merged.levels}
    assert levels == {"P2": 0.6, "SG": 0.65}, "P1 is the axis; P2 (the companion) and SG are held"
    assert with_operating_point(virtual(), {}) == virtual()


def test_the_companion_moves_from_the_held_level_on_the_stand(monkeypatch):
    seen: list[tuple[float, float]] = []
    sense = simulated.PhantomPhysics.sense

    def spy(self, levels, dwell_s, samples, gap_s=0.0):
        seen.append((levels["P1"], levels["P2"]))
        return sense(self, levels, dwell_s, samples, gap_s)

    monkeypatch.setattr(simulated.PhantomPhysics, "sense", spy)
    held = start() | HELD
    plan = compile_sweep(with_operating_point(virtual(), held), default_stand(), {"simulated": SimulatedEmitter()})
    for _ in Executor(plan, {DEVICE_ID: default_device(noise=False)}).run().frames():
        pass
    p1 = np.array([p for p, _ in seen])
    p2 = np.array([q for _, q in seen])
    pulse = np.tile([-0.1, 0.1], 2)
    # P2 = its held level + c_21 × the P1 axis value + the P2 pulse; P1 = the axis + c_12 × the pulse
    np.testing.assert_allclose(p2, 0.6 - 0.07 * np.repeat([0.5, 0.7], 2) + pulse, atol=1e-9)
    np.testing.assert_allclose(p1, np.repeat([0.5, 0.7], 2) - 0.12 * pulse, atol=1e-9)
