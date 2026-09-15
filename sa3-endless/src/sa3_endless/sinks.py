"""Consumer side: where the chunks go (sound card, WAV file, or both)."""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)


class WavSink:
    def __init__(self, path: str, sample_rate: int, channels: int):
        import soundfile as sf

        self.file = sf.SoundFile(path, mode="w", samplerate=sample_rate, channels=channels, subtype="PCM_24")

    def write(self, chunk: np.ndarray) -> None:
        self.file.write(np.ascontiguousarray(chunk.T))

    def close(self) -> None:
        self.file.close()


class SoundDeviceSink:
    """Blocking playback through PortAudio (pip install -e '.[audio]')."""

    def __init__(self, sample_rate: int, channels: int, device: Optional[str] = None, blocksize: int = 2048):
        try:
            import sounddevice as sd
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("sounddevice is not installed. Run: pip install -e '.[audio]'") from exc
        self.sd = sd
        self.stream = sd.OutputStream(
            samplerate=sample_rate, channels=channels, dtype="float32", device=device, blocksize=blocksize
        )
        self.stream.start()

    def write(self, chunk: np.ndarray) -> None:
        self.stream.write(np.ascontiguousarray(chunk.T))

    def close(self) -> None:
        self.stream.stop()
        self.stream.close()


class MultiSink:
    def __init__(self, *sinks):
        self.sinks = [s for s in sinks if s is not None]

    def write(self, chunk: np.ndarray) -> None:
        for s in self.sinks:
            s.write(chunk)

    def close(self) -> None:
        for s in self.sinks:
            s.close()
