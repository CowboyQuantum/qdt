import itertools

import numpy as np
import pytest

from qdt_sim.noise import Composite, NoiseModel, NoNoise, OneOverFNoise, TelegraphNoise, WhiteNoise


def test_models_satisfy_protocol():
    for m in (WhiteNoise(1.0), TelegraphNoise(1.0, 1.0, 1.0), OneOverFNoise(1.0), NoNoise()):
        assert isinstance(m, NoiseModel)


def test_white_noise_has_the_declared_sigma_and_is_reproducible():
    wa, wb = WhiteNoise(2.0, seed=3), WhiteNoise(2.0, seed=3)
    a = [wa.sample(t) for t in range(20000)]
    b = [wb.sample(t) for t in range(20000)]
    assert a == b
    assert np.std(a) == pytest.approx(2.0, rel=0.03)
    assert WhiteNoise(0.0).sample(0.0) == 0.0


def test_telegraph_takes_two_values_and_switches_at_its_rates():
    tn = TelegraphNoise(amplitude=1.0, rate_up=10.0, rate_down=10.0, seed=0)
    t = np.arange(0, 200.0, 1e-3)
    x = np.array([tn.sample(ti) for ti in t])
    assert set(np.unique(x)) == {-0.5, 0.5}
    switches = np.count_nonzero(np.diff(x))
    assert switches == pytest.approx(200 * 10.0, rel=0.15)  # ≈ rate × duration each way
    assert x.mean() == pytest.approx(0.0, abs=0.05)


def test_telegraph_is_sampled_exactly_for_any_time_step():
    # with a huge step the state is independent of the past: mean over many such steps → p_up - 1/2
    tn = TelegraphNoise(amplitude=1.0, rate_up=3.0, rate_down=1.0, seed=5)
    x = np.array([tn.sample(1e6 * k) for k in range(4000)])
    assert x.mean() == pytest.approx(0.75 - 0.5, abs=0.03)


def test_one_over_f_spectrum_slope():
    n = OneOverFNoise(amplitude=1.0, f_min=1.0, f_max=1e3, n_fluctuators=40, seed=2)
    dt, length = 1e-4, 2**17
    x = np.array([n.sample(k * dt) for k in range(length)])
    assert np.std(x) == pytest.approx(1.0, rel=0.3)
    psd = np.abs(np.fft.rfft(x - x.mean())) ** 2
    f = np.fft.rfftfreq(length, dt)
    band = (f > 3.0) & (f < 300.0)
    # average the periodogram in log-spaced bins before fitting
    edges = np.geomspace(3.0, 300.0, 12)
    fb, pb = [], []
    for lo, hi in itertools.pairwise(edges):
        sel = band & (f >= lo) & (f < hi)
        fb.append(np.sqrt(lo * hi))
        pb.append(psd[sel].mean())
    slope = np.polyfit(np.log(fb), np.log(pb), 1)[0]
    assert -1.4 < slope < -0.6


def test_composite_sums():
    c = Composite((WhiteNoise(0.0), TelegraphNoise(2.0, 1.0, 1.0, seed=0)))
    assert c.sample(0.0) in (-1.0, 1.0)


def test_invalid_rates_rejected():
    with pytest.raises(ValueError):
        TelegraphNoise(1.0, 0.0, 0.0)
    with pytest.raises(ValueError):
        OneOverFNoise(1.0, f_min=10.0, f_max=1.0)
