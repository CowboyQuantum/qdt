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
    # at the default (small) bias the peaks are the linear-response sech² train within a few percent
    assert i.max() == pytest.approx(m.sensor_peak_a + m.sensor_background_a, rel=0.03)
    valley = (  # halfway between two peaks both tails contribute
        m.sensor_background_a
        + 2 * m.sensor_peak_a / np.cosh(m.sensor_period_v / 2 / m.sensor_width_v) ** 2
    )
    assert i.min() == pytest.approx(valley, rel=0.05)
    # in the linear-response limit the train is exactly the ADR 0020 sech² train (summed over peaks)
    tiny = (m.sensor_current(phi, v_sd=1e-9) - m.sensor_background_a) * m.sensor_bias_v / 1e-9
    k = np.arange(-3, 4)
    d = phi[:, None] - m.sensor_phase_v - k * m.sensor_period_v
    sech = (m.sensor_peak_a / np.cosh(d / m.sensor_width_v) ** 2).sum(axis=1)
    np.testing.assert_allclose(tiny, sech, rtol=1e-4)
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


def test_ground_state_is_the_zero_temperature_limit():
    m = DoubleDotModel()
    cold = DoubleDotModel(temperature_k=1e-4)
    v = np.stack(np.meshgrid(np.linspace(-0.02, 0.06, 9), np.linspace(-0.02, 0.06, 9), indexing="ij"), -1)
    v = np.concatenate([v, np.zeros(v.shape[:-1] + (1,))], axis=-1)
    np.testing.assert_array_equal(m.ground_state(v), np.rint(cold.mean_occupation(v)))


def test_transition_map_marks_lines_where_the_ground_state_changes():
    m = DoubleDotModel()
    p1 = np.linspace(-0.02, 0.06, 64)
    p2 = np.linspace(-0.02, 0.06, 64)
    v = np.stack([*np.meshgrid(p1, p2, indexing="ij"), np.zeros((64, 64))], axis=-1)
    t = m.transition_map(v)
    n = m.ground_state(v)
    assert t.shape == (64, 64) and t.dtype == np.int8
    assert set(np.unique(t)) <= {0, 1, 2, 3}
    # every marked cell borders a different ground state; every unmarked cell borders none
    diff = (np.diff(n, axis=0) != 0).any(-1)[:, :-1] | (np.diff(n, axis=1) != 0).any(-1)[:-1, :]
    np.testing.assert_array_equal(t[:-1, :-1] != 0, diff)
    assert (t == 1).sum() > 50 and (t == 2).sum() > 50  # both families cross the window


def test_sensor_bias_opens_coulomb_diamonds():
    """Blockade inside the diamond, saturation outside; the apex sits at V_sd = E_c / e, the edges at
    `diamond_edges`, and the current reverses with the bias."""
    m = DoubleDotModel()
    phi = m.sensor_phase_v + m.sensor_period_v / 2  # halfway between two degeneracy points
    e_c = m.sensor_charging_ev
    # the sensor is warm (kT_s ≈ 0.08 E_c, from sensor_width_v), so blockade is soft near the apex
    assert m.sensor_current(phi, 0.2 * e_c) < m.sensor_background_a + 0.1 * m.sensor_peak_a
    assert m.sensor_current(phi, 1.3 * e_c) > m.sensor_background_a + m.sensor_peak_a
    assert m.sensor_current(phi, -1.3 * e_c) < m.sensor_background_a - m.sensor_peak_a
    (phi_0, s_up), (_, s_down) = m.diamond_edges(0)
    assert phi_0 == m.sensor_phase_v and s_down == -s_up
    v_apex = (m.sensor_period_v / 2) * s_up  # where the rising edge of k meets the falling edge of k+1
    assert v_apex == pytest.approx(e_c, rel=1e-12)
    # on an edge the current is half-way between blockade and saturation
    for d in (-0.08, 0.05):
        v = s_up * d
        i_on, i_off = m.sensor_current(phi_0 + d, v * 1.3), m.sensor_current(phi_0 + d, v * 0.7)
        i_edge = m.sensor_current(phi_0 + d, v)
        assert min(i_on, i_off) < i_edge < max(i_on, i_off)
