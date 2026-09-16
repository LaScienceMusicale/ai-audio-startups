"""Loading the short samples that seed the stream."""

from __future__ import annotations

import os
from typing import List

import numpy as np

from .dsp import peak_normalize, resample, to_channels

AUDIO_EXT = {".wav", ".flac", ".aif", ".aiff", ".ogg", ".mp3"}


def list_samples(path: str) -> List[str]:
    if os.path.isdir(path):
        files = sorted(
            os.path.join(path, f) for f in os.listdir(path) if os.path.splitext(f)[1].lower() in AUDIO_EXT
        )
        if not files:
            raise SystemExit(f"no audio files found in {path}")
        return files
    if os.path.isfile(path):
        return [path]
    raise SystemExit(f"no such file or directory: {path}")


def load_sample(path: str, sample_rate: int, channels: int, normalize: bool = True) -> np.ndarray:
    """Read a file and return float32 [channels, samples] at `sample_rate`."""
    import soundfile as sf

    data, sr = sf.read(path, dtype="float32", always_2d=True)  # [samples, channels]
    audio = to_channels(data.T, channels)
    audio = resample(audio, sr, sample_rate)
    return peak_normalize(audio) if normalize else audio
