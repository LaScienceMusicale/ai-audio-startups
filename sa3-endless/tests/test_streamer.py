import numpy as np

from sa3_endless.engine import MockEngine
from sa3_endless.streamer import StreamConfig, Streamer


def make_seed(sr, seconds=3.0):
    t = np.arange(int(sr * seconds)) / sr
    tone = 0.5 * np.sin(2 * np.pi * 220 * t).astype(np.float32)
    return np.stack([tone, tone])


def collect(streamer, n_chunks):
    out = [streamer.next_chunk(timeout=5.0) for _ in range(n_chunks)]
    assert all(c is not None for c in out)
    return out


def test_stream_produces_expected_lengths():
    eng = MockEngine(sample_rate=8000)
    cfg = StreamConfig(chunk_seconds=1.0, context_seconds=2.0, overlap_seconds=0.25, lookahead=1)
    s = Streamer(eng, make_seed(8000), cfg).start()
    try:
        first, second, third = collect(s, 3)
        assert first.shape == (2, 8000 * 3 - 2000)  # seed minus the overlap kept as pending tail
        # every generated chunk delivers exactly chunk_seconds + one overlap (the seam)
        assert second.shape == (2, 8000 + 2000)
        assert third.shape == (2, 8000 + 2000)
        assert eng.calls >= 2
    finally:
        s.stop()


def test_stream_is_continuous_at_seams():
    sr = 8000
    eng = MockEngine(sample_rate=sr)
    cfg = StreamConfig(chunk_seconds=1.0, context_seconds=2.0, overlap_seconds=0.1, lookahead=1)
    s = Streamer(eng, make_seed(sr), cfg).start()
    try:
        audio = np.concatenate(collect(s, 4), axis=1)[0]
    finally:
        s.stop()
    # a 220 Hz tone continued by looping should never jump by more than the max
    # slope of the sine (2*pi*f*A/sr) plus the small gain wobble.
    max_step = 2 * np.pi * 220 * 0.5 / sr * 1.2 + 0.03
    assert np.max(np.abs(np.diff(audio))) < max_step


def test_reseed_and_prompt():
    sr = 8000
    eng = MockEngine(sample_rate=sr)
    cfg = StreamConfig(chunk_seconds=0.5, context_seconds=1.0, overlap_seconds=0.05, lookahead=1)
    s = Streamer(eng, make_seed(sr, 1.0), cfg).start()
    try:
        collect(s, 2)
        silence = np.zeros((2, sr), np.float32)
        s.reseed(silence)
        s.set_prompt("wind")
        assert s.prompt == "wind"
        chunks = collect(s, 4)
        # the new seed is emitted as-is after a short crossfade from the old tail
        ov = int(0.05 * sr)
        assert any(np.max(np.abs(c[:, ov:])) < 1e-6 and c.shape[1] > ov for c in chunks)
    finally:
        s.stop()


def test_stop_unblocks_consumer():
    eng = MockEngine(sample_rate=8000, latency=0.05)
    s = Streamer(eng, make_seed(8000), StreamConfig(chunk_seconds=0.5, lookahead=1)).start()
    s.next_chunk(timeout=5.0)
    s.stop()
    # drain until None
    for _ in range(10):
        if s.next_chunk(timeout=1.0) is None:
            break
    else:
        raise AssertionError("stream did not stop")
