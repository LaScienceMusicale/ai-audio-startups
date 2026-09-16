"""Command line: `sa3-endless --samples my_folder`."""

from __future__ import annotations

import argparse
import logging
import random
import sys
import threading
import time
from typing import List, Optional

from .continuous import ContinuousConfig, ContinuousStream
from .engine import MockEngine, StableAudioEngine
from .samples import list_samples, load_sample
from .sinks import CallbackOutput, WavSink
from .streamer import ChunkStats, StreamConfig

log = logging.getLogger("sa3_endless")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sa3-endless",
        description="Load short samples and let them continue forever with Stable Audio 3.",
    )
    p.add_argument("--samples", required=True, help="audio file or folder of samples to seed from")
    p.add_argument("--engine", choices=["sa3", "mock"], default="sa3", help="mock = no model, loops the sample")
    p.add_argument("--model", default="small-sfx", help="Stable Audio 3 model: small-sfx, small-music, medium, ...")
    p.add_argument("--device", default=None, help="torch device (cuda, mps, cpu). Default: auto")
    p.add_argument("--steps", type=int, default=8, help="diffusion steps (8 is the SA3 default)")
    p.add_argument("--cfg-scale", type=float, default=1.0)
    p.add_argument("--prompt", default=None, help="optional text prompt guiding the continuation")
    p.add_argument("--chunk", type=float, default=8.0, help="seconds of new audio per generation")
    p.add_argument("--context", type=float, default=10.0, help="seconds of past audio given to the model")
    p.add_argument("--overlap", type=float, default=0.5, help="seconds regenerated and crossfaded at each seam")
    p.add_argument("--lookahead", type=int, default=1, help="chunks generated ahead of the ring buffer")
    p.add_argument("--buffer", type=float, default=30.0, help="seconds of audio kept ahead of playback")
    p.add_argument("--low-water", type=float, default=3.0, help="below this many buffered seconds, loop the context instead of going silent")
    p.add_argument("--preroll", type=float, default=4.0, help="seconds buffered before playback starts")
    p.add_argument("--max-chunk", type=float, default=30.0, help="cap for the adaptive chunk length")
    p.add_argument("--no-adaptive", action="store_true", help="keep --chunk fixed instead of adapting to generation speed")
    p.add_argument("--blocksize", type=int, default=1024, help="audio callback block size in frames")
    p.add_argument("--seed", type=int, default=-1, help="generation seed (-1 = random)")
    p.add_argument("--switch-every", type=float, default=0.0, help="seconds between automatic re-seeds from another sample (0 = off)")
    p.add_argument("--shuffle", action="store_true", help="pick samples at random instead of in order")
    p.add_argument("--output", default=None, help="also record everything played to this WAV file")
    p.add_argument("--render", type=float, default=0.0, help="render this many seconds to --output without playing (offline)")
    p.add_argument("--audio-device", default=None, help="sounddevice output device name or index")
    p.add_argument("--osc-port", type=int, default=0, help="listen for OSC control on this UDP port (0 = off)")
    p.add_argument("--no-stdin", action="store_true", help="disable keyboard control (for headless services)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


class SampleDeck:
    """Keeps the list of sample files and which one comes next."""

    def __init__(self, files: List[str], shuffle: bool):
        self.files = files
        self.shuffle = shuffle
        self.index = -1

    def next_path(self) -> str:
        if self.shuffle and len(self.files) > 1:
            choices = [i for i in range(len(self.files)) if i != self.index]
            self.index = random.choice(choices)
        else:
            self.index = (self.index + 1) % len(self.files)
        return self.files[self.index]

    def path_for(self, key: str) -> Optional[str]:
        if key.isdigit() and int(key) < len(self.files):
            self.index = int(key)
            return self.files[self.index]
        for i, f in enumerate(self.files):
            if key in f:
                self.index = i
                return f
        return None


def _start_stdin_control(streamer: ContinuousStream, deck: SampleDeck, sr: int, ch: int, stop: threading.Event) -> None:
    help_text = "keys:  n = next sample   s <name|index> = seed with sample   p <text> = prompt   p = clear prompt   q = quit"
    print(help_text, flush=True)

    def loop():
        for line in sys.stdin:
            cmd = line.strip()
            if not cmd:
                continue
            if cmd == "q":
                stop.set()
                return
            if cmd == "n":
                path = deck.next_path()
                streamer.reseed(load_sample(path, sr, ch))
                print(f"-> reseed {path}", flush=True)
            elif cmd.startswith("s "):
                path = deck.path_for(cmd[2:].strip())
                if path:
                    streamer.reseed(load_sample(path, sr, ch))
                    print(f"-> reseed {path}", flush=True)
                else:
                    print("unknown sample", flush=True)
            elif cmd == "p":
                streamer.set_prompt(None)
                print("-> prompt cleared", flush=True)
            elif cmd.startswith("p "):
                streamer.set_prompt(cmd[2:].strip())
                print(f"-> prompt {streamer.prompt!r}", flush=True)
            else:
                print(help_text, flush=True)

    threading.Thread(target=loop, name="stdin", daemon=True).start()


def _start_osc_control(port: int, streamer: ContinuousStream, deck: SampleDeck, sr: int, ch: int, stop: threading.Event):
    try:
        from pythonosc.dispatcher import Dispatcher
        from pythonosc.osc_server import ThreadingOSCUDPServer
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("python-osc is not installed. Run: pip install -e '.[osc]'") from exc

    def on_reseed(_addr, *args):
        path = deck.path_for(str(args[0])) if args else deck.next_path()
        if path:
            streamer.reseed(load_sample(path, sr, ch))
            log.info("osc reseed %s", path)

    def on_prompt(_addr, *args):
        streamer.set_prompt(" ".join(str(a) for a in args) if args else None)
        log.info("osc prompt %r", streamer.prompt)

    def on_stop(_addr, *args):
        stop.set()

    d = Dispatcher()
    d.map("/reseed", on_reseed)
    d.map("/prompt", on_prompt)
    d.map("/stop", on_stop)
    server = ThreadingOSCUDPServer(("0.0.0.0", port), d)
    threading.Thread(target=server.serve_forever, name="osc", daemon=True).start()
    log.info("OSC listening on udp/%d  (/reseed [name|index], /prompt <text>, /stop)", port)
    return server


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.render and not args.output:
        raise SystemExit("--render needs --output")

    files = list_samples(args.samples)
    deck = SampleDeck(files, args.shuffle)

    if args.engine == "mock":
        engine = MockEngine()
    else:
        engine = StableAudioEngine(args.model, device=args.device, steps=args.steps, cfg_scale=args.cfg_scale)
        engine.load()
    sr, ch = engine.sample_rate, engine.channels

    def on_stats(s: ChunkStats):
        log.info("chunk %d  +%.1fs generated in %.1fs  (rtf %.2f)", s.index, s.seconds, s.gen_time, s.rtf)

    config = ContinuousConfig(
        stream=StreamConfig(
            chunk_seconds=args.chunk,
            context_seconds=args.context,
            overlap_seconds=args.overlap,
            lookahead=args.lookahead,
            prompt=args.prompt,
            seed=args.seed,
        ),
        buffer_seconds=args.buffer,
        low_water_seconds=args.low_water,
        preroll_seconds=args.preroll,
        max_chunk_seconds=args.max_chunk,
        adaptive=not args.no_adaptive,
    )
    first = deck.next_path()
    log.info("seeding from %s (%d sample(s) available)", first, len(files))
    stream = ContinuousStream(engine, load_sample(first, sr, ch), config)
    stream.streamer.on_stats = lambda s: (on_stats(s), stream._on_stats(s))
    stream.start()

    stop = threading.Event()
    recorder = WavSink(args.output, sr, ch) if args.output else None
    if not args.no_stdin and not args.render and sys.stdin.isatty():
        _start_stdin_control(stream, deck, sr, ch, stop)
    if args.osc_port:
        _start_osc_control(args.osc_port, stream, deck, sr, ch, stop)

    played = 0.0
    output = None
    next_switch = time.monotonic() + args.switch_every if args.switch_every else None
    try:
        if args.render:
            block = args.blocksize
            while played < args.render and not stop.is_set():
                if next_switch is not None and time.monotonic() >= next_switch:
                    path = deck.next_path()
                    stream.reseed(load_sample(path, sr, ch))
                    log.info("auto reseed %s", path)
                    next_switch = time.monotonic() + args.switch_every
                recorder.write(stream.read(block, block=True))
                played += block / sr
        else:
            log.info("buffering %.1fs before playback...", args.preroll)
            stream.wait_preroll()
            output = CallbackOutput(stream, device=args.audio_device, blocksize=args.blocksize, tee=recorder)
            output.start()
            log.info("playing. %.1fs buffered", stream.seconds_buffered())
            last_report = time.monotonic()
            while not stop.is_set():
                time.sleep(0.2)
                if next_switch is not None and time.monotonic() >= next_switch:
                    path = deck.next_path()
                    stream.reseed(load_sample(path, sr, ch))
                    log.info("auto reseed %s", path)
                    next_switch = time.monotonic() + args.switch_every
                if args.verbose and time.monotonic() - last_report > 10:
                    last_report = time.monotonic()
                    log.debug("buffer %.1fs  chunk %.1fs  rtf %.2f  holds %d  underrun frames %d",
                              stream.seconds_buffered(), stream.state.chunk_seconds, stream.state.last_rtf,
                              stream.state.holds, stream.ring.underrun_frames)
            played = output.frames / sr
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()
        if output is not None:
            output.close()
        elif recorder is not None:
            recorder.close()
        log.info("stopped after %.0fs of audio (%d holds, %d underrun frames)",
                 played, stream.state.holds, stream.ring.underrun_frames)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
