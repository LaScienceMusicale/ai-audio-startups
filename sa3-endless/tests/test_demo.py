import os

import numpy as np
import soundfile as sf

from sa3_endless.demo import main


def test_demo_renders_seed_and_continuation(tmp_path):
    sr = 44100
    t = np.arange(sr * 12) / sr
    sf.write(tmp_path / "seed.wav", (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr)
    out = tmp_path / "demo"
    assert main(["--seed", str(tmp_path / "seed.wav"), "--seed-seconds", "10", "--seconds", "20",
                 "--engine", "mock", "--out", str(out), "--chunk", "5", "--context", "5"]) == 0
    seed, _ = sf.read(out / "seed.wav")
    cont, _ = sf.read(out / "continuation.wav")
    full, _ = sf.read(out / "full.wav")
    assert len(seed) == 10 * sr and len(cont) == 20 * sr and len(full) == 30 * sr
    assert os.path.exists(out / "index.html")
