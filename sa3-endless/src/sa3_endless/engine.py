"""Continuation engines.

An engine takes a context (the audio that was just played) and returns the audio
that should come *after* it. Everything is float32 numpy with shape [channels, samples]
at `engine.sample_rate`.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

import numpy as np

log = logging.getLogger(__name__)


class Engine(Protocol):
    sample_rate: int
    channels: int

    def continue_audio(
        self,
        context: np.ndarray,
        new_seconds: float,
        prompt: Optional[str] = None,
        seed: int = -1,
    ) -> np.ndarray:
        """Return `new_seconds` of audio that follows `context`."""
        ...


class MockEngine:
    """Cheap stand-in for tests and for checking the audio pipeline without a model.

    It continues the context by looping it with a slow random gain wobble, so the
    output is continuous with the input and obviously repetitive.
    """

    def __init__(self, sample_rate: int = 44100, channels: int = 2, latency: float = 0.0):
        self.sample_rate = sample_rate
        self.channels = channels
        self.latency = latency
        self.calls = 0

    def continue_audio(self, context, new_seconds, prompt=None, seed=-1):
        import time

        self.calls += 1
        if self.latency:
            time.sleep(self.latency)
        n_new = int(round(new_seconds * self.sample_rate))
        if context.shape[1] == 0:
            return np.zeros((self.channels, n_new), dtype=np.float32)
        reps = int(np.ceil(n_new / context.shape[1])) + 1
        tiled = np.tile(context, (1, reps))[:, :n_new]
        rng = np.random.default_rng(None if seed < 0 else seed)
        wobble = 1.0 + 0.05 * np.sin(np.linspace(0, 2 * np.pi * rng.uniform(0.5, 2.0), n_new))
        return (tiled * wobble).astype(np.float32)


class StableAudioEngine:
    """Continuation with Stable Audio 3 (inpainting past the end of the context).

    Requires the `stable-audio-3` package (pip install -e ".[sa3]"). The model is
    loaded lazily on first use so the CLI can fail fast on argument errors.
    """

    def __init__(
        self,
        model_name: str = "small-sfx",
        device: Optional[str] = None,
        steps: int = 8,
        cfg_scale: float = 1.0,
        model_half: bool = True,
    ):
        self.model_name = model_name
        self.device = device
        self.steps = steps
        self.cfg_scale = cfg_scale
        self.model_half = model_half
        self.channels = 2
        self._model = None
        self.sample_rate = 44100  # overwritten by the model on load

    def load(self):
        if self._model is not None:
            return self._model
        try:
            from stable_audio_3 import StableAudioModel
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "stable_audio_3 is not installed. Run: pip install -e '.[sa3]' "
                "(see https://github.com/Stability-AI/stable-audio-3)"
            ) from exc
        log.info("loading Stable Audio 3 model %r on %s", self.model_name, self.device or "auto")
        self._model = StableAudioModel.from_pretrained(
            self.model_name, device=self.device, model_half=self.model_half
        )
        self.sample_rate = int(self._model.model.sample_rate)
        log.info("model loaded, sample rate %d Hz", self.sample_rate)
        return self._model

    def continue_audio(self, context, new_seconds, prompt=None, seed=-1):
        import torch

        model = self.load()
        sr = self.sample_rate
        ctx_seconds = context.shape[1] / sr
        total = ctx_seconds + new_seconds
        audio = model.generate(
            prompt=prompt or None,
            duration=total,
            steps=self.steps,
            cfg_scale=self.cfg_scale,
            seed=seed,
            inpaint_audio=(sr, torch.from_numpy(np.ascontiguousarray(context))),
            inpaint_mask_start_seconds=ctx_seconds,
            inpaint_mask_end_seconds=total,
        )
        out = audio[0].float().cpu().numpy()  # [channels, samples]
        start = int(round(ctx_seconds * sr))
        n_new = int(round(new_seconds * sr))
        tail = out[:, start : start + n_new]
        if tail.shape[1] < n_new:  # model truncated a bit short: pad with silence
            tail = np.pad(tail, ((0, 0), (0, n_new - tail.shape[1])))
        from .dsp import to_channels

        return to_channels(tail, self.channels)
