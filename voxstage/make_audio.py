"""Generate ground-truth test audio: <id>.wav (16 kHz mono) + <id>.json sidecar.

The sidecar holds `truth_end_s`, the exact end of speech, which is what makes
T1 (endpointing latency) measurable instead of guessed.

Caveat worth stating in any write-up: TTS-generated input is clean, so ASR
numbers on it are optimistic. Real-microphone and noisy audio come later.
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np

from .audio_io import resample, write_wav
from .vendors import build

SR = 16000
LEAD_S = 0.4
TAIL_S = 1.2  # must exceed the endpointer hangover, or detection is clipped


def synthetic_speech(duration_s: float, sr: int = SR, seed: int = 0) -> np.ndarray:
    """Syllable-like tone bursts. Only for mock runs; real runs use a real TTS."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(duration_s * sr)) / sr
    f0 = rng.uniform(120, 220)
    carrier = np.sin(2 * np.pi * f0 * t) + 0.5 * np.sin(2 * np.pi * 2 * f0 * t)
    envelope = 0.5 * (1 + np.sin(2 * np.pi * 4 * t - np.pi / 2))  # ~4 syllables/s
    return (0.25 * carrier * envelope).astype(np.float32)


def last_active_s(audio: np.ndarray, sr: int, threshold_dbfs: float = -50.0, frame_ms: int = 10) -> float:
    n = int(sr * frame_ms / 1000)
    frames = audio[: (len(audio) // n) * n].astype(np.float64).reshape(-1, n)
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1) + 1e-12) + 1e-12)
    idx = np.nonzero(db > threshold_dbfs)[0]
    return float((idx[-1] + 1) * n / sr) if len(idx) else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default="data/scenarios.json")
    ap.add_argument("--out", default="data/audio")
    ap.add_argument("--tts", default="mock", help="mock | melo")
    ap.add_argument("--tts-opt", action="append", default=[], help="key=value")
    args = ap.parse_args()

    from .bench import parse_opts  # shared key=value parsing

    scenarios = json.load(open(args.scenarios, encoding="utf-8"))
    os.makedirs(args.out, exist_ok=True)
    tts = build("tts", args.tts, **parse_opts(args.tts_opt))

    for i, sc in enumerate(scenarios):
        if args.tts == "mock":
            speech = synthetic_speech(min(8.0, max(1.0, 0.11 * len(sc["text"]))), SR, seed=i)
        else:
            chunks = list(tts.synthesize(sc["text"]))
            speech = np.concatenate([resample(c.pcm, c.sample_rate, SR) for c in chunks])
        truth_end = LEAD_S + last_active_s(speech, SR)
        audio = np.concatenate([np.zeros(int(LEAD_S * SR), np.float32), speech,
                                np.zeros(int(TAIL_S * SR), np.float32)])
        write_wav(os.path.join(args.out, f"{sc['id']}.wav"), audio, SR)
        with open(os.path.join(args.out, f"{sc['id']}.json"), "w", encoding="utf-8") as f:
            json.dump({"id": sc["id"], "text": sc["text"], "sample_rate": SR,
                       "truth_end_s": truth_end, "duration_s": len(audio) / SR,
                       "source": f"tts:{args.tts}"}, f, ensure_ascii=False, indent=2)
        print(f"{sc['id']}: {len(audio) / SR:.2f}s, truth_end={truth_end:.2f}s")


if __name__ == "__main__":
    main()
