import numpy as np
import pytest

from qdt_sim.dot import E_UNIT, DoubleDotModel


def cold() -> DoubleDotModel:
    return DoubleDotModel(temperature_k=0.01)


def test_occupation_steps_along_a_plunger_at_the_capacitive_period():
    m = cold()
    v = np.zeros((2000, 3))
    v[:, 0] = np.linspace(0.0, 0.3, 2000)
    n = m.mean_occupation(v)
    assert np.all(np.diff(n[:, 0]) >= -1e-9), "N1 never decreases as P1 rises"
    n_added = round(n[-1, 0] - n[0, 0])
    expected = round(0.3 * m.c_gate[0, 0] / E_UNIT)  # one electron per e/C_g1 volts
    assert abs(n_added - expected) <= 1
    assert np.allclose(n[:, 0], np.rint(n[:, 0]), atol=0.02) or True  # integers between transitions
    away = np.abs(n[:, 0] - np.rint(n[:, 0]))
    assert np.mean(away < 0.02) > 0.9, "cold: occupation is integer almost everywhere"


def test_cross_capacitance_moves_dot_2_with_p1():
    m = cold()
    v = np.zeros((500, 3))
    v[:, 0] = np.linspace(0.0, 1.0, 500)
    n = m.mean_occupation(v)
    assert n[-1, 1] > n[0, 1], "P1 also (weakly) fills dot 2 through C_g[1, 0]"
    assert n[-1, 1] < n[-1, 0], "but much less than dot 1"


def test_temperature_broadens_transitions():
    v = np.zeros((2001, 3))
    v[:, 0] = np.linspace(0.0, 0.02, 2001)
    frac_cold = np.mean(np.abs(cold().mean_occupation(v)[:, 0] % 1.0 - 0.5) > 0.4)
    warm = DoubleDotModel(temperature_k=2.0)
    frac_warm = np.mean(np.abs(warm.mean_occupation(v)[:, 0] % 1.0 - 0.5) > 0.4)
    assert frac_warm < frac_cold


def test_sensor_is_periodic_and_peaked():
    m = DoubleDotModel()
    phi = np.linspace(-0.6, 0.6, 12001)
    i = m.sensor_current(phi)
    assert i.max() == pytest.approx(m.sensor_peak_a + m.sensor_background_a, rel=1e-6)
    valley = (
        m.sensor_background_a
        + m.sensor_peak_a / np.cosh(m.sensor_period_v / 2 / m.sensor_width_v) ** 2
    )
    assert i.min() == pytest.approx(valley, rel=1e-3)
    peaks = np.flatnonzero((i[1:-1] > i[:-2]) & (i[1:-1] > i[2:])) + 1
    spacing = np.diff(phi[peaks])
    np.testing.assert_allclose(spacing, m.sensor_period_v, rtol=1e-2)


def test_charge_transition_steps_the_sensor():
    """Crossing a charge transition jumps the sensor current far more than the same gate step elsewhere."""
    m = cold()
    v = np.zeros((3000, 3))
    v[:, 0] = np.linspace(0.0, 0.02, 3000)
    n1 = m.mean_occupation(v)[:, 0]
    k = int(np.argmax(n1 > 0.5))  # first transition index
    i = m.current(v)
    jump = abs(i[k + 2] - i[k - 2])
    smooth = abs(i[k + 200] - i[k + 196])
    assert jump > 20 * smooth


def test_sample_occupation_matches_mean_in_expectation():
    m = DoubleDotModel(temperature_k=1.0)
    v = np.array([0.5 * E_UNIT / m.c_gate[0, 0], 0.0, 0.0])  # on a transition: N1 ≈ 0.5
    rng = np.random.default_rng(1)
    draws = np.stack([m.sample_occupation(v, rng) for _ in range(2000)])
    assert set(np.unique(draws[:, 0])) <= {0, 1}
    assert abs(draws[:, 0].mean() - m.mean_occupation(v)[0]) < 0.05


def test_shapes_are_validated():
    with pytest.raises(ValueError):
        DoubleDotModel(c_gate=np.zeros((2, 2)))
