import numpy as np
import pytest

from sanscontact.interpretation.one_euro import OneEuroFilter2D

FPS = 30.0


def run(filter_, xs, ys):
    return np.array([filter_(x, y, i / FPS) for i, (x, y) in enumerate(zip(xs, ys, strict=True))])


def test_constant_input_stays_constant():
    out = run(OneEuroFilter2D(), [100.0] * 50, [200.0] * 50)
    assert np.allclose(out, [100.0, 200.0])


def test_jitter_at_rest_is_strongly_reduced():
    rng = np.random.default_rng(1)
    xs = 500 + rng.normal(0, 4, 300)
    ys = 300 + rng.normal(0, 4, 300)
    out = run(OneEuroFilter2D(min_cutoff=1.0, beta=0.015), xs, ys)[60:]
    assert out[:, 0].std() < 0.5 * xs[60:].std()


def test_follows_a_step_eventually():
    out = run(OneEuroFilter2D(), [0.0] * 10 + [1000.0] * 120, [0.0] * 130)
    assert out[-1, 0] == pytest.approx(1000.0, abs=1.0)


def test_higher_beta_means_less_lag_in_motion():
    xs = np.arange(90) * 40.0  # fast, steady motion: 1200 px/s
    lag_low = xs[-1] - run(OneEuroFilter2D(beta=0.0), xs, np.zeros(90))[-1, 0]
    lag_high = xs[-1] - run(OneEuroFilter2D(beta=0.05), xs, np.zeros(90))[-1, 0]
    assert 0 <= lag_high < lag_low


def test_non_increasing_time_returns_last_value():
    f = OneEuroFilter2D()
    first = f(10.0, 10.0, 1.0)
    assert f(50.0, 50.0, 1.0) == first


def test_reset_and_invalid_parameters():
    f = OneEuroFilter2D()
    f(10.0, 10.0, 0.0)
    f.reset()
    assert f(99.0, 1.0, 5.0) == (99.0, 1.0)
    with pytest.raises(ValueError):
        OneEuroFilter2D(min_cutoff=0)
