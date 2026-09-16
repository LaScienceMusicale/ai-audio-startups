"""Checks StableAudioEngine against a fake StableAudioModel carrying the upstream
generate() signature, so a signature drift is caught without the weights."""

import sys
import types

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from sa3_endless.engine import StableAudioEngine  # noqa: E402


class FakeInner:
    sample_rate = 44100
    io_channels = 2


class FakeStableAudioModel:
    calls = []

    def __init__(self):
        self.model = FakeInner()

    @staticmethod
    def from_pretrained(model_name, device=None, model_half=True):
        return FakeStableAudioModel()

    def generate(
        self, prompt=None, negative_prompt=None, duration=120, steps=8, cfg_scale=1.0, batch_size=1,
        sample_size=5292032, truncate_output_to_duration=True, conditioning=None, conditioning_tensors=None,
        negative_conditioning=None, negative_conditioning_tensors=None, seed=-1, init_audio=None,
        init_noise_level=1.0, inpaint_audio=None, inpaint_mask=None, inpaint_mask_start_seconds=None,
        inpaint_mask_end_seconds=None, duration_padding_sec=6.0, apg_scale=1.0, dist_shift=None,
        return_latents=False, chunked_decode=None, **sampler_kwargs,
    ):
        assert prompt is not None, "Must provide either prompt or conditioning"  # upstream assert
        sr, audio = inpaint_audio
        assert isinstance(audio, torch.Tensor) and audio.ndim == 2
        self.calls.append(dict(prompt=prompt, duration=duration, start=inpaint_mask_start_seconds,
                               end=inpaint_mask_end_seconds, steps=steps, seed=seed))
        n = int(duration * sr)
        out = torch.zeros(1, 2, n)
        out[:, :, : audio.shape[1]] = audio  # keep context, "generate" silence after it
        out[:, :, audio.shape[1]:] = 0.25
        return out


@pytest.fixture
def fake_sa3(monkeypatch):
    mod = types.ModuleType("stable_audio_3")
    mod.StableAudioModel = FakeStableAudioModel
    monkeypatch.setitem(sys.modules, "stable_audio_3", mod)
    FakeStableAudioModel.calls.clear()
    return FakeStableAudioModel


def test_engine_calls_generate_like_upstream(fake_sa3):
    eng = StableAudioEngine("small-sfx", steps=4)
    eng.load()
    ctx = np.zeros((2, 44100 * 3), np.float32)
    out = eng.continue_audio(ctx, 2.0, prompt=None, seed=7)
    call = fake_sa3.calls[-1]
    assert call["prompt"] == ""  # no prompt must become the empty string, never None
    assert call["duration"] == pytest.approx(5.0)
    assert call["start"] == pytest.approx(3.0) and call["end"] == pytest.approx(5.0)
    assert call["steps"] == 4 and call["seed"] == 7
    assert out.shape == (2, 44100 * 2)
    assert np.allclose(out, 0.25)  # only the part after the context is returned


def test_engine_passes_prompt(fake_sa3):
    eng = StableAudioEngine("small-sfx")
    eng.continue_audio(np.zeros((2, 44100), np.float32), 1.0, prompt="wind")
    assert fake_sa3.calls[-1]["prompt"] == "wind"
