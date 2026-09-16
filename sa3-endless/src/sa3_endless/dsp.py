"""Small numpy DSP helpers. Audio arrays are float32 with shape [channels, samples]."""

from __future__ import annotations

import numpy as np


def to_channels(audio: np.ndarray, channels: int) -> np.ndarray:
    """Return `audio` with exactly `channels` channels (mono is duplicated, extras dropped)."""
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[None, :]
    if audio.shape[0] == channels:
        return audio
    if audio.shape[0] == 1:
        return np.repeat(audio, channels, axis=0)
    if audio.shape[0] > channels:
        return audio[:channels]
    # fewer channels than wanted (but more than one): pad by repeating the last one
    pad = np.repeat(audio[-1:], channels - audio.shape[0], axis=0)
    return np.concatenate([audio, pad], axis=0)


def resample(audio: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """Resample [channels, samples] audio. Uses soxr when available, linear interpolation otherwise."""
    if sr_in == sr_out:
        return np.asarray(audio, dtype=np.float32)
    try:
        import soxr

        # soxr wants [samples, channels]
        out = soxr.resample(np.ascontiguousarray(audio.T), sr_in, sr_out, quality="HQ")
        return np.ascontiguousarray(out.T, dtype=np.float32)
    except ImportError:  # pragma: no cover - fallback path
        n_in = audio.shape[1]
        n_out = int(round(n_in * sr_out / sr_in))
        x_in = np.linspace(0.0, 1.0, n_in, endpoint=False)
        x_out = np.linspace(0.0, 1.0, n_out, endpoint=False)
        return np.stack([np.interp(x_out, x_in, ch) for ch in audio]).astype(np.float32)


def crossfade(tail: np.ndarray, head: np.ndarray) -> np.ndarray:
    """Equal-power crossfade of `tail` (fading out) into `head` (fading in).

    Both are [channels, n] with the same n. Returns [channels, n].
    """
    if tail.shape != head.shape:
        raise ValueError(f"crossfade shapes differ: {tail.shape} vs {head.shape}")
    n = tail.shape[1]
    if n == 0:
        return tail.astype(np.float32)
    t = np.linspace(0.0, 1.0, n, endpoint=False, dtype=np.float32)
    fade_out = np.cos(t * np.pi / 2)
    fade_in = np.sin(t * np.pi / 2)
    return (tail * fade_out + head * fade_in).astype(np.float32)


def peak_normalize(audio: np.ndarray, peak: float = 0.9) -> np.ndarray:
    """Scale so that the absolute peak equals `peak` (no-op on silence)."""
    m = float(np.max(np.abs(audio))) if audio.size else 0.0
    if m <= 1e-9:
        return audio.astype(np.float32)
    return (audio * (peak / m)).astype(np.float32)
