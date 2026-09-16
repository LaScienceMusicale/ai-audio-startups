import numpy as np

from sa3_endless.dsp import crossfade, peak_normalize, resample, to_channels


def test_to_channels_mono_to_stereo():
    mono = np.ones((1, 10), np.float32)
    assert to_channels(mono, 2).shape == (2, 10)
    assert to_channels(np.ones((3, 10), np.float32), 2).shape == (2, 10)


def test_crossfade_is_equal_power_and_continuous():
    n = 1000
    a = np.ones((2, n), np.float32)
    b = np.ones((2, n), np.float32)
    out = crossfade(a, b)
    assert out.shape == (2, n)
    # equal power: energy stays ~1 for two equal, uncorrelated-ish signals at the ends
    assert abs(out[0, 0] - 1.0) < 1e-5
    assert abs(out[0, -1] - 1.0) < 1e-2
    # midpoint of an equal-power fade of identical signals is sqrt(2) (> 1, no dip)
    assert out[0, n // 2] > 1.0


def test_resample_length():
    x = np.random.default_rng(0).standard_normal((2, 44100)).astype(np.float32)
    y = resample(x, 44100, 48000)
    assert y.shape[0] == 2
    assert abs(y.shape[1] - 48000) <= 2


def test_peak_normalize():
    x = np.array([[0.1, -0.5, 0.2]], np.float32)
    assert np.isclose(np.max(np.abs(peak_normalize(x, 0.9))), 0.9)
    assert np.all(peak_normalize(np.zeros((1, 4), np.float32)) == 0)
