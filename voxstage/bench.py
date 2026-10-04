"""Benchmark runner: N repeats x scenarios -> events.jsonl, meta.json, report.md, histogram.

Design choices that protect the numbers:
- warm-up turns run first and are excluded (cold-start is a different question);
- scenarios are interleaved round-robin so slow drift (shared Colab GPU, API
  load) spreads across scenarios instead of biasing one;
- rate-limit sleeping happens between turns, never inside a timed segment;
- every run records its environment in meta.json so a number is never orphaned.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import platform
import subprocess
import sys
import time
from importlib import metadata

from .audio_io import read_wav
from .cost import PriceTable
from .endpointer import EnergyEndpointer
from .events import EventLog
from .metrics import format_markdown, write_report
from .pipeline import Pipeline
from .vendors import build


def parse_opts(items: list[str]) -> dict:
    out: dict = {}
    for it in items:
        k, _, v = it.partition("=")
        for cast in (int, float):
            try:
                v = cast(v)
                break
            except ValueError:
                continue
        else:
            if v.lower() in ("true", "false"):
                v = v.lower() == "true"
        out[k] = v
    return out


def collect_meta(args, opts) -> dict:
    def ver(pkg):
        try:
            return metadata.version(pkg)
        except metadata.PackageNotFoundError:
            return None

    gpu = None
    try:
        gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=5).stdout.strip() or None
    except Exception:
        pass
    return {
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version.split()[0], "platform": platform.platform(), "gpu": gpu,
        "packages": {p: ver(p) for p in ("numpy", "faster-whisper", "google-genai", "melotts")},
        "vendors": {"asr": [args.asr, opts["asr"]], "llm": [args.llm, opts["llm"]], "tts": [args.tts, opts["tts"]]},
        "run": {"repeats": args.repeats, "warmup": args.warmup, "rpm": args.rpm,
                "hangover_ms": args.hangover_ms, "min_sentence_chars": args.min_sentence_chars},
        "note": "Colab shares hardware; compare runs only within the same session or with many repeats.",
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-dir", default="data/audio")
    ap.add_argument("--out", default="runs/latest")
    ap.add_argument("--asr", default="mock")
    ap.add_argument("--llm", default="mock")
    ap.add_argument("--tts", default="mock")
    ap.add_argument("--asr-opt", action="append", default=[])
    ap.add_argument("--llm-opt", action="append", default=[])
    ap.add_argument("--tts-opt", action="append", default=[])
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--rpm", type=float, default=0, help="max LLM requests/min (0 = no throttle)")
    ap.add_argument("--hangover-ms", type=int, default=500)
    ap.add_argument("--min-sentence-chars", type=int, default=8)
    ap.add_argument("--prices", default=None, help="optional prices.json for shadow cost")
    args = ap.parse_args(argv)

    opts = {k: parse_opts(getattr(args, f"{k}_opt")) for k in ("asr", "llm", "tts")}
    os.makedirs(args.out, exist_ok=True)
    events_path = os.path.join(args.out, "events.jsonl")
    if os.path.exists(events_path):
        os.remove(events_path)

    clips = []
    for meta_path in sorted(glob.glob(os.path.join(args.audio_dir, "*.json"))):
        side = json.load(open(meta_path, encoding="utf-8"))
        audio, sr = read_wav(meta_path[:-5] + ".wav")
        clips.append((side["id"], audio, sr, side["truth_end_s"]))
    if not clips:
        sys.exit(f"no audio in {args.audio_dir}; run: python -m voxstage.make_audio")

    log = EventLog(events_path)
    pipe = Pipeline(build("asr", args.asr, **opts["asr"]), build("llm", args.llm, **opts["llm"]),
                    build("tts", args.tts, **opts["tts"]), log=log,
                    endpointer=EnergyEndpointer(hangover_ms=args.hangover_ms),
                    prices=PriceTable.load(args.prices), min_sentence_chars=args.min_sentence_chars)

    schedule = [("warmup", i, clips[0], True) for i in range(args.warmup)]
    for r in range(args.repeats):
        for clip in clips:  # interleave scenarios round-robin
            schedule.append((clip[0], r, clip, False))

    min_gap = 60.0 / args.rpm if args.rpm else 0.0
    last_start = 0.0
    for n, (sid, turn, (cid, audio, sr, truth), warm) in enumerate(schedule, 1):
        wait = last_start + min_gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)  # outside any timed segment
        last_start = time.monotonic()
        res = pipe.run_turn(sid, turn, audio, sr, truth, warmup=warm)
        flag = "warmup" if warm else ("ok" if res.ok else f"ERROR {res.error}")
        print(f"[{n}/{len(schedule)}] {sid}#{turn} {flag}")
    log.close()

    meta = collect_meta(args, opts)
    with open(os.path.join(args.out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    summary = write_report(args.out, meta)
    print(format_markdown(summary))


if __name__ == "__main__":
    main()
