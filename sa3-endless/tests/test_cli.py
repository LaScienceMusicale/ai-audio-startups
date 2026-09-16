import numpy as np
import soundfile as sf

from sa3_endless.cli import main


def test_offline_render_with_mock_engine(tmp_path):
    sr = 22050
    t = np.arange(sr * 2) / sr
    seed = (0.3 * np.sin(2 * np.pi * 330 * t)).astype(np.float32)
    samples = tmp_path / "samples"
    samples.mkdir()
    sf.write(samples / "a.wav", seed, sr)
    sf.write(samples / "b.wav", seed * 0.5, sr)
    out = tmp_path / "out.wav"
    rc = main([
        "--samples", str(samples), "--engine", "mock", "--render", "6", "--output", str(out),
        "--chunk", "1", "--context", "2", "--overlap", "0.1", "--switch-every", "2", "--no-stdin",
    ])
    assert rc == 0
    audio, out_sr = sf.read(out)
    assert out_sr == 44100
    assert audio.shape[1] == 2
    assert audio.shape[0] >= 6 * out_sr
