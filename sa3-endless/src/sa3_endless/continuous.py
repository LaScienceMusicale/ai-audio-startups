"""A gapless audio stream on top of chunked generation.

The model produces audio in chunks; this layer makes the output a continuous
signal that never stops:

* a ring buffer holds several seconds of audio ahead of playback,
* the feeder keeps it topped up from the generator,
* if the generator falls behind, the feeder plays a loop of the recent context
  (crossfaded, ending exactly where the model will resume) instead of silence,
* chunk length adapts to the measured generation speed.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .dsp import crossfade
from .streamer import ChunkStats, StreamConfig, Streamer

log = logging.getLogger(__name__)


@dataclass
class ContinuousConfig:
    stream: StreamConfig = field(default_factory=StreamConfig)
    buffer_seconds: float = 30.0  # ring buffer capacity
    low_water_seconds: float = 3.0  # below this, hold audio is inserted
    preroll_seconds: float = 4.0  # audio buffered before playback starts
    max_chunk_seconds: float = 30.0  # cap for adaptive chunk growth
    adaptive: bool = True


@dataclass
class StreamState:
    chunks: int = 0
    holds: int = 0
    last_rtf: float = 0.0
    chunk_seconds: float = 0.0


class ContinuousStream:
    """Pull audio with `read(frames)` at any block size; it is always gapless."""

    def __init__(self, engine, seed_audio: np.ndarray, config: ContinuousConfig = ContinuousConfig()):
        from .ring import RingBuffer

        self.config = config
        self.sr = engine.sample_rate
        self.channels = engine.channels
        self._base_chunk = config.stream.chunk_seconds
        self.state = StreamState(chunk_seconds=self._base_chunk)
        self.streamer = Streamer(engine, seed_audio, config.stream, on_stats=self._on_stats)
        self.ring = RingBuffer(self.channels, int(config.buffer_seconds * self.sr))
        self._ov = self.streamer._overlap
        self._last_tail = np.zeros((self.channels, 0), np.float32)
        self._stop = threading.Event()
        self._feeder: Optional[threading.Thread] = None

    # ---- lifecycle ----------------------------------------------------------------

    def start(self) -> "ContinuousStream":
        self.streamer.start()
        self._feeder = threading.Thread(target=self._feed, name="sa3-feeder", daemon=True)
        self._feeder.start()
        return self

    def wait_preroll(self, timeout: float = 600.0) -> None:
        want = int(self.config.preroll_seconds * self.sr)
        t0 = time.monotonic()
        while self.ring.available() < want and time.monotonic() - t0 < timeout and not self._stop.is_set():
            time.sleep(0.05)

    def stop(self) -> None:
        self._stop.set()
        self.streamer.stop()
        self.ring.close()

    # ---- control passthrough --------------------------------------------------------

    def reseed(self, audio: np.ndarray) -> None:
        self.streamer.reseed(audio)

    def set_prompt(self, prompt: Optional[str]) -> None:
        self.streamer.set_prompt(prompt)

    @property
    def prompt(self):
        return self.streamer.prompt

    def seconds_buffered(self) -> float:
        return self.ring.available() / self.sr

    # ---- consumer -----------------------------------------------------------------------

    def read(self, frames: int, block: bool = False) -> np.ndarray:
        """[channels, frames]. Non-blocking by default (for audio callbacks); missing
        frames are zeros and counted in `ring.underrun_frames`."""
        return self.ring.read(frames, block=block)

    # ---- producer side ----------------------------------------------------------------

    def _on_stats(self, s: ChunkStats) -> None:
        self.state.chunks = s.index
        self.state.last_rtf = s.rtf
        cfg = self.config
        if not cfg.adaptive:
            return
        st = cfg.stream
        # Generation cost is roughly proportional to context + chunk, so longer chunks
        # amortise the context. Grow when we are close to real time, shrink when idle.
        if s.rtf > 0.6 and st.chunk_seconds < cfg.max_chunk_seconds:
            st.chunk_seconds = min(cfg.max_chunk_seconds, st.chunk_seconds * 1.5)
            log.info("generation at rtf %.2f: chunk length -> %.1fs", s.rtf, st.chunk_seconds)
        elif s.rtf < 0.25 and st.chunk_seconds > self._base_chunk:
            st.chunk_seconds = max(self._base_chunk, st.chunk_seconds / 1.5)
        self.state.chunk_seconds = st.chunk_seconds

    def _write(self, audio: np.ndarray) -> None:
        self.ring.write(audio, block=True)
        if self._ov:
            self._last_tail = audio[:, -self._ov :]

    def _hold_segment(self) -> Optional[np.ndarray]:
        """One loop of the recent context, crossfaded in from what was last written and
        ending exactly at the point the generator will continue from."""
        ctx = self.streamer.history[:, -self.streamer._ctx :]
        ov = self._ov
        if ctx.shape[1] <= 2 * ov:
            return None
        if self._last_tail.shape[1] == ov and ov:
            head = crossfade(self._last_tail, ctx[:, :ov])
            return np.concatenate([head, ctx[:, ov:]], axis=1)
        return ctx

    def _feed(self) -> None:
        low = int(self.config.low_water_seconds * self.sr)
        while not self._stop.is_set():
            chunk = self.streamer.next_chunk(timeout=0.05)
            if chunk is not None:
                self._write(chunk)
                continue
            if self.ring.available() < low:
                seg = self._hold_segment()
                if seg is not None:
                    self.state.holds += 1
                    log.warning("generator behind: holding on a %.1fs loop of the context", seg.shape[1] / self.sr)
                    self._write(seg)
