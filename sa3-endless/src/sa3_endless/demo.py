"""`sa3-endless-demo`: seed of N seconds -> continuation of M seconds, files + listening page."""

from __future__ import annotations

import argparse
import html
import logging
import os
import time
from typing import List, Optional

import numpy as np
import soundfile as sf

from .continuous import ContinuousConfig, ContinuousStream
from .engine import MockEngine, StableAudioEngine
from .samples import load_sample
from .streamer import StreamConfig

log = logging.getLogger("sa3_endless.demo")

PAGE = """<!doctype html><meta charset="utf-8"><title>sa3-endless demo</title>
<style>body{{font:15px/1.5 system-ui;max-width:720px;margin:2rem auto;padding:0 1rem;color:#222}}
audio{{width:100%}}h2{{margin-top:2rem}}small{{color:#666}}</style>
<h1>sa3-endless</h1>
<p>{engine} · seed <b>{seed_name}</b> · {seed_s:.0f} s de départ, {cont_s:.0f} s de suite · chunks {chunk:.0f} s, contexte {context:.0f} s, overlap {overlap:.2f} s{prompt}</p>
<h2>1. Le son de départ ({seed_s:.0f} s)</h2><audio controls src="seed.wav"></audio>
<h2>2. La suite générée seule ({cont_s:.0f} s)</h2><audio controls src="continuation.wav"></audio>
<h2>3. Enchaîné ({total_s:.0f} s)</h2><audio controls src="full.wav"></audio>
<p><small>La suite commence à {seed_s:.0f} s. {stats}</small></p>
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sa3-endless-demo", description="Render seed + continuation for listening.")
    p.add_argument("--seed", required=True, help="audio file used as the starting sound")
    p.add_argument("--seed-seconds", type=float, default=10.0, help="how much of the file to use (from its start)")
    p.add_argument("--seconds", type=float, default=50.0, help="length of the generated continuation")
    p.add_argument("--out", default="demo", help="output folder")
    p.add_argument("--engine", choices=["sa3", "mock"], default="sa3")
    p.add_argument("--model", default="small-sfx")
    p.add_argument("--device", default=None)
    p.add_argument("--steps", type=int, default=8)
    p.add_argument("--prompt", default=None)
    p.add_argument("--chunk", type=float, default=10.0)
    p.add_argument("--context", type=float, default=10.0)
    p.add_argument("--overlap", type=float, default=0.5)
    p.add_argument("--gen-seed", type=int, default=-1, help="generation seed for reproducibility")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def render(engine, seed_audio: np.ndarray, seconds: float, cfg: StreamConfig, stats: List[str]) -> np.ndarray:
    """Return seed followed by `seconds` of generated continuation, through the real streaming path."""
    sr = engine.sample_rate
    stream = ContinuousStream(
        engine, seed_audio,
        ContinuousConfig(stream=cfg, buffer_seconds=seconds + cfg.chunk_seconds,
                         low_water_seconds=0.0, preroll_seconds=0.0),
    )
    stream.streamer.on_stats = lambda s: (
        stats.append(f"chunk {s.index}: +{s.seconds:.0f}s en {s.gen_time:.1f}s (rtf {s.rtf:.2f})"),
        stream._on_stats(s),
    )
    stream.start()
    total = int((seed_audio.shape[1] / sr + seconds) * sr)
    out = np.zeros((engine.channels, 0), np.float32)
    try:
        while out.shape[1] < total:
            out = np.concatenate([out, stream.read(4096, block=True)], axis=1)
    finally:
        stream.stop()
    return out[:, :total]


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.engine == "mock":
        engine = MockEngine()
        engine_name = "moteur factice (boucle du sample, pas de modèle)"
    else:
        engine = StableAudioEngine(args.model, device=args.device, steps=args.steps)
        engine.load()
        engine_name = f"Stable Audio 3 {args.model}, {args.steps} steps"
    sr, ch = engine.sample_rate, engine.channels

    seed = load_sample(args.seed, sr, ch)[:, : int(args.seed_seconds * sr)]
    seed_s = seed.shape[1] / sr
    cfg = StreamConfig(chunk_seconds=args.chunk, context_seconds=args.context, overlap_seconds=args.overlap,
                       lookahead=1, prompt=args.prompt, seed=args.gen_seed)
    stats: List[str] = []
    t0 = time.perf_counter()
    full = render(engine, seed, args.seconds, cfg, stats)
    elapsed = time.perf_counter() - t0
    n_seed = seed.shape[1]

    os.makedirs(args.out, exist_ok=True)
    sf.write(os.path.join(args.out, "seed.wav"), full[:, :n_seed].T, sr, subtype="PCM_24")
    sf.write(os.path.join(args.out, "continuation.wav"), full[:, n_seed:].T, sr, subtype="PCM_24")
    sf.write(os.path.join(args.out, "full.wav"), full.T, sr, subtype="PCM_24")
    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.format(
            engine=html.escape(engine_name), seed_name=html.escape(os.path.basename(args.seed)),
            seed_s=seed_s, cont_s=args.seconds, total_s=full.shape[1] / sr,
            chunk=args.chunk, context=args.context, overlap=args.overlap,
            prompt=f" · prompt « {html.escape(args.prompt)} »" if args.prompt else " · sans prompt",
            stats=html.escape(f"Rendu en {elapsed:.0f} s. " + " · ".join(stats)),
        ))
    log.info("wrote %s/{seed,continuation,full}.wav and index.html in %.0fs", args.out, elapsed)
    for line in stats:
        log.info(line)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
