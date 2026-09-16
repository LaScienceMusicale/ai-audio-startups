import numpy as np

from sa3_endless.continuous import ContinuousConfig, ContinuousStream
from sa3_endless.engine import MockEngine
from sa3_endless.ring import RingBuffer
from sa3_endless.streamer import StreamConfig


def tone(sr, seconds, f=220.0):
    t = np.arange(int(sr * seconds)) / sr
    x = (0.5 * np.sin(2 * np.pi * f * t)).astype(np.float32)
    return np.stack([x, x])


def test_ring_roundtrip_and_wrap():
    r = RingBuffer(2, 100)
    a = np.arange(2 * 70, dtype=np.float32).reshape(2, 70)
    assert r.write(a) == 70
    out = r.read(50)
    assert np.array_equal(out, a[:, :50])
    b = np.arange(2 * 60, dtype=np.float32).reshape(2, 60) + 1000
    assert r.write(b) == 60  # wraps around
    out = r.read(80)
    assert np.array_equal(out, np.concatenate([a[:, 50:], b], axis=1))
    # underrun: 10 frames missing, zero filled and counted
    out = r.read(10)
    assert np.all(out == 0) and r.underrun_frames == 10


def test_ring_read_blocking_waits_for_data():
    import threading

    r = RingBuffer(1, 1000)
    threading.Timer(0.05, lambda: r.write(np.ones((1, 100), np.float32))).start()
    out = r.read(100, block=True, timeout=2.0)
    assert np.all(out == 1)


def test_continuous_stream_never_underruns_with_fast_engine():
    sr = 8000
    cfg = ContinuousConfig(
        stream=StreamConfig(chunk_seconds=1.0, context_seconds=2.0, overlap_seconds=0.1, lookahead=1),
        buffer_seconds=5.0, low_water_seconds=1.0, preroll_seconds=2.0,
    )
    s = ContinuousStream(MockEngine(sample_rate=sr), tone(sr, 3.0), cfg).start()
    try:
        s.wait_preroll(timeout=5.0)
        assert s.seconds_buffered() >= 2.0
        audio = np.concatenate([s.read(512, block=True) for _ in range(8000 * 6 // 512)], axis=1)[0]
        assert s.ring.underrun_frames == 0
        # continuous signal: no jumps larger than the sine slope + wobble
        assert np.max(np.abs(np.diff(audio))) < 2 * np.pi * 220 * 0.5 / sr * 1.2 + 0.03
    finally:
        s.stop()


def test_hold_keeps_audio_flowing_when_engine_is_slow():
    sr = 8000
    # engine takes 1.5s to produce 1s of audio: slower than real time
    eng = MockEngine(sample_rate=sr, latency=1.5)
    cfg = ContinuousConfig(
        stream=StreamConfig(chunk_seconds=1.0, context_seconds=2.0, overlap_seconds=0.1, lookahead=1),
        buffer_seconds=10.0, low_water_seconds=2.0, preroll_seconds=1.0, max_chunk_seconds=4.0,
    )
    s = ContinuousStream(eng, tone(sr, 3.0), cfg).start()
    try:
        s.wait_preroll(timeout=5.0)
        # drain faster than real time; the feeder must keep filling with holds
        got = 0
        for _ in range(40):
            block = s.read(2000, block=True)
            got += block.shape[1]
            assert np.max(np.abs(block)) > 0.01, "silence reached the output"
        assert s.state.holds >= 1
        assert s.ring.underrun_frames == 0
    finally:
        s.stop()


def test_adaptive_chunk_grows_when_slow():
    sr = 8000
    eng = MockEngine(sample_rate=sr, latency=0.8)  # rtf 0.8 for 1s chunks
    cfg = ContinuousConfig(
        stream=StreamConfig(chunk_seconds=1.0, context_seconds=1.0, overlap_seconds=0.05, lookahead=1),
        buffer_seconds=20.0, max_chunk_seconds=4.0, preroll_seconds=0.5,
    )
    s = ContinuousStream(eng, tone(sr, 2.0), cfg).start()
    try:
        import time
        t0 = time.monotonic()
        while s.state.chunks < 2 and time.monotonic() - t0 < 10:
            s.read(sr // 4, block=True)
        assert s.state.chunks >= 2
        assert s.state.chunk_seconds > 1.0
    finally:
        s.stop()
