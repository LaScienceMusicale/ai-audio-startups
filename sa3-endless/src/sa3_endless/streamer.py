"""Producer side: turns an engine into an endless stream of audio chunks."""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from .dsp import crossfade, to_channels
from .engine import Engine

log = logging.getLogger(__name__)


@dataclass
class StreamConfig:
    chunk_seconds: float = 8.0  # how much new audio each generation adds
    context_seconds: float = 10.0  # how much recent audio the model sees
    overlap_seconds: float = 0.5  # regenerated and crossfaded to hide the seam
    lookahead: int = 2  # chunks generated ahead of playback
    prompt: Optional[str] = None
    seed: int = -1  # -1 = random every chunk


@dataclass
class ChunkStats:
    index: int
    seconds: float
    gen_time: float

    @property
    def rtf(self) -> float:
        """Real-time factor: generation time / audio time. Above 1.0 the stream falls behind."""
        return self.gen_time / self.seconds if self.seconds else float("inf")


class Streamer:
    """Generates audio continuously from a seed sample.

    Every chunk is produced by asking the engine to continue the last
    `context_seconds` of what has been emitted. The last `overlap_seconds` of the
    previous chunk are regenerated and crossfaded with the new audio so that no
    seam is audible. Consumers call `next_chunk()`; it blocks until audio is ready.
    """

    def __init__(
        self,
        engine: Engine,
        seed_audio: np.ndarray,
        config: StreamConfig = StreamConfig(),
        on_stats: Optional[Callable[[ChunkStats], None]] = None,
    ):
        self.engine = engine
        self.config = config
        self.on_stats = on_stats
        self.sr = engine.sample_rate
        self.channels = engine.channels
        self._overlap = int(round(config.overlap_seconds * self.sr))
        self._ctx = int(round(config.context_seconds * self.sr))
        self._queue: queue.Queue[Optional[np.ndarray]] = queue.Queue(maxsize=max(1, config.lookahead))
        self._lock = threading.Lock()
        self._reseed: Optional[np.ndarray] = None
        self._prompt = config.prompt
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._index = 0
        self.history = np.zeros((self.channels, 0), dtype=np.float32)  # everything emitted
        self._pending_tail = np.zeros((self.channels, 0), dtype=np.float32)
        self.reseed(seed_audio)

    # ---- control -----------------------------------------------------------------

    def reseed(self, audio: np.ndarray) -> None:
        """Crossfade into `audio` (at engine sample rate) and continue from there."""
        audio = to_channels(audio, self.channels)
        if audio.shape[1] <= self._overlap * 2:
            raise ValueError("seed audio is too short for the configured overlap")
        with self._lock:
            self._reseed = audio

    def set_prompt(self, prompt: Optional[str]) -> None:
        with self._lock:
            self._prompt = prompt or None

    @property
    def prompt(self) -> Optional[str]:
        return self._prompt

    def start(self) -> "Streamer":
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="sa3-producer", daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        # unblock a producer waiting on a full queue
        try:
            self._queue.get_nowait()
        except queue.Empty:
            pass

    def next_chunk(self, timeout: Optional[float] = None) -> Optional[np.ndarray]:
        """Blocking. Returns [channels, samples], or None once stopped."""
        if self._stop.is_set() and self._queue.empty():
            return None
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    # ---- producer ----------------------------------------------------------------

    def _emit(self, audio: np.ndarray) -> None:
        """Crossfade `audio` onto the pending tail, keep a new tail, queue the rest."""
        ov = self._overlap
        if self._pending_tail.shape[1] == ov and ov > 0:
            head = crossfade(self._pending_tail, audio[:, :ov])
            body = np.concatenate([head, audio[:, ov:-ov]], axis=1)
        else:  # very first chunk: nothing to fade from
            body = audio[:, :-ov] if ov > 0 else audio
        self._pending_tail = audio[:, -ov:] if ov > 0 else np.zeros((self.channels, 0), np.float32)
        self.history = np.concatenate([self.history, body], axis=1)[:, -(self._ctx + ov) :]
        self._queue.put(body)

    def _context(self) -> np.ndarray:
        """Recent audio the model should continue, ending where the pending tail starts."""
        return self.history[:, -self._ctx :]

    def _step(self) -> None:
        with self._lock:
            reseed = self._reseed
            self._reseed = None
            prompt = self._prompt
        if reseed is not None:
            self._emit(reseed)
            return
        cfg = self.config
        want = cfg.overlap_seconds + cfg.chunk_seconds + cfg.overlap_seconds
        t0 = time.perf_counter()
        new = self.engine.continue_audio(self._context(), want, prompt=prompt, seed=cfg.seed)
        gen = time.perf_counter() - t0
        new = to_channels(new, self.channels)
        n_want = int(round(want * self.sr))
        if new.shape[1] != n_want:
            new = np.pad(new, ((0, 0), (0, max(0, n_want - new.shape[1]))))[:, :n_want]
        self._index += 1
        stats = ChunkStats(self._index, cfg.chunk_seconds, gen)
        if stats.rtf > 1.0:
            log.warning("chunk %d: generation slower than real time (rtf %.2f)", stats.index, stats.rtf)
        if self.on_stats:
            self.on_stats(stats)
        self._emit(new)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._step()
            except Exception:  # keep the installation alive, log and retry
                log.exception("generation failed, retrying in 1s")
                time.sleep(1.0)
        self._queue.put(None)
