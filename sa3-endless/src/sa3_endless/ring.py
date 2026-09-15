"""Thread-safe ring buffer of float32 audio, shape [channels, frames]."""

from __future__ import annotations

import threading

import numpy as np


class RingBuffer:
    def __init__(self, channels: int, capacity_frames: int):
        self.channels = channels
        self.capacity = int(capacity_frames)
        self._buf = np.zeros((channels, self.capacity), dtype=np.float32)
        self._read = 0
        self._count = 0
        self._cv = threading.Condition()
        self.underrun_frames = 0
        self.closed = False

    def available(self) -> int:
        with self._cv:
            return self._count

    def free(self) -> int:
        with self._cv:
            return self.capacity - self._count

    def write(self, chunk: np.ndarray, block: bool = True) -> int:
        """Write all of `chunk`; blocks while the buffer is full unless block=False (then truncates)."""
        chunk = np.asarray(chunk, dtype=np.float32)
        n = chunk.shape[1]
        written = 0
        with self._cv:
            while written < n and not self.closed:
                space = self.capacity - self._count
                if space == 0:
                    if not block:
                        break
                    self._cv.wait(timeout=0.1)
                    continue
                take = min(space, n - written)
                w = (self._read + self._count) % self.capacity
                first = min(take, self.capacity - w)
                self._buf[:, w : w + first] = chunk[:, written : written + first]
                if take > first:
                    self._buf[:, : take - first] = chunk[:, written + first : written + take]
                self._count += take
                written += take
                self._cv.notify_all()
        return written

    def read(self, frames: int, block: bool = False, timeout: float | None = None) -> np.ndarray:
        """Read `frames` frames. Missing frames are zero-filled and counted as underrun
        (unless block=True, then it waits for them)."""
        out = np.zeros((self.channels, frames), dtype=np.float32)
        got = 0
        with self._cv:
            while got < frames:
                if self._count == 0:
                    if block and not self.closed:
                        if not self._cv.wait(timeout=timeout):
                            break
                        continue
                    break
                take = min(self._count, frames - got)
                first = min(take, self.capacity - self._read)
                out[:, got : got + first] = self._buf[:, self._read : self._read + first]
                if take > first:
                    out[:, got + first : got + take] = self._buf[:, : take - first]
                self._read = (self._read + take) % self.capacity
                self._count -= take
                got += take
                self._cv.notify_all()
            if got < frames:
                self.underrun_frames += frames - got
        return out

    def close(self) -> None:
        with self._cv:
            self.closed = True
            self._cv.notify_all()
