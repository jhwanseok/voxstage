"""Turn JSONL events into per-segment latency distributions.

Segments (ms):
  T1   speech end -> endpoint detected        (audio time, endpointer's own latency)
  T2   endpoint -> ASR final transcript
  T3   LLM request -> first token
  T3b  first token -> first speakable sentence (sentence-chunking delay)
  T4   TTS request -> first audio chunk
  T5   first chunk -> playback start           (n/a unless a real sink measures it)
  E2E  speech end -> first audio chunk         (what the caller experiences, minus playback)

Warm-up turns and failed turns are excluded from distributions and counted separately.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Optional

import numpy as np

from .events import read_events

SEGMENTS = [
    ("T1", "speech end -> endpoint"),
    ("T2", "endpoint -> ASR final"),
    ("T3", "LLM request -> first token"),
    ("T3b", "first token -> first sentence"),
    ("T4", "TTS request -> first chunk"),
    ("T5", "first chunk -> playback"),
    ("E2E", "speech end -> first audio chunk"),
]


def _first(evs: list[dict], etype: str, **match) -> Optional[dict]:
    for e in evs:
        if e["type"] == etype and all(e["data"].get(k) == v for k, v in match.items()):
            return e
    return None


def compute_turns(events: list[dict]) -> dict:
    by_turn: dict[tuple, list[dict]] = defaultdict(list)
    for e in events:
        by_turn[(e["session_id"], e["turn"], e["warmup"])].append(e)

    turns, errors, warmups = [], [], 0
    for (sid, turn, warm), evs in by_turn.items():
        if warm:
            warmups += 1
            continue
        err = _first(evs, "error")
        if err:
            errors.append({"session_id": sid, "turn": turn, **err["data"]})
            continue
        ep = _first(evs, "endpoint")
        asr_req, asr_fin = _first(evs, "asr_request"), _first(evs, "asr_final")
        llm_req, llm_tok = _first(evs, "llm_request"), _first(evs, "llm_first_token")
        sent = _first(evs, "llm_first_sentence")
        tts_req = _first(evs, "tts_request", sentence_idx=0)
        tts_chunk = _first(evs, "tts_first_chunk", sentence_idx=0)
        play = _first(evs, "playback_start")
        if not all([ep, asr_req, asr_fin, llm_req, llm_tok, sent, tts_req, tts_chunk]):
            errors.append({"session_id": sid, "turn": turn, "stage": "incomplete",
                           "error": "missing events for first-sentence path"})
            continue
        t1 = (ep["data"]["detected_s"] - ep["data"]["truth_end_s"]) * 1000
        seg = {
            "T1": t1,
            "T2": (asr_fin["t"] - ep["t"]) * 1000,
            "T3": (llm_tok["t"] - llm_req["t"]) * 1000,
            "T3b": (sent["t"] - llm_tok["t"]) * 1000,
            "T4": (tts_chunk["t"] - tts_req["t"]) * 1000,
            "E2E": t1 + (tts_chunk["t"] - ep["t"]) * 1000,
        }
        if play and play["data"].get("measured"):
            seg["T5"] = (play["t"] - tts_chunk["t"]) * 1000
        seg["unattributed"] = seg["E2E"] - (seg["T1"] + seg["T2"] + seg["T3"] + seg["T3b"] + seg["T4"])
        seg["clipped"] = bool(ep["data"].get("clipped"))
        seg["session_id"], seg["turn"] = sid, turn
        turns.append(seg)
    return {"turns": turns, "errors": errors, "warmup_turns": warmups}


def stats(values: list[float]) -> dict:
    a = np.asarray(values, dtype=float)
    return {
        "n": int(a.size), "mean": float(a.mean()), "p50": float(np.percentile(a, 50)),
        "p95": float(np.percentile(a, 95)), "p99": float(np.percentile(a, 99)),
        "min": float(a.min()), "max": float(a.max()),
    }


def summarize(computed: dict, events: list[dict]) -> dict:
    turns = computed["turns"]
    segs = {}
    for name, _ in SEGMENTS:
        vals = [t[name] for t in turns if name in t]
        if vals:
            segs[name] = stats(vals)
    cost = defaultdict(lambda: defaultdict(float))
    for e in events:
        if e["type"] == "cost" and not e["warmup"]:
            d = e["data"]
            cost[d["kind"]]["shadow_usd"] += d.get("shadow_usd", 0.0)
            for k, v in d.get("usage", {}).items():
                if isinstance(v, (int, float)):
                    cost[d["kind"]][k] += v
    return {
        "segments": segs,
        "n_ok": len(turns),
        "n_errors": len(computed["errors"]),
        "n_warmup": computed["warmup_turns"],
        "n_clipped_endpoint": sum(1 for t in turns if t["clipped"]),
        "cost": {k: dict(v) for k, v in cost.items()},
        "errors": computed["errors"][:10],
    }


def format_markdown(summary: dict, meta: Optional[dict] = None) -> str:
    L = []
    L.append("# Latency report")
    if meta:
        L.append("")
        L.append("```json")
        L.append(json.dumps(meta, ensure_ascii=False, indent=2))
        L.append("```")
    L.append("")
    L.append(f"Turns ok: {summary['n_ok']} · errors: {summary['n_errors']} · "
             f"warm-up (excluded): {summary['n_warmup']} · endpoint clipped: {summary['n_clipped_endpoint']}")
    n = summary["n_ok"]
    if n and n < 100:
        L.append("")
        L.append(f"> n={n}: p95 is a rough estimate and p99 is essentially the max. "
                 "Treat tail percentiles as indicative until n >= 100 per segment.")
    L.append("")
    L.append("| segment | what | n | mean | p50 | p95 | p99 | max |")
    L.append("|---|---|---|---|---|---|---|---|")
    desc = dict(SEGMENTS)
    for name, _ in SEGMENTS:
        s = summary["segments"].get(name)
        if s is None:
            L.append(f"| {name} | {desc[name]} | 0 | n/a | n/a | n/a | n/a | n/a |")
            continue
        L.append(f"| {name} | {desc[name]} | {s['n']} | {s['mean']:.0f} | {s['p50']:.0f} | "
                 f"{s['p95']:.0f} | {s['p99']:.0f} | {s['max']:.0f} |")
    L.append("")
    L.append("All values in milliseconds. T5 is n/a when the sink does not really play audio.")
    if summary["cost"]:
        L.append("")
        L.append("## Cost (shadow USD at the configured price table; 0 if prices were not set)")
        for kind, d in summary["cost"].items():
            L.append(f"- {kind}: " + ", ".join(f"{k}={v:.4g}" for k, v in d.items()))
    if summary["errors"]:
        L.append("")
        L.append("## First errors")
        for e in summary["errors"]:
            L.append(f"- turn {e['session_id']}/{e['turn']} stage={e.get('stage')}: {e.get('error')}")
    return "\n".join(L) + "\n"


def plot_histograms(computed: dict, path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = [n for n, _ in SEGMENTS if n != "T5" and any(n in t for t in computed["turns"])]
    if not names:
        return
    cols = 3
    rows = (len(names) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 3 * rows), squeeze=False)
    for ax, name in zip(axes.flat, names):
        vals = [t[name] for t in computed["turns"] if name in t]
        ax.hist(vals, bins=min(20, max(5, len(vals) // 2)), color="#3346c8", alpha=0.85)
        p50, p95 = np.percentile(vals, 50), np.percentile(vals, 95)
        ax.axvline(p50, color="#1f7a4d", lw=1.5, label=f"p50 {p50:.0f}")
        ax.axvline(p95, color="#b3322b", lw=1.5, label=f"p95 {p95:.0f}")
        ax.set_title(f"{name}  (n={len(vals)})", fontsize=10)
        ax.set_xlabel("ms")
        ax.legend(fontsize=8)
    for ax in list(axes.flat)[len(names):]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def write_report(out_dir: str, meta: Optional[dict] = None) -> dict:
    events = read_events(os.path.join(out_dir, "events.jsonl"))
    computed = compute_turns(events)
    summary = summarize(computed, events)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(format_markdown(summary, meta))
    plot_histograms(computed, os.path.join(out_dir, "latency_hist.png"))
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Summarize an events.jsonl run directory")
    ap.add_argument("out_dir")
    args = ap.parse_args()
    meta_path = os.path.join(args.out_dir, "meta.json")
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else None
    summary = write_report(args.out_dir, meta)
    print(format_markdown(summary))


if __name__ == "__main__":
    main()
